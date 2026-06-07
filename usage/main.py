"""
NAF + SSD1306 Usage Examples.

Wiring:
  ESP32 GPIO22 → SCL
  ESP32 GPIO21 → SDA

Place .naf files alongside main.py, or embed as bytes.
"""

from machine import I2C, Pin
from ssd1306_naf import SSD1306
from naf import NAF
import time

# ── Init ──────────────────────────────────────────────────

i2c = I2C(1, scl=Pin(22), sda=Pin(21), freq=400000)
oled = SSD1306(128, 64, i2c)


# ── Example 1: Single frame from file ────────────────────

def demo_single():
    naf = NAF("demo.naf")

    # Original position
    oled.fill(0)
    oled.blit_naf_frame(naf[0])
    oled.show()
    time.sleep(1)

    # Offset position
    oled.fill(0)
    oled.blit_naf_frame(naf[0], x=16, y=8)
    oled.show()
    time.sleep(1)

    # Bottom-right corner
    oled.fill(0)
    oled.blit_naf_frame(naf[0], x=64, y=32)
    oled.show()
    time.sleep(1)

    naf.close()


# ── Example 2: Play animation ─────────────────────────────

def demo_animate():
    naf = NAF("animation.naf")
    oled.blit_naf(naf)                  # full screen, file timing
    # oled.blit_naf(naf, x=10, y=0, interval=200)  # offset + custom interval
    naf.close()


# ── Example 3: Memory-embedded NAF ────────────────────────

def demo_memory():
    # raw = b'\x4E\x41\x46\x1A...'       # from naf2c.py
    # naf = NAF(raw)
    # oled.blit_naf_frame(naf[0])
    # oled.show()
    pass


# ── Run ───────────────────────────────────────────────────

def demo_bad_apple():
    print('loading bad_apple.naf...')
    naf = NAF('bad_apple.naf')
    print(naf.width, 'x', naf.height, 'frames:', naf.frames)
    oled.blit_naf(naf, interval=33)  # 30fps
    naf.close()


if __name__ == '__main__':
    print('loading genshin_start.naf...')
    naf = NAF('genshin_start.naf')
    print(naf.width, 'x', naf.height, 'frames:', naf.frames)
    oled.blit_naf(naf, interval=33)  # 30fps
    naf.close()
