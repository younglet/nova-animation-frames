#!/usr/bin/env python3
"""
img2naf — Convert a single image to NAF format.

CLI:  python img2naf icon.png -o icon.naf -W 32 -H 32 --dither
LIB:  from img2naf import img_to_naf
      img_to_naf("icon.png", "icon.naf", width=32, height=32, dither=True)
"""

import argparse, sys
from PIL import Image, ImageOps
from naf_encoder import NAFEncoder
from naf_convert import image_to_pages, floyd_steinberg


def img_to_naf(input_path, output_path, width, height,
               threshold=128, dither=False, delay=100,
               invert=True):
    """
    Convert a single image (PNG/JPG/BMP) to NAF.

    Args:
        input_path:  Path to image file
        output_path: Path to output .naf file
        width, height: Target size (1~65535)
        threshold:   Monochrome threshold (0~255)
        dither:      Floyd-Steinberg dithering
        delay:       Frame delay in ms
    """
    img = Image.open(input_path).convert('L')

    mono = (floyd_steinberg(img, threshold) if dither
            else img.point(lambda p: 255 if p >= threshold else 0).convert('1'))

    if invert:
        mono = ImageOps.invert(mono.convert('L')).convert('1')

    pages = image_to_pages(mono, width, height)

    enc = NAFEncoder(width, height, default_delay=delay, loop_count=1)
    enc.add_frame_rle(pages, delay=delay)

    data = enc.encode()
    with open(output_path, 'wb') as f:
        f.write(data)

    raw = width * enc.pages
    return len(data), raw


def main():
    parser = argparse.ArgumentParser(description='Image → NAF converter')
    parser.add_argument('input', help='Input image (PNG, JPG, BMP, etc.)')
    parser.add_argument('-o', '--output', required=True, help='Output .naf file')
    parser.add_argument('-W', '--width', type=int, required=True, help='Target width (1~65535)')
    parser.add_argument('-H', '--height', type=int, required=True, help='Target height (1~65535)')
    parser.add_argument('-t', '--threshold', type=int, default=128, help='Monochrome threshold 0~255 (default: 128)')
    parser.add_argument('--dither', action='store_true', help='Floyd-Steinberg dithering')
    parser.add_argument('--no-invert', action='store_true', help='Disable invert')
    parser.add_argument('--delay', type=int, default=100, help='Frame delay ms (default: 100)')
    args = parser.parse_args()

    if args.width < 1 or args.height < 1:
        print("Error: width/height must be >= 1"); sys.exit(1)

    size, raw = img_to_naf(
        args.input, args.output, args.width, args.height,
        threshold=args.threshold, dither=args.dither, delay=args.delay,
        invert=not args.no_invert,
    )
    pct = (1 - size / raw) * 100 if raw else 0
    print(f"  1 frame | {args.width}x{args.height} | RAW {raw}B → NAF {size}B ({pct:.1f}%)")
    print(f"  Saved: {args.output}")


if __name__ == '__main__':
    main()
