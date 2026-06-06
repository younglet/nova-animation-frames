#!/usr/bin/env python3
"""
naf2gif — Convert NAF animation back to animated GIF.

CLI:  python naf2gif input.naf -o out.gif -s 4
LIB:  from naf2gif import naf_to_gif
      naf_to_gif("in.naf", "out.gif", scale=4, fps=10)
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


def naf_to_gif(input_path, output_path, scale=1, fps=0):
    """
    Convert NAF to animated GIF.

    Args:
        input_path:  Path to .naf file
        output_path: Path to output .gif file
        scale:       Integer scale factor (1~8)
        fps:         Override frame rate (0 = use NAF delays)
    """
    with NAFFile(input_path) as naf:
        frames = []
        durations = []

        for i in range(naf.frame_count):
            pages = naf.get_frame(i)
            img = pages_to_image(pages, naf.width, naf.height)
            if scale > 1:
                img = img.resize((naf.width * scale, naf.height * scale),
                                 Image.NEAREST)
            frames.append(img)

            dur = int(1000 / fps) if fps > 0 else naf.default_delay
            durations.append(dur)

        if frames:
            frames[0].save(
                output_path, save_all=True, append_images=frames[1:],
                duration=durations,
                loop=naf.loop_count if naf.loop_count > 0 else 0,
            )

    return len(frames), naf.width, naf.height


def main():
    parser = argparse.ArgumentParser(description='NAF → GIF converter')
    parser.add_argument('input', help='Input .naf file')
    parser.add_argument('-o', '--output', required=True, help='Output .gif file')
    parser.add_argument('--fps', type=int, default=0, help='Override frame rate (0=use NAF delays)')
    parser.add_argument('-s', '--scale', type=int, default=1, help='Scale factor 1~8')
    args = parser.parse_args()

    n, w, h = naf_to_gif(args.input, args.output, scale=args.scale, fps=args.fps)
    print(f"  {n} frames → {args.output}  ({w * args.scale}x{h * args.scale})")
    print(f"  Input: {os.path.getsize(args.input):,}B → Output: {os.path.getsize(args.output):,}B")


if __name__ == '__main__':
    main()
