"""
NAF Encoder — Nova Animation Frames encoder (PC-side Python).

Creates .naf files from raw frame data (page-organized byte arrays).
Frames can be added as RAW, RLE, DELTA, or DELTA+RLE.

Usage:
    from naf_encoder import NAFEncoder

    enc = NAFEncoder(128, 64, default_delay=100, loop_count=0)

    # Add frames (each frame is a list of `pages` bytearrays/bytes)
    enc.add_frame_rle([page0, page1, ..., page7])
    enc.add_frame_delta_rle([page0, ...])  # auto-detects unchanged pages

    # Save
    with open("output.naf", "wb") as f:
        f.write(enc.encode())

    # Or get stats
    enc.print_stats()
"""

import struct
from math import ceil
from typing import List, Optional, Tuple


class NAFEncoder:
    """Nova Animation Frames encoder."""

    MAGIC = b'NAF\x1a'
    VERSION = 1

    TYPE_RAW   = 0x00  # Uncompressed
    TYPE_RLE   = 0x01  # RLE compressed
    TYPE_DELTA = 0x02  # Delta from previous frame (raw pages)
    TYPE_D_RLE = 0x03  # Delta from previous frame + RLE

    MAX_REPEAT = 127   # Max bytes in a repeat run
    MAX_LITERAL = 127  # Max bytes in a literal run
    MIN_REPEAT = 3     # Minimum consecutive bytes to trigger repeat run

    def __init__(self, width: int, height: int,
                 default_delay: int = 100, loop_count: int = 0):
        """
        Args:
            width, height: 1~65535 pixels (0x0000 = 1024)
            default_delay: ms between frames (0 = as fast as possible)
            loop_count: 0=infinite loop, N=play N times
        """
        if width < 1 or height < 1:
            raise ValueError("Size must be at least 1×1")

        self.width = width
        self.height = height
        self.pages = ceil(height / 8)
        self.default_delay = default_delay
        self.loop_count = loop_count

        # _frames: list of (type, delay, [page0_data, ...])
        self._frames: List[Tuple[int, int, List[bytes]]] = []

        # Stats
        self._raw_total = 0      # total bytes if all RAW
        self._encoded_total = 0  # actual encoded bytes (data only)
        self._stats_per_frame: List[dict] = []

    # ── Public API ─────────────────────────────────────────

    def add_frame_raw(self, pages: List[bytes], delay: int = 0):
        """Add a RAW (uncompressed) frame."""
        self._validate_pages(pages)
        self._frames.append((self.TYPE_RAW, delay, [bytes(p) for p in pages]))

    def add_frame_rle(self, pages: List[bytes], delay: int = 0):
        """Add an RLE-compressed frame."""
        self._validate_pages(pages)
        self._frames.append((self.TYPE_RLE, delay, [bytes(p) for p in pages]))

    def add_frame_delta(self, pages: List[bytes], delay: int = 0):
        """Add a DELTA frame (only changed pages vs previous frame, raw)."""
        self._validate_pages(pages)
        self._frames.append((self.TYPE_DELTA, delay, [bytes(p) for p in pages]))

    def add_frame_delta_rle(self, pages: List[bytes], delay: int = 0):
        """Add a DELTA+RLE frame (changed pages RLE-compressed)."""
        self._validate_pages(pages)
        self._frames.append((self.TYPE_D_RLE, delay, [bytes(p) for p in pages]))

    def encode(self) -> bytes:
        """Encode all frames and return the complete .naf file as bytes."""
        buf = bytearray()

        # ── Header (18 bytes) ────────────────────────────
        wb = self.width if self.width < 1024 else 0x0000
        hb = self.height if self.height < 1024 else 0x0000
        wb = 0x0000 if self.width == 1024 else self.width
        hb = 0x0000 if self.height == 1024 else self.height

        buf.extend(self.MAGIC)                              # 0x00: 4B magic
        buf.append(self.VERSION)                            # 0x04: 1B version
        buf.extend(struct.pack('>H', wb))                   # 0x05: 2B width  (0=1024)
        buf.extend(struct.pack('>H', hb))                   # 0x07: 2B height (0=1024)
        buf.append(self.pages)                              # 0x09: 1B pages
        buf.extend(struct.pack('>H', len(self._frames)))    # 0x0A: 2B frame count
        buf.extend(struct.pack('>H', self.default_delay))   # 0x0C: 2B default delay
        buf.append(self.loop_count)                         # 0x0E: 1B loop count
        buf.append(0x00)                                    # 0x0F: 1B flags (LE offsets)
        buf.extend(b'\x00\x00')                             # 0x10: 2B reserved

        # ── Placeholder for offset table ────────────────
        offset_table_pos = len(buf)
        buf.extend(b'\x00\x00\x00\x00' * len(self._frames))

        # ── Encode frames ───────────────────────────────
        offsets = []
        prev_pages = None

        for idx, (ftype, delay, pages) in enumerate(self._frames):
            offsets.append(len(buf))

            # Encode pages → (encoded_data_blob, page_sizes_list)
            encoded_blob, page_sizes = self._encode_pages(
                pages, prev_pages, ftype
            )

            frame_data_size = 2 * self.pages + len(encoded_blob)

            # Frame header: type(1) + delay(2) = 3 bytes
            buf.append(ftype)
            buf.extend(struct.pack('>H', delay))

            # Page table (2 bytes per page)
            for ps in page_sizes:
                buf.extend(struct.pack('>H', ps))

            # Page data blob
            buf.extend(encoded_blob)

            # Track stats
            raw_sz = self.width * self.pages
            self._raw_total += raw_sz
            self._encoded_total += frame_data_size
            self._stats_per_frame.append({
                'frame': idx,
                'type': ['RAW', 'RLE', 'DELTA', 'D_RLE'][ftype],
                'raw_bytes': raw_sz,
                'encoded_bytes': frame_data_size,
                'ratio': f"{(1 - frame_data_size / raw_sz) * 100:.1f}%",
            })

            # Update previous frame for delta
            if ftype >= self.TYPE_DELTA:
                prev_pages = pages
            elif prev_pages is None:
                prev_pages = pages  # first frame becomes baseline

        # ── Write offset table ───────────────────────────
        for i, off in enumerate(offsets):
            struct.pack_into('<I', buf, offset_table_pos + i * 4, off)

        return bytes(buf)

    def print_stats(self):
        """Print compression statistics."""
        print(f"\n{'='*60}")
        print(f"  NAF Encode Summary")
        print(f"  Size: {self.width}×{self.height} | Pages: {self.pages}")
        print(f"  Frames: {len(self._frames)} | Default Delay: {self.default_delay}ms")
        print(f"{'='*60}")
        print(f"  {'Frame':<6} {'Type':<7} {'Raw(B)':<9} {'Enc(B)':<9} {'Saved'}")
        print(f"  {'-'*45}")

        for s in self._stats_per_frame:
            print(f"  {s['frame']:<6} {s['type']:<7} "
                  f"{s['raw_bytes']:<9} {s['encoded_bytes']:<9} {s['ratio']}")

        total_raw = self._raw_total
        total_enc = self._encoded_total
        overall = (1 - total_enc / max(total_raw, 1)) * 100
        print(f"  {'-'*45}")
        print(f"  {'TOTAL':<6} {'':<7} {total_raw:<9} {total_enc:<9} "
              f"{overall:.1f}%")
        print(f"{'='*60}\n")

    # ── Internal ──────────────────────────────────────────

    def _validate_pages(self, pages):
        if len(pages) != self.pages:
            raise ValueError(
                f"Expected {self.pages} pages, got {len(pages)}"
            )
        for i, p in enumerate(pages):
            if len(p) != self.width:
                raise ValueError(
                    f"Page {i}: expected {self.width} bytes, got {len(p)}"
                )

    def _rle_encode_page(self, data: bytes) -> bytes:
        """RLE-encode a single page (width bytes) into NAF RLE format."""
        out = bytearray()
        i = 0
        n = len(data)

        while i < n:
            # ── Find repeat run ──────────────────────────
            run_start = i
            while (i + 1 < n and
                   data[i + 1] == data[run_start] and
                   (i + 1 - run_start) < self.MAX_REPEAT):
                i += 1
            run_len = i - run_start + 1

            if run_len >= self.MIN_REPEAT:
                # Emit any pending literal run first
                # (handled below - we do literal then repeat)
                pass

            # ── Decide: literal or repeat ────────────────
            if run_len >= self.MIN_REPEAT:
                # Flush pending literal
                if run_start > 0:
                    lit_end = run_start
                    # Actually, we need to track literal from last emitted position
                    pass
                # Emit repeat run
                out.append(0x80 + run_len)
                out.append(data[run_start])
                i = run_start + run_len
            else:
                # Collect literal run
                lit_start = run_start
                while i < n:
                    # Look ahead for a repeat
                    j = i
                    while (j + 1 < n and
                           data[j + 1] == data[i] and
                           (j + 1 - i) < self.MAX_REPEAT):
                        j += 1
                    ahead_run = j - i + 1
                    if ahead_run >= self.MIN_REPEAT:
                        break
                    i = j + 1
                    if (i - lit_start) >= self.MAX_LITERAL:
                        break

                lit_len = i - lit_start
                if lit_len > 0:
                    out.append(lit_len)  # 1~127
                    out.extend(data[lit_start:i])
                # i is now at start of next repeat (or end)

        # Simpler implementation:
        # I'll rewrite this more cleanly below
        return bytes(out)

    def _rle_encode_page_v2(self, data: bytes) -> bytes:
        """Cleaner RLE encoder for a single page."""
        out = bytearray()
        i = 0
        n = len(data)

        while i < n:
            # ── Measure repeat run length at position i ──
            run_len = 1
            while (i + run_len < n and
                   data[i + run_len] == data[i] and
                   run_len < self.MAX_REPEAT):
                run_len += 1

            if run_len >= self.MIN_REPEAT:
                # Emit repeat
                out.append(0x80 + run_len)
                out.append(data[i])
                i += run_len
            else:
                # Collect literal run
                lit_start = i
                i += 1
                while i < n and (i - lit_start) < self.MAX_LITERAL:
                    # Look ahead
                    ahead = 1
                    while (i + ahead < n and
                           data[i + ahead] == data[i] and
                           ahead < self.MAX_REPEAT):
                        ahead += 1
                    if ahead >= self.MIN_REPEAT:
                        break
                    i += 1

                lit_len = i - lit_start
                out.append(lit_len)
                out.extend(data[lit_start:i])

        out.append(0x00)  # terminator
        return bytes(out)

    # Use the cleaner version
    _rle_encode_page = _rle_encode_page_v2

    def _encode_pages(self, pages: List[bytes],
                      prev_pages: Optional[List[bytes]],
                      frame_type: int) -> Tuple[bytes, List[int]]:
        """
        Encode pages into (blob, page_sizes).
        Returns consecutive encoded page data blob + list of sizes.
        """
        parts = []
        page_sizes = []
        is_delta = frame_type in (self.TYPE_DELTA, self.TYPE_D_RLE)
        use_rle = frame_type in (self.TYPE_RLE, self.TYPE_D_RLE)

        for i, data in enumerate(pages):
            # ── Check all-zero ───────────────────────────
            if self._is_all_zero(data):
                page_sizes.append(0x0000)
                continue

            # ── Check delta same-as-previous ─────────────
            if is_delta and prev_pages is not None and data == prev_pages[i]:
                page_sizes.append(0xFFFF)
                continue

            # ── Encode ───────────────────────────────────
            if use_rle:
                encoded = self._rle_encode_page(data)
            else:
                encoded = data

            page_sizes.append(len(encoded))
            parts.append(encoded)

        return b''.join(parts), page_sizes

    @staticmethod
    def _is_all_zero(data: bytes) -> bool:
        """Fast check if all bytes are 0x00."""
        # For Python, check first and last byte to short-circuit
        if not data:
            return True
        # Use a simple scan for small pages, count zeros for larger
        return data.count(0) == len(data)
        # Even faster: not any(data) — works because 0 is falsy
        # return not any(data)


# ── Quick test / demo ────────────────────────────────────────


def _demo():
    """Demonstrate NAF encoding with various frame types."""
    import random

    print("═" * 60)
    print("  NAF Encoder — Demo")
    print("═" * 60)

    # ── Create encoder for 128×64 ─────────────────────────
    enc = NAFEncoder(128, 64, default_delay=100, loop_count=0)

    blank = b'\x00' * 128
    full = b'\xFF' * 128
    checker = bytes([0x55 if i % 2 == 0 else 0xAA for i in range(128)])
    random_page = bytes(random.getrandbits(8) for _ in range(128))

    # Frame 0: full blank → should compress to almost nothing
    enc.add_frame_rle([blank] * 8, delay=500)

    # Frame 1: text-like content (sparse)
    text_pages = [blank] * 8
    text_pages[2] = bytes([0xFF if i < 80 and i % 6 == 0 else 0x00 for i in range(128)])
    text_pages[3] = bytes([0xFF if i < 80 and i % 6 == 0 else 0x00 for i in range(128)])
    enc.add_frame_rle(text_pages, delay=1000)

    # Frame 2: full white
    enc.add_frame_rle([full] * 8, delay=200)

    # Frame 3: checker pattern → medium compressibility
    enc.add_frame_rle([checker] * 8, delay=200)

    # Frame 4: random noise → worst case (will expand slightly)
    enc.add_frame_rle([bytes(random.getrandbits(8) for _ in range(128)) for _ in range(8)], delay=50)

    # Frame 5-10: delta animation — blinking cursor
    base_pages = [blank] * 8
    base_pages[3] = bytes([0xFF if i < 16 else 0x00 for i in range(128)])
    enc.add_frame_rle(base_pages, delay=500)  # keyframe

    for _ in range(5):
        alt = [bytes(p) for p in base_pages]
        alt[3] = bytes([0x00 if i < 16 else base_pages[3][i] for i in range(128)])
        enc.add_frame_delta_rle(alt, delay=500)
        alt2 = [bytes(p) for p in base_pages]
        enc.add_frame_delta_rle(alt2, delay=500)

    # ── Encode ────────────────────────────────────────────
    data = enc.encode()

    print(f"\n  Total .naf file size: {len(data)} bytes")
    print(f"  Frames: {enc._frames.__len__()}")
    enc.print_stats()

    # Save to file
    with open("demo.naf", "wb") as f:
        f.write(data)
    print(f"  Saved to: demo.naf\n")

    return data


if __name__ == '__main__':
    _demo()
