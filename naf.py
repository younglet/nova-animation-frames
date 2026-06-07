"""
NAF — Nova Animation Frames decoder for MicroPython (ESP32).

Single class, auto-detects input type:

  # From file
  naf = NAF("animation.naf")

  # From memory (bytes / bytearray / memoryview / BytesIO)
  naf = NAF(b'\x4E\x41\x46\x1A...')
  naf = NAF(bytearray(...))

Usage:
  naf = NAF("icon.naf")
  print(naf.width, naf.height, naf.frame_count)

  frame = naf.get_frame(0)
  # frame[page] = bytearray(width bytes), MONO_VLSB layout

  # 2D slice → new NAFFrame
  sub = frame[0:16, 8:24]           # y, x → 16×16 region
  inverted = ~sub                    # invert
  frame.paste(inverted, x=8, y=0)   # paste back

  # Pixel access
  frame.get_pixel(x, y)             # → 0 | 1
  frame.set_pixel(x, y, 1)          # set / clear

  naf.close()
"""

import struct
import io


# ── Frame type constants ───────────────────────────────────

TYPE_RAW   = 0x00
TYPE_RLE   = 0x01
TYPE_DELTA = 0x02
TYPE_D_RLE = 0x03


class NAFFrame:
    """A single decoded NAF frame.

    Properties:
        width, height: Frame dimensions in pixels
        pages:         List of bytearrays, one per page (MONO_VLSB)

    Methods:
        invert():      Invert black/white in-place, returns self
        blit(oled, x, y): Render onto an SSD1306 display
    """

    def __init__(self, pages, width, height):
        self.pages = pages
        self.width = width
        self.height = height

    def __getitem__(self, key):
        """frame[page] → bytearray, or frame[y:y2, x:x2] → NAFFrame."""
        if isinstance(key, int):
            return self.pages[key]
        if isinstance(key, tuple):
            return self._slice(key)
        raise TypeError("NAFFrame index must be int (page) or tuple of slices (y, x)")

    def __len__(self):
        return len(self.pages)

    def __iter__(self):
        return iter(self.pages)

    # ── Pixel access ────────────────────────────────────

    def get_pixel(self, x, y):
        """Return 0 or 1 for pixel at (x, y)."""
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return 0
        page = y >> 3
        bit = y & 7
        return (self.pages[page][x] >> bit) & 1

    def set_pixel(self, x, y, val):
        """Set pixel at (x, y) to 0 or 1. Bounds are silently clipped."""
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return
        page = y >> 3
        bit = y & 7
        if val:
            self.pages[page][x] |= (1 << bit)
        else:
            self.pages[page][x] &= ~(1 << bit) & 0xFF

    # ── 2D slice ────────────────────────────────────────

    def _slice(self, key):
        """frame[y0:y1, x0:x1] → new NAFFrame."""
        if len(key) != 2:
            raise ValueError("Slice requires exactly 2 dimensions: [y, x]")
        yk, xk = key

        def _norm(s, limit):
            if isinstance(s, int):
                return s, s + 1
            start = s.start if s.start is not None else 0
            stop = s.stop if s.stop is not None else limit
            if start < 0:
                start = 0
            if stop > limit:
                stop = limit
            if stop < start:
                stop = start
            return start, stop

        y0, y1 = _norm(yk, self.height)
        x0, x1 = _norm(xk, self.width)
        new_w = x1 - x0
        new_h = y1 - y0
        new_pages_count = (new_h + 7) // 8

        if new_w == 0 or new_h == 0:
            return NAFFrame([bytearray(0) for _ in range(new_pages_count)],
                            new_w, new_h)

        bit_shift = y0 & 7  # offset within source page
        src_page0 = y0 >> 3

        new_pages = []
        for p in range(new_pages_count):
            sp = src_page0 + p
            dst = bytearray(new_w)

            if bit_shift == 0:
                # Y aligned: straight copy
                src = self.pages[sp]
                for col in range(new_w):
                    dst[col] = src[x0 + col]
            else:
                # Cross-page shift: each output byte = bits from two source pages
                src0 = self.pages[sp]
                src1 = self.pages[sp + 1] if sp + 1 < len(self.pages) else None
                inv_shift = 8 - bit_shift
                for col in range(new_w):
                    byte0 = src0[x0 + col]
                    hi = byte0 >> bit_shift
                    if src1 is not None:
                        lo = (src1[x0 + col] & ((1 << bit_shift) - 1)) << inv_shift
                    else:
                        lo = 0
                    dst[col] = (hi | lo) & 0xFF

            new_pages.append(dst)

        # Mask trailing bits on last page
        trailing = new_h & 7
        if trailing:
            mask = (1 << trailing) - 1
            last = new_pages[-1]
            for i in range(len(last)):
                last[i] &= mask

        return NAFFrame(new_pages, new_w, new_h)

    # ── Paste ───────────────────────────────────────────

    def paste(self, src, x=0, y=0):
        """Paste `src` NAFFrame into self at (x, y). Modifies self in-place.

        Pixels outside the destination are silently clipped.
        Returns self for chaining.
        """
        # Clip source region to destination bounds
        sx0 = max(0, -x)
        sy0 = max(0, -y)
        sx1 = min(src.width, self.width - x)
        sy1 = min(src.height, self.height - y)

        if sx1 <= sx0 or sy1 <= sy0:
            return self

        w = sx1 - sx0
        h = sy1 - sy0

        # Fast path: both Y-aligned to page boundaries
        if (y & 7) == 0 and (sy0 & 7) == 0:
            dst_page0 = y >> 3
            src_page0 = sy0 >> 3
            page_count = (h + 7) // 8
            for p in range(page_count):
                dp = dst_page0 + p
                sp = src_page0 + p
                if dp >= len(self.pages) or sp >= len(src.pages):
                    break
                pd = self.pages[dp]
                ps = src.pages[sp]
                for col in range(w):
                    pd[x + sx0 + col] = ps[sx0 + col]
            return self

        # General case: per-pixel
        for dy in range(h):
            for dx in range(w):
                pixel = src.get_pixel(sx0 + dx, sy0 + dy)
                self.set_pixel(x + sx0 + dx, y + sy0 + dy, pixel)
        return self

    def invert(self):
        """Flip all bits in-place (black ↔ white). Returns self."""
        for p in self.pages:
            for i in range(len(p)):
                p[i] = ~p[i] & 0xFF
        return self

    def __invert__(self):
        """~frame → new inverted NAFFrame without modifying original."""
        new_pages = [bytearray(~b & 0xFF for b in p) for p in self.pages]
        return NAFFrame(new_pages, self.width, self.height)

    def blit(self, oled, x=0, y=0):
        """Render this frame onto an SSD1306 display at (x, y).

        Requires the SSD1306 class with blit_naf_frame method
        (see ssd1306_naf.py).

        Usage:
            frame = naf[0]
            frame.blit(oled, x=10, y=0)
            oled.show()
        """
        oled.blit_naf_frame(self, x, y)

    def __repr__(self):
        # Count non-zero bytes for a quick "fill" indicator
        nz = sum(1 for p in self.pages for b in p if b != 0)
        return "NAFFrame(%dx%d, %d/%d non-zero)" % (
            self.width, self.height, nz, self.width * len(self.pages))


class NAF:
    """Read and decode .naf files or binary data."""

    def __init__(self, source):
        """
        Args:
            source: One of:
                - str:  Path to .naf file
                - bytes / bytearray / memoryview: Raw NAF binary data
                - io.BytesIO / file-like: Already-opened stream
        """
        self._own = False  # True if we opened the file, need to close it

        if isinstance(source, str):
            self._f = open(source, "rb")
            self._own = True
        elif isinstance(source, (bytes, bytearray, memoryview)):
            self._f = io.BytesIO(source)
            self._own = True
        elif hasattr(source, 'read') and hasattr(source, 'seek'):
            self._f = source
            self._own = False
        else:
            raise TypeError("NAF: expected str path, bytes, or file-like object")

        self._parse_header()
        self._prev = None       # cached previous frame for delta
        self._prev_idx = -1

    # ── Header parsing ───────────────────────────────────

    def _parse_header(self):
        f = self._f

        magic = f.read(4)
        if magic != b'NAF\x1a':
            raise ValueError("Not a valid NAF file (bad magic: %s)" % magic)

        ver = f.read(1)[0]
        if ver != 1:
            raise ValueError("Unsupported NAF version: %d" % ver)

        w = struct.unpack('>H', f.read(2))[0]
        self.width = 1024 if w == 0 else w

        h = struct.unpack('>H', f.read(2))[0]
        self.height = 1024 if h == 0 else h

        self.pages = f.read(1)[0]
        self.frame_count = struct.unpack('>H', f.read(2))[0]
        self.default_delay = struct.unpack('>H', f.read(2))[0]
        self.loop_count = f.read(1)[0]
        self._flags = f.read(1)[0]
        f.read(2)  # reserved

        # Frame offset table
        endian = '<I' if (self._flags & 1) == 0 else '>I'
        self._offsets = []
        for _ in range(self.frame_count):
            off = struct.unpack(endian, f.read(4))[0]
            self._offsets.append(off)

    # ── Frame access ─────────────────────────────────────

    def get_frame(self, index):
        """
        Decode frame `index`.
        Returns NAFFrame with .pages, .width, .height.
        Use frame[page] to access individual page bytearrays.
        """
        if index < 0 or index >= self.frame_count:
            raise IndexError("Frame %d out of range (0-%d)" %
                             (index, self.frame_count - 1))

        if self._prev is not None:
            if index == self._prev_idx:
                return NAFFrame([bytearray(p) for p in self._prev],
                                self.width, self.height)
            if index == self._prev_idx + 1:
                frame = self._decode_at(index)
                self._prev = frame
                self._prev_idx = index
                return NAFFrame([bytearray(p) for p in frame],
                                self.width, self.height)

        # Random access: reset and decode from frame 0
        self._prev = None
        self._prev_idx = -1
        for i in range(index + 1):
            frame = self._decode_at(i)
            self._prev = frame
            self._prev_idx = i
        return NAFFrame([bytearray(p) for p in frame],
                        self.width, self.height)

    def __getitem__(self, index):
        """naf[3] → NAFFrame."""
        return self.get_frame(index)

    def __len__(self):
        """len(naf) → frame_count."""
        return self.frame_count

    # ── Low-level frame decoder ──────────────────────────

    def _decode_at(self, index):
        self._f.seek(self._offsets[index])

        ftype = self._f.read(1)[0]
        delay = struct.unpack('>H', self._f.read(2))[0]
        # Page table follows immediately — no total_size field

        page_sizes = []
        for _ in range(self.pages):
            sz = struct.unpack('>H', self._f.read(2))[0]
            page_sizes.append(sz)

        is_delta = ftype in (TYPE_DELTA, TYPE_D_RLE)
        use_rle  = ftype in (TYPE_RLE,   TYPE_D_RLE)

        frame = []
        for p in range(self.pages):
            ps = page_sizes[p]

            if ps == 0x0000:
                frame.append(bytearray(self.width))
            elif ps == 0xFFFF and is_delta and self._prev is not None:
                frame.append(bytearray(self._prev[p]))
            else:
                raw = self._f.read(ps)
                if use_rle:
                    page = self._rle_decode(raw, self.width)
                else:
                    page = bytearray(raw)
                    if len(page) < self.width:
                        page.extend(b'\x00' * (self.width - len(page)))
                frame.append(page)

        # Last-page mask for non-multiple-of-8 heights
        trailing = self.height & 7
        if trailing:
            mask = (1 << trailing) - 1
            last = frame[-1]
            for i in range(len(last)):
                last[i] &= mask

        return frame

    # ── RLE Decoder ──────────────────────────────────────

    @staticmethod
    def _rle_decode(data, target_len):
        """
        Decode NAF RLE stream into `target_len` bytes.

        Control byte:
          0x00        = terminator
          0x01 - 0x7F = literal N bytes
          0x81 - 0xFF = repeat next byte (N - 0x80) times
        """
        out = bytearray()
        pos = 0
        dlen = len(data)

        while len(out) < target_len and pos < dlen:
            ctrl = data[pos]
            pos += 1

            if ctrl == 0x00 or ctrl == 0x80:
                break

            if ctrl <= 0x7F:
                count = ctrl
                end = pos + count
                if end > dlen:
                    count = dlen - pos
                out.extend(data[pos:pos + count])
                pos += count
            else:
                count = ctrl - 0x80
                if pos < dlen:
                    val = data[pos]
                    pos += 1
                    out.extend(bytes([val]) * count)

        need = target_len - len(out)
        if need > 0:
            out.extend(b'\x00' * need)
        elif len(out) > target_len:
            out = out[:target_len]

        return out

    # ── Utilities ────────────────────────────────────────

    @property
    def frames(self):
        """Alias for frame_count."""
        return self.frame_count

    def close(self):
        if self._own:
            self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __repr__(self):
        return ("NAF(%dx%d, pages=%d, frames=%d, delay=%dms)" %
                (self.width, self.height, self.pages,
                 self.frame_count, self.default_delay))


# Backward compatibility
NAFFile = NAF
