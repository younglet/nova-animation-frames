"""
NAFFrame Slice & Paste Tests.

Tests:
  - get_pixel / set_pixel
  - 2D slice: frame[y0:y1, x0:x1] → NAFFrame
  - paste: frame.paste(sub, x, y)
  - Edge cases: empty slices, single pixel, full copy, clipping
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def make_frame(w, h):
    """Create a blank NAFFrame of given size."""
    from naf import NAFFrame
    pages = (h + 7) // 8
    return NAFFrame([bytearray(w) for _ in range(pages)], w, h)


def make_checker(w, h):
    """Create a checkerboard frame (pixel on when (x+y) % 2 == 0)."""
    from naf import NAFFrame
    pages = (h + 7) // 8
    frame = NAFFrame([bytearray(w) for _ in range(pages)], w, h)
    for y in range(h):
        for x in range(w):
            if (x + y) & 1 == 0:
                frame.set_pixel(x, y, 1)
    return frame


def test_get_set_pixel():
    """Basic pixel read/write."""
    from naf import NAFFrame

    f = make_frame(16, 16)

    # Set and read back
    f.set_pixel(3, 5, 1)
    assert f.get_pixel(3, 5) == 1, "set/get pixel failed"
    assert f.get_pixel(0, 0) == 0, "blank pixel should be 0"

    # Clear
    f.set_pixel(3, 5, 0)
    assert f.get_pixel(3, 5) == 0, "clear pixel failed"

    # Out of bounds (silently ignored)
    f.set_pixel(999, 999, 1)
    assert f.get_pixel(999, 999) == 0, "OOB should return 0"

    print("  OK  get_pixel / set_pixel")


def test_slice_full_frame():
    """Slice entire frame should return identical frame."""
    f = make_checker(32, 24)
    g = f[0:24, 0:32]

    assert g.width == 32
    assert g.height == 24
    assert len(g.pages) == 3  # 24 / 8 = 3

    for y in range(24):
        for x in range(32):
            if f.get_pixel(x, y) != g.get_pixel(x, y):
                print(f"  FAIL full slice at ({x},{y}): {f.get_pixel(x,y)} != {g.get_pixel(x,y)}")
                return False

    print("  OK  full frame slice")


def test_slice_sub_region_aligned():
    """Slice a page-aligned sub-region (Y % 8 == 0)."""
    f = make_checker(32, 24)  # 3 pages
    # Slice middle page: rows 8..15
    g = f[8:16, 4:20]

    assert g.width == 16
    assert g.height == 8
    assert len(g.pages) == 1

    for y in range(8):
        for x in range(16):
            expected = f.get_pixel(4 + x, 8 + y)
            actual = g.get_pixel(x, y)
            if expected != actual:
                print(f"  FAIL aligned slice at ({x},{y})")
                return False

    print("  OK  aligned sub-region slice (Y%8==0)")


def test_slice_sub_region_unaligned_y():
    """Slice where Y is not page-aligned."""
    f = make_checker(32, 24)
    # Slice rows 5..14 (crosses page boundary at row 8)
    g = f[5:15, 2:18]

    assert g.width == 16
    assert g.height == 10
    assert len(g.pages) == 2  # ceil(10/8) = 2

    for y in range(10):
        for x in range(16):
            expected = f.get_pixel(2 + x, 5 + y)
            actual = g.get_pixel(x, y)
            if expected != actual:
                print(f"  FAIL unaligned slice at ({x},{y}): "
                      f"expected {expected}, got {actual}")
                return False

    print("  OK  unaligned Y slice (rows 5..14)")


def test_slice_all_combinations():
    """Brute-force: slice every possible sub-rect of a small frame."""
    f = make_checker(16, 16)

    for y0 in range(0, 16, 2):
        for y1 in range(y0 + 1, 17, 3):
            for x0 in range(0, 16, 3):
                for x1 in range(x0 + 1, 17, 4):
                    g = f[y0:y1, x0:x1]
                    w = x1 - x0
                    h = y1 - y0
                    if g.width != w or g.height != h:
                        print(f"  FAIL size {y0}:{y1},{x0}:{x1}: "
                              f"got {g.width}x{g.height}, expected {w}x{h}")
                        return False
                    for y in range(h):
                        for x in range(w):
                            exp = f.get_pixel(x0 + x, y0 + y)
                            act = g.get_pixel(x, y)
                            if exp != act:
                                print(f"  FAIL pixel mismatch at "
                                      f"slice [{y0}:{y1},{x0}:{x1}] "
                                      f"local ({x},{y}): {exp} != {act}")
                                return False
    print("  OK  exhaustive sub-rectangle slices (16×16)")


def test_single_pixel_slice():
    """Slice a 1×1 region."""
    f = make_checker(16, 16)
    f.set_pixel(7, 11, 1)

    g = f[11:12, 7:8]
    assert g.width == 1
    assert g.height == 1
    assert g.get_pixel(0, 0) == 1

    g2 = f[11:12, 6:7]
    assert g2.get_pixel(0, 0) == f.get_pixel(6, 11)

    print("  OK  single pixel slice")


def test_empty_slice():
    """Empty slices return zero-area frames."""
    f = make_checker(16, 16)

    g = f[5:5, 0:8]
    assert g.width == 8 and g.height == 0

    g = f[0:8, 4:4]
    assert g.width == 0 and g.height == 8

    # Both zero
    g = f[5:5, 4:4]
    assert g.width == 0 and g.height == 0

    print("  OK  empty slice")


def test_oob_slice():
    """Out-of-bounds slice clamped to frame bounds."""
    f = make_checker(16, 16)

    g = f[-5:10, -3:20]
    assert g.width == 16  # clamped x: -3→0, 20→16
    assert g.height == 10  # clamped y: -5→0, 10→10

    # Content should match frame top-left 16×10
    for y in range(10):
        for x in range(16):
            assert g.get_pixel(x, y) == f.get_pixel(x, y)

    print("  OK  out-of-bounds slice clamped")


def test_paste_page_aligned():
    """Paste a page-aligned sub-frame back."""
    f = make_frame(32, 32)
    sub = make_checker(16, 16)

    f.paste(sub, x=4, y=8)

    # Verify pixels in pasted region
    for y in range(16):
        for x in range(16):
            expected = sub.get_pixel(x, y)
            actual = f.get_pixel(4 + x, 8 + y)
            if expected != actual:
                print(f"  FAIL paste aligned at ({x},{y})")
                return False

    # Verify pixels outside are still zero
    for y in range(32):
        for x in range(32):
            inside = (4 <= x < 20) and (8 <= y < 24)
            if not inside:
                assert f.get_pixel(x, y) == 0, f"unaltered pixel ({x},{y}) changed"

    print("  OK  paste page-aligned")


def test_paste_unaligned():
    """Paste with non-aligned Y offset."""
    f = make_frame(32, 32)
    sub = make_checker(16, 16)

    f.paste(sub, x=2, y=5)

    for y in range(16):
        for x in range(16):
            expected = sub.get_pixel(x, y)
            actual = f.get_pixel(2 + x, 5 + y)
            if expected != actual:
                print(f"  FAIL paste unaligned at ({x},{y}): "
                      f"expected {expected}, got {actual}")
                return False

    print("  OK  paste Y-unaligned")


def test_paste_clip():
    """Paste that extends beyond destination should clip."""
    f = make_frame(16, 16)
    sub = make_checker(8, 8)

    # Paste partly off the right and bottom edges
    f.paste(sub, x=12, y=12)

    # Visible region: x=12..15 (4 cols), y=12..15 (4 rows) of sub's x=0..3, y=0..3
    for y in range(4):
        for x in range(4):
            expected = sub.get_pixel(x, y)
            actual = f.get_pixel(12 + x, 12 + y)
            if expected != actual:
                print(f"  FAIL paste clip at ({12 + x},{12 + y})")
                return False

    # Outside should be zero
    assert f.get_pixel(0, 0) == 0

    print("  OK  paste clipping")


def test_paste_negative_offset():
    """Paste with source partly off the left/top edge."""
    f = make_frame(16, 16)
    sub = make_checker(8, 8)

    f.paste(sub, x=-4, y=-2)

    # Only bottom-right 4×6 of sub should be visible
    for y in range(6):
        for x in range(4):
            expected = sub.get_pixel(4 + x, 2 + y)
            actual = f.get_pixel(x, y)
            if expected != actual:
                print(f"  FAIL paste negative at ({x},{y})")
                return False

    print("  OK  paste negative offset")


def test_paste_chaining():
    """paste returns self for chaining."""
    f = make_frame(16, 16)
    sub1 = make_checker(8, 8)
    sub2 = make_frame(8, 8)
    sub2.set_pixel(0, 0, 1)
    sub2.set_pixel(7, 7, 1)

    f.paste(sub1, x=0, y=0).paste(sub2, x=8, y=8)

    assert f.get_pixel(0, 0) == 1  # from sub1 (checker)
    assert f.get_pixel(8, 8) == 1  # from sub2
    assert f.get_pixel(15, 15) == 1  # from sub2
    assert f.get_pixel(1, 0) == 0  # checker pattern

    print("  OK  paste chaining")


def test_slice_then_paste_roundtrip():
    """Slice a region, invert it, paste back."""
    f = make_checker(32, 24)

    # Slice a region
    region = f[4:20, 8:24]  # 16×16
    inverted = ~region

    # Paste inverted back
    f.paste(inverted, x=8, y=4)

    # Verify: pixels in region should be flipped
    for y in range(24):
        for x in range(32):
            inside = (8 <= x < 24) and (4 <= y < 20)
            expected_orig = make_checker(32, 24).get_pixel(x, y)
            if inside:
                assert f.get_pixel(x, y) != expected_orig, \
                    f"Pixel ({x},{y}) should be inverted inside region"
            else:
                assert f.get_pixel(x, y) == expected_orig, \
                    f"Pixel ({x},{y}) should be unchanged outside region"

    print("  OK  slice → invert → paste roundtrip")


def test_dimensions_odd():
    """Frames with odd dimensions (height not multiple of 8)."""
    f = make_checker(10, 13)  # 13 rows → 2 pages, last page has 5 effective rows

    # Full slice
    g = f[0:13, 0:10]
    assert g.width == 10 and g.height == 13

    for y in range(13):
        for x in range(10):
            assert g.get_pixel(x, y) == f.get_pixel(x, y), \
                f"Mismatch at ({x},{y})"

    # Sub-slice crossing last page boundary
    h = f[5:13, 2:8]
    for y in range(8):
        for x in range(6):
            assert h.get_pixel(x, y) == f.get_pixel(2 + x, 5 + y)

    print("  OK  odd dimensions (10×13)")


def test_large_dimension():
    """256×64 stress test (typical OLED width)."""
    f = make_checker(256, 64)

    # Slice center
    g = f[16:48, 32:224]  # 32×192
    assert g.width == 192
    assert g.height == 32

    # Spot-check pixels
    for y in [0, 15, 31]:
        for x in [0, 100, 191]:
            exp = f.get_pixel(32 + x, 16 + y)
            act = g.get_pixel(x, y)
            assert exp == act, f"Large slice mismatch at ({x},{y})"

    print("  OK  large frame (256×64)")


# ── Run ─────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  NAFFrame Slice & Paste Tests")
    print("=" * 60)

    tests = [
        test_get_set_pixel,
        test_slice_full_frame,
        test_slice_sub_region_aligned,
        test_slice_sub_region_unaligned_y,
        test_slice_all_combinations,
        test_single_pixel_slice,
        test_empty_slice,
        test_oob_slice,
        test_paste_page_aligned,
        test_paste_unaligned,
        test_paste_clip,
        test_paste_negative_offset,
        test_paste_chaining,
        test_slice_then_paste_roundtrip,
        test_dimensions_odd,
        test_large_dimension,
    ]

    passed = 0
    failed = []

    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed.append((t.__name__, str(e)))
            print(f"  FAIL {t.__name__}: {e}")

    print(f"\n  Result: {passed}/{len(tests)} passed")
    if failed:
        print("  Failures:")
        for name, err in failed:
            print(f"    - {name}: {err}")
    print("=" * 60)
    return len(failed) == 0


if __name__ == '__main__':
    ok = main()
    sys.exit(0 if ok else 1)
