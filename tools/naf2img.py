#!/usr/bin/env python3
"""
naf2img — Convert NAF frames to PNG or JPEG images.

CLI:  python naf2img input.naf -o out.png --frame 0 -s 4
      python naf2img input.naf -o seq.png               # all frames → seq_0000.png ...
LIB:  from naf2img import naf_to_img
      naf_to_img("in.naf", "out.png", frame=3, scale=4)
      naf_to_img("in.naf", "frames.png")                # → frames_0000.png ...
"""

import argparse, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image
from naf import NAFFile


def pages_to_image(pages, width, height):
    """NAF pages → PIL Image (MONO_VLSB → mode '1')."""
    img = Image.new('1', (width, height))
    px = img.load()
    for y in range(height):
        page = y // 8
        bit = y & 7
        for x in range(width):
            if page < len(pages) and (pages[page][x] >> bit) & 1:
                px[x, y] = 1
    return img


def _save_one(img, path, fmt, bg):
    """Save a single image as PNG or JPEG."""
    if fmt == 'jpg':
        rgb = Image.new('RGB', img.size, (255, 255, 255) if bg == 'white' else (0, 0, 0))
        rgb.paste(img, (0, 0))
        rgb.save(path, 'JPEG', quality=90)
    else:
        img.save(path, 'PNG')


def naf_to_img(input_path, output_path, frame=None, fmt='png',
               scale=1, bg='white'):
    """
    Convert NAF frame(s) to image(s).

    Args:
        input_path:  Path to .naf file
        output_path: Output path. For multi-frame, gets _NNNN suffix.
        frame:       Frame index (None = all frames)
        fmt:         'png' or 'jpg'
        scale:       Integer scale factor
        bg:          Background for JPEG ('white' or 'black')

    Returns:
        list of output file paths
    """
    saved = []

    with NAFFile(input_path) as naf:
        if frame is not None:
            pages = naf.get_frame(frame)
            img = pages_to_image(pages, naf.width, naf.height)
            if scale > 1:
                img = img.resize((naf.width * scale, naf.height * scale),
                                 Image.NEAREST)
            _save_one(img, output_path, fmt, bg)
            saved.append(output_path)
        else:
            base, ext = os.path.splitext(output_path)
            ext = '.png' if fmt == 'png' else '.jpg'
            for i in range(naf.frame_count):
                pages = naf.get_frame(i)
                img = pages_to_image(pages, naf.width, naf.height)
                if scale > 1:
                    img = img.resize((naf.width * scale, naf.height * scale),
                                     Image.NEAREST)
                fname = f"{base}_{i:04d}{ext}"
                _save_one(img, fname, fmt, bg)
                saved.append(fname)

    return saved


def main():
    parser = argparse.ArgumentParser(description='NAF → Image converter')
    parser.add_argument('input', help='Input .naf file')
    parser.add_argument('-o', '--output', required=True, help='Output image file')
    parser.add_argument('--frame', type=int, default=None, help='Frame index (default: all)')
    parser.add_argument('-f', '--format', default='png', choices=['png', 'jpg'])
    parser.add_argument('-s', '--scale', type=int, default=1, help='Scale factor')
    parser.add_argument('-b', '--bg', default='white', choices=['white', 'black'])
    args = parser.parse_args()

    files = naf_to_img(
        args.input, args.output,
        frame=args.frame, fmt=args.format,
        scale=args.scale, bg=args.bg,
    )
    for f in files:
        print(f"  Saved: {f}")
    print(f"  {len(files)} file(s)")
    in_sz = os.path.getsize(args.input)
    out_sz = sum(os.path.getsize(f) for f in files)
    print(f"  NAF → Image: {in_sz:,}B → {out_sz:,}B")


if __name__ == '__main__':
    main()
