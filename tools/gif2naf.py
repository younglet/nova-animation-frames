#!/usr/bin/env python3
"""
gif2naf — Convert animated GIF to NAF format.

CLI:  python gif2naf input.gif -o out.naf -W 128 -H 64 --dither
LIB:  from gif2naf import gif_to_naf
      gif_to_naf("in.gif", "out.naf", width=128, height=64, dither=True)
"""

import argparse, sys
from PIL import Image, ImageOps
from naf_encoder import NAFEncoder
from naf_convert import image_to_pages, floyd_steinberg
from img2naf import fit_image


def gif_to_naf(input_path, output_path, width, height,
               delay=100, threshold=128, dither=False,
               use_delta=True, loop_count=0,
               invert=True, fit='stretch', callback=None):
    """
    Convert animated GIF to NAF.

    invert: Invert black/white (default True — white→black, black→white).
    fit:    stretch | contain | cover
    """
    gif = Image.open(input_path)
    enc = NAFEncoder(width, height, default_delay=delay, loop_count=loop_count)
    prev_pages = None
    frame_idx = 0
    total = getattr(gif, 'n_frames', 0)

    try:
        while True:
            frame_img = gif.convert('RGBA')
            bg = Image.new('RGBA', gif.size, (255, 255, 255, 255))
            bg.paste(frame_img, (0, 0), frame_img)
            gray = bg.convert('L')
            gray = fit_image(gray, width, height, fit)

            mono = (floyd_steinberg(gray, threshold) if dither
                    else gray.point(lambda p: 255 if p >= threshold else 0).convert('1'))

            if invert:
                mono = ImageOps.invert(mono.convert('L')).convert('1')

            pages = image_to_pages(mono, width, height)
            dur = gif.info.get('duration', 10) * 10
            frame_delay = dur if dur > 0 else delay

            if frame_idx == 0 or not use_delta:
                enc.add_frame_rle(pages, delay=frame_delay)
            else:
                enc.add_frame_delta_rle(pages, delay=frame_delay)

            prev_pages = pages
            frame_idx += 1

            if callback:
                callback(frame_idx, total)

            gif.seek(frame_idx)
    except EOFError:
        pass
    finally:
        gif.close()

    data = enc.encode()
    with open(output_path, 'wb') as f:
        f.write(data)

    raw = width * enc.pages * frame_idx
    return len(data), frame_idx, raw


def main():
    parser = argparse.ArgumentParser(description='GIF → NAF converter')
    parser.add_argument('input', help='Input GIF file')
    parser.add_argument('-o', '--output', required=True, help='Output .naf file')
    parser.add_argument('-W', '--width', type=int, required=True, help='Target width (1~65535)')
    parser.add_argument('-H', '--height', type=int, required=True, help='Target height (1~65535)')
    parser.add_argument('-d', '--delay', type=int, default=100, help='Default frame delay ms (default: 100)')
    parser.add_argument('-t', '--threshold', type=int, default=128, help='Monochrome threshold 0~255 (default: 128)')
    parser.add_argument('--dither', action='store_true', help='Floyd-Steinberg dithering')
    parser.add_argument('--no-delta', action='store_true', help='Disable delta compression')
    parser.add_argument('--no-invert', action='store_true', help='Disable invert (keep original colors)')
    parser.add_argument('-l', '--loop', type=int, default=0, help='Loop count (0=forever)')
    parser.add_argument('--fit', choices=['stretch','contain','cover'], default='stretch',
                        help='Fit mode (default: stretch)')
    args = parser.parse_args()

    if args.width < 1 or args.height < 1:
        print("Error: width/height must be >= 1"); sys.exit(1)

    def cb(i, t):
        print(f"\r  Frame {i}...", end='' if t else '')

    size, frames, raw = gif_to_naf(
        args.input, args.output, args.width, args.height,
        delay=args.delay, threshold=args.threshold,
        dither=args.dither, use_delta=not args.no_delta,
        loop_count=args.loop,
        invert=not args.no_invert, fit=args.fit,
        callback=cb,
    )
    print()
    pct = (1 - size / raw) * 100 if raw else 0
    print(f"  {frames} frames | {args.width}x{args.height} | RAW {raw:,}B → NAF {size:,}B ({pct:.1f}%)")
    print(f"  Saved: {args.output}")


if __name__ == '__main__':
    main()
