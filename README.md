# NAF — Nova Animation Frames

> Compact monochrome animation format for embedded OLED displays.  
> 1×1 ~ 256×256, multi-frame + delta + RLE. Single-file MicroPython decoder.

## File

```
naf.py    — MicroPython decoder, all-in-one, zero deps
```

## Usage

```python
from naf import NAF

# File
naf = NAF("animation.naf")

# Memory (embedded in firmware)
naf = NAF(b'\x4E\x41\x46\x1A...')

# Access
print(naf.width, naf.height, naf.frames)   # 128 64 93
frame = naf[0]                              # → NAFFrame
frame = naf.get_frame(5)

# Page-level access (MONO_VLSB)
frame[page]         # → bytearray for page N
len(frame)          # → page count
```

### Pixel & Slice

```python
# Pixel access
frame.get_pixel(x, y)               # → 0 | 1
frame.set_pixel(x, y, 1)            # set / clear

# 2D slice → new NAFFrame (copy)
icon = frame[0:16, 8:24]            # rows 0..16, cols 8..24
head = frame[y, x]                  # single row at y

# Invert (copy or in-place)
flipped = ~icon                      # new NAFFrame
icon.invert()                        # in-place, returns self

# Paste onto another frame
frame.paste(icon, x=10, y=0)         # in-place, returns self for chaining
```

## SSD1306 Blit

```python
from ssd1306_naf import SSD1306

oled = SSD1306(128, 64, i2c)
with NAF("icon.naf") as naf:
    oled.blit_naf_frame(naf[0])               # 单帧，原点
    oled.blit_naf_frame(naf[3], x=16, y=8)    # 单帧，偏移
    oled.blit_naf(naf)                        # 播放全部动画
    oled.blit_naf(naf, interval=-1)           # 静态模式，只渲染第一帧
    oled.show()
```

更完整的 SSD1306 驱动见 `usage/lib/ssd1306_naf.py`。

## Tools

See [tools/README.md](tools/README.md) for all conversion commands.

```bash
python tools/gif2naf anim.gif -o out.naf -W 128 -H 64
python tools/naf2c out.naf -o anim.h          # embed in firmware
open tools/web/demo.html                      # preview in browser
```

## Spec

See `NAF_Specification.md` for the binary protocol.
