"""
NAF Round-Trip Verification Test.

End-to-end test: encode random frames → decode → verify bit-exact match.
Tests all four frame types (RAW, RLE, DELTA, D_RLE).
"""

import sys
import random
import os

# Add parent and tools dir for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))

from naf_encoder import NAFEncoder
from naf import NAFFile


def random_pages(width, pages, seed=None):
    """Generate random page data."""
    if seed is not None:
        random.seed(seed)
    return [bytes(random.getrandbits(8) for _ in range(width))
            for _ in range(pages)]


def pages_equal(a, b):
    """Deep compare two lists of bytearrays/bytes."""
    if len(a) != len(b):
        return False
    for pa, pb in zip(a, b):
        if bytes(pa) != bytes(pb):
            return False
    return True


def mask_pages(pages, width, height):
    """Apply last-page mask for non-multiple-of-8 heights."""
    trailing = height & 7
    if trailing == 0:
        return pages
    mask = (1 << trailing) - 1
    result = [bytearray(p) for p in pages]
    last = result[-1]
    for i in range(len(last)):
        last[i] &= mask
    return [bytes(p) for p in result]


def test_roundtrip():
    """Main round-trip test."""
    print("=" * 60)
    print("  NAF Round-Trip Verification")
    print("=" * 60)

    all_passed = 0
    all_total = 0

    for width, height in [(128, 64), (64, 32), (32, 16), (1, 1), (256, 64)]:
        pages = (height + 7) // 8
        enc = NAFEncoder(width, height, default_delay=50)
        original_frames = []

        # ── Build test frames ────────────────────────────
        # Frame 0: RAW all zeros
        blank = [b'\x00' * width for _ in range(pages)]
        enc.add_frame_raw(blank)
        original_frames.append(blank)

        # Frame 1: RAW random data
        r1 = random_pages(width, pages, seed=42)
        enc.add_frame_raw(r1)
        original_frames.append(r1)

        # Frame 2: RLE all ones
        ones = [b'\xFF' * width for _ in range(pages)]
        enc.add_frame_rle(ones)
        original_frames.append(ones)

        # Frame 3: RLE checker pattern
        checker = bytes([0x55 if i % 2 == 0 else 0xAA for i in range(width)])
        enc.add_frame_rle([checker for _ in range(pages)])
        original_frames.append([checker for _ in range(pages)])

        # Frame 4: RLE random
        r2 = random_pages(width, pages, seed=123)
        enc.add_frame_rle(r2)
        original_frames.append(r2)

        # Frame 5: DELTA (vs frame 4, all same → should be tiny)
        enc.add_frame_delta(r2, delay=10)
        original_frames.append(r2)

        # Frame 6: DELTA (small change — flip first byte of page 0)
        r3 = [bytearray(p) for p in r2]
        if width > 0 and pages > 0:
            r3[0][0] ^= 0xFF
        r3 = [bytes(p) for p in r3]
        enc.add_frame_delta(r3)
        original_frames.append(r3)

        # Frame 7: D_RLE sparse data (few dots)
        sparse = [bytearray(width) for _ in range(pages)]
        for p in range(pages):
            for c in range(0, width, 7):
                sparse[p][c] = 0xFF
        sparse = [bytes(p) for p in sparse]
        enc.add_frame_delta_rle(sparse)
        original_frames.append(sparse)

        # ── Encode ───────────────────────────────────────
        data = enc.encode()
        fname = f"_test_{width}x{height}.naf"
        with open(fname, "wb") as f:
            f.write(data)

        # ── Decode & verify ──────────────────────────────
        with NAFFile(fname) as naf:
            assert naf.width == width, f"Width mismatch: {naf.width} != {width}"
            assert naf.height == height, f"Height mismatch"
            assert naf.frame_count == len(original_frames), \
                f"Frame count: {naf.frame_count} != {len(original_frames)}"

            for i, orig in enumerate(original_frames):
                decoded = naf.get_frame(i)
                # Apply trailing page mask to original for fair comparison
                masked_orig = mask_pages(orig, width, height)
                if not pages_equal(decoded, masked_orig):
                    print(f"\n  FAIL: {width}x{height} frame {i}")
                    for p in range(pages):
                        if bytes(decoded[p]) != bytes(orig[p]):
                            print(f"    Page {p} mismatch "
                                  f"(decoded[{p}][0]={decoded[p][0]:02X}, "
                                  f"orig[{p}][0]={orig[p][0]:02X})")
                    break
                all_passed += 1
            else:
                print(f"  OK {width:>3}x{height:<3}  "
                      f"{len(original_frames)} frames — ALL MATCH")

        all_total += len(original_frames)
        os.remove(fname)  # cleanup

    print(f"\n  Result: {all_passed}/{all_total} frames verified OK")
    print("=" * 60)
    return all_passed == all_total


if __name__ == '__main__':
    ok = test_roundtrip()
    sys.exit(0 if ok else 1)
