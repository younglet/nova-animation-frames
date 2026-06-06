"""
NAF Convert — Shared image conversion utilities.

Used by: img2naf, gif2naf
"""

from PIL import Image


def floyd_steinberg(image, threshold=128):
    """
    Apply Floyd-Steinberg dithering to a grayscale PIL Image.
    Returns a monochrome Image (mode '1').
    """
    img = image.convert('L')
    w, h = img.size
    pixels = img.load()
    buf = [[float(pixels[x, y]) for x in range(w)] for y in range(h)]

    for y in range(h):
        for x in range(w):
            old = buf[y][x]
            new = 255.0 if old >= threshold else 0.0
            err = old - new
            buf[y][x] = new
            if x + 1 < w:
                buf[y][x + 1] += err * 7 / 16
            if y + 1 < h:
                if x - 1 >= 0:
                    buf[y + 1][x - 1] += err * 3 / 16
                buf[y + 1][x] += err * 5 / 16
                if x + 1 < w:
                    buf[y + 1][x + 1] += err * 1 / 16

    out = Image.new('1', (w, h))
    out_px = out.load()
    for y in range(h):
        for x in range(w):
            out_px[x, y] = 1 if buf[y][x] >= 128 else 0
    return out


def image_to_pages(image, width, height):
    """
    Convert a PIL Image (mode '1') to NAF page data.

    Resizes to (width, height), converts to 1-bit.
    Returns list of bytes, one per page.

    NAF page format (MONO_VLSB):
      page[p][col].bit[b] = pixel at row (p*8 + b), column (col)
    """
    img = image.resize((width, height), Image.LANCZOS)
    if img.mode != '1':
        img = img.convert('1')

    pages_count = (height + 7) // 8
    pages = [bytearray(width) for _ in range(pages_count)]

    px = img.load()
    for y in range(height):
        page_idx = y // 8
        bit = y & 7
        for x in range(width):
            if px[x, y]:
                pages[page_idx][x] |= (1 << bit)

    return [bytes(p) for p in pages]
