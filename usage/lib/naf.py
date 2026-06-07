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

    def __getitem__(self, page):
        """frame[page] → bytearray for that page."""
        return self.pages[page]

    def __len__(self):
        return len(self.pages)

    def __iter__(self):
        return iter(self.pages)

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
