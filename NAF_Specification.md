# NAF — Nova Animation Frames v1.0

> Compact monochrome animation format for embedded displays.  
> 1×1 ~ 65535×65535, multi-frame + delta + RLE.

## File Layout

```
┌────────┬──────┬──────────────────────────────────────────┐
│ Offset │ Size │ Description                              │
├────────┼──────┼──────────────────────────────────────────┤
│ 0x00   │ 4    │ Magic: "NAF\x1A"                         │
│ 0x04   │ 1    │ Version: 0x01                            │
│ 0x05   │ 2    │ Width  (BE, 0x0000 = 1024)               │
│ 0x07   │ 2    │ Height (BE, 0x0000 = 1024)               │
│ 0x09   │ 1    │ Pages = ceil(Height / 8)                 │
│ 0x0A   │ 2    │ Frame Count (BE, 1~65535)                │
│ 0x0C   │ 2    │ Default Delay (BE, ms)                   │
│ 0x0E   │ 1    │ Loop Count (0 = forever)                 │
│ 0x0F   │ 1    │ Flags (bit0: 0=LE offsets, 1=BE)         │
│ 0x10   │ 2    │ Reserved                                 │
├────────┼──────┼──────────────────────────────────────────┤
│ 0x12   │ 4×N  │ Frame Offset Table (32-bit)              │
├────────┼──────┼──────────────────────────────────────────┤
│ var    │ var  │ Frame data ...                           │
└────────┴──────┴──────────────────────────────────────────┘
```

## Frame Layout

```
┌────────┬──────┬──────────────────────────────────────────┐
│ Offset │ Size │ Description                              │
├────────┼──────┼──────────────────────────────────────────┤
│ 0x00   │ 1    │ Frame Type (0=RAW, 1=RLE, 2=DELTA, 3=D_RLE) │
│ 0x01   │ 2    │ Delay Override (BE ms, 0=use default)    │
│ 0x03   │ 2×P  │ Page Table                               │
├────────┼──────┼──────────────────────────────────────────┤
│ var    │ var  │ Page data                                │
└────────┴──────┴──────────────────────────────────────────┘
```

## Page Table

| Value | Meaning |
|-------|---------|
| 0x0000 | All-zero page (no data) |
| 0xFFFF | Same as previous frame (Delta only) |
| other | Encoded page size in bytes |

## RLE Encoding

| Control byte | Meaning |
|-------------|---------|
| 0x00 | Terminator |
| 0x01–0x7F | Literal: next N bytes raw |
| 0x80 | Reserved |
| 0x81–0xFF | Repeat: next byte repeated (N−0x80) times |

## Size Examples (128×64)

| Type | Size | Compression |
|------|------|-------------|
| RAW | 1046 B | — |
| RLE blank | 24 B | 97.7% |
| RLE text | ~120 B | 88.5% |

## Delta (30-frame animation, 128×64)

| Scene | RAW | Delta+RLE |
|-------|-----|-----------|
| Blinking cursor | 31,380 B | ~2,200 B |
| Scrolling digits | 31,380 B | ~6,000 B |
