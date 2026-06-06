#!/usr/bin/env python3
"""
mp42naf — Convert MP4 video to NAF animation.

Usage:
  python mp42naf bad_apple.mp4 -o bad_apple.naf -W 128 -H 64 --fps 12 --dither
"""

import argparse, sys, subprocess, os, tempfile
from PIL import Image, ImageOps
from naf_encoder import NAFEncoder
from naf_convert import image_to_pages, floyd_steinberg
import imageio_ffmpeg


def mp4_to_naf(input_path, output_path, width, height,
               fps=12, threshold=128, dither=True, use_delta=True,
               invert=True, callback=None):
    """
    Convert MP4 video to NAF animation.

    Args:
        input_path:  Path to .mp4 file
        output_path: Output .naf file
        width, height: Target size
        fps:         Output frame rate
        threshold:   Monochrome threshold
        dither:      Floyd-Steinberg dithering
        use_delta:   Delta frame compression
        callback:    callback(frame_index)
    """
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    # Get total frame count
    probe = subprocess.run(
        [ffmpeg, '-i', input_path, '-f', 'null', '-'],
        capture_output=True, text=True,
    )
    duration = None
    for line in probe.stderr.split('\n'):
        if 'Duration' in line:
            # Duration: 00:03:52.19
            parts = line.split('Duration:')[1].strip().split(',')[0].strip()
            h, m, s = parts.split(':')
            duration = float(h) * 3600 + float(m) * 60 + float(s)
            break

    total_frames = int(duration * fps) if duration else 0

    # Pipe: ffmpeg → raw RGB24 frames → Python
    cmd = [
        ffmpeg,
        '-i', input_path,
        '-f', 'rawvideo',
        '-pix_fmt', 'gray',
        '-vf', f'fps={fps},scale={width}:{height}:flags=lanczos',
        '-video_size', f'{width}x{height}',
        '-loglevel', 'error',
        'pipe:1'
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    frame_size = width * height

    enc = NAFEncoder(width, height, default_delay=int(1000 / fps), loop_count=0)
    prev_pages = None
    frame_idx = 0

    while True:
        raw = proc.stdout.read(frame_size)
        if len(raw) < frame_size:
            break

        # Convert grayscale bytes to PIL Image
        img = Image.frombytes('L', (width, height), raw)

        # Monochrome
        if dither:
            mono = floyd_steinberg(img, threshold)
        else:
            mono = img.point(lambda p: 255 if p >= threshold else 0).convert('1')

        if invert:
            mono = ImageOps.invert(mono.convert('L')).convert('1')

        pages = image_to_pages(mono, width, height)

        if frame_idx == 0 or not use_delta:
            enc.add_frame_rle(pages, delay=int(1000 / fps))
        else:
            enc.add_frame_delta_rle(pages, delay=int(1000 / fps))

        prev_pages = pages
        frame_idx += 1

        if callback:
            callback(frame_idx, total_frames)

    proc.terminate()

    data = enc.encode()
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'wb') as f:
        f.write(data)

    raw_total = width * enc.pages * frame_idx
    return len(data), frame_idx, raw_total


def main():
    parser = argparse.ArgumentParser(description='MP4 → NAF converter')
    parser.add_argument('input', help='Input MP4 file')
    parser.add_argument('-o', '--output', required=True, help='Output .naf file')
    parser.add_argument('-W', '--width', type=int, default=128, help='Target width (default: 128)')
    parser.add_argument('-H', '--height', type=int, default=64, help='Target height (default: 64)')
    parser.add_argument('--fps', type=int, default=12, help='Output fps (default: 12)')
    parser.add_argument('-t', '--threshold', type=int, default=128, help='Threshold 0~255 (default: 128)')
    parser.add_argument('--dither', action='store_true', default=True, help='Floyd-Steinberg dither (default: on)')
    parser.add_argument('--no-dither', dest='dither', action='store_false', help='Disable dithering')
    parser.add_argument('--no-delta', action='store_true', help='Disable delta compression')
    parser.add_argument('--no-invert', action='store_true', help='Disable invert')
    args = parser.parse_args()

    if args.width < 1 or args.height < 1:
        print("Error: width/height must be >= 1"); sys.exit(1)

    def cb(i, total):
        pct = i / total * 100 if total else 0
        print(f"\r  Frame {i}/{total or '?'} ({pct:.0f}%)", end='', flush=True)

    print(f"  Converting {args.input} ...")
    size, frames, raw = mp4_to_naf(
        args.input, args.output,
        args.width, args.height,
        fps=args.fps,
        threshold=args.threshold,
        dither=args.dither,
        use_delta=not args.no_delta,
        invert=not args.no_invert,
        callback=cb,
    )
    print()
    pct = (1 - size / raw) * 100 if raw else 0
    dur = frames / args.fps if args.fps > 0 else 0
    print(f"  {frames} frames | {args.width}x{args.height} @ {args.fps}fps | {dur:.0f}s")
    print(f"  RAW {raw:,}B → NAF {size:,}B ({pct:.1f}%)  [{size/1024:.1f} KB]")
    print(f"  Saved: {args.output}")


if __name__ == '__main__':
    main()
