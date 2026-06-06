"""
SSD1306 OLED driver with NAF blit support.

Based on the official MicroPython SSD1306 driver, with two added methods:
  blit_naf_frame(frame, x, y)   — render a single decoded NAF frame
  blit_naf(naf, x, y, delay)    — play NAF animation with auto-timing

Usage:
    from machine import I2C, Pin
    from ssd1306_naf import SSD1306
    from naf import NAF

    i2c = I2C(1, scl=Pin(22), sda=Pin(21))
    oled = SSD1306(128, 64, i2c)

    naf = NAF("animation.naf")

    # Single frame, placed at (10, 0)
    oled.blit_naf_frame(naf[0], 10, 0)

    # Play full animation at (0, 0), use NAF file's timing
    oled.blit_naf(naf)

    # Play at offset with custom delay (overrides file timing)
    oled.blit_naf(naf, x=16, y=8, delay=200)
"""

from micropython import const
import framebuf
import time


# ── SSD1306 register definitions ────────────────────────────

SET_CONTRAST      = const(0x81)
SET_ENTIRE_ON     = const(0xA4)
SET_NORM_INV      = const(0xA6)
SET_DISP          = const(0xAE)
SET_MEM_ADDR      = const(0x20)
SET_COL_ADDR      = const(0x21)
SET_PAGE_ADDR     = const(0x22)
SET_DISP_START_LINE = const(0x40)
SET_SEG_REMAP     = const(0xA0)
SET_MUX_RATIO     = const(0xA8)
SET_IREF_SELECT   = const(0xAD)
SET_COM_OUT_DIR   = const(0xC0)
SET_DISP_OFFSET   = const(0xD3)
SET_COM_PIN_CFG   = const(0xDA)
SET_DISP_CLK_DIV  = const(0xD5)
SET_PRECHARGE     = const(0xD9)
SET_VCOM_DESEL    = const(0xDB)
SET_CHARGE_PUMP   = const(0x8D)


class SSD1306(framebuf.FrameBuffer):
    """SSD1306 OLED driver with NAF blit support."""

    def __init__(self, width, height, i2c, addr=0x3C, external_vcc=False):
        self.width = width
        self.height = height
        self.external_vcc = external_vcc
        self.pages = self.height // 8
        self.buffer = bytearray(self.pages * self.width)
        super().__init__(self.buffer, self.width, self.height, framebuf.MONO_VLSB)

        self.i2c = i2c
        self.addr = addr
        self.temp = bytearray(2)
        self.write_list = [b"\x40", None]

        self.init_display()

    # ── Low-level I²C ─────────────────────────────────────

    def write_cmd(self, cmd):
        self.temp[0] = 0x80
        self.temp[1] = cmd
        self.i2c.writeto(self.addr, self.temp)

    def write_data(self, buf):
        self.write_list[1] = buf
        self.i2c.writevto(self.addr, self.write_list)

    # ── Display init ──────────────────────────────────────

    def init_display(self):
        for cmd in (
            SET_DISP,
            SET_MEM_ADDR, 0x00,
            SET_DISP_START_LINE,
            SET_SEG_REMAP | 0x01,
            SET_MUX_RATIO, self.height - 1,
            SET_COM_OUT_DIR | 0x08,
            SET_DISP_OFFSET, 0x00,
            SET_COM_PIN_CFG, 0x02 if self.width > 2 * self.height else 0x12,
            SET_DISP_CLK_DIV, 0x80,
            SET_PRECHARGE, 0x22 if self.external_vcc else 0xF1,
            SET_VCOM_DESEL, 0x30,
            SET_CONTRAST, 0xFF,
            SET_ENTIRE_ON,
            SET_NORM_INV,
            SET_IREF_SELECT, 0x30,
            SET_CHARGE_PUMP, 0x10 if self.external_vcc else 0x14,
            SET_DISP | 0x01,
        ):
            self.write_cmd(cmd)
        self.fill(0)
        self.show()

    def poweroff(self):
        self.write_cmd(SET_DISP)

    def poweron(self):
        self.write_cmd(SET_DISP | 0x01)

    def contrast(self, contrast):
        self.write_cmd(SET_CONTRAST)
        self.write_cmd(contrast)

    def invert(self, invert):
        self.write_cmd(SET_NORM_INV | (invert & 1))

    def rotate(self, rotate):
        self.write_cmd(SET_COM_OUT_DIR | ((rotate & 1) << 3))
        self.write_cmd(SET_SEG_REMAP | (rotate & 1))

    def show(self):
        x0 = 0
        x1 = self.width - 1
        if self.width != 128:
            col_offset = (128 - self.width) // 2
            x0 += col_offset
            x1 += col_offset
        self.write_cmd(SET_COL_ADDR)
        self.write_cmd(x0)
        self.write_cmd(x1)
        self.write_cmd(SET_PAGE_ADDR)
        self.write_cmd(0)
        self.write_cmd(self.pages - 1)
        self.write_data(self.buffer)

    # ══════════════════════════════════════════════════════
    #  NAF Blit
    # ══════════════════════════════════════════════════════

    def blit_naf_frame(self, frame, x=0, y=0):
        """
        Render a single decoded NAF frame onto the OLED buffer.

        Args:
            frame: NAFFrame from naf.get_frame(i), or raw list of bytearrays.
            x, y:  Top-left position on OLED. Negative values clip source.

        Auto-clips if frame exceeds screen bounds.
        """
        # Accept both NAFFrame objects and raw list[bytearray]
        if hasattr(frame, 'pages'):
            pages = frame.pages
            src_w = frame.width
            src_h = frame.height
        else:
            pages = frame
            src_w = len(frame[0]) if frame else 0
            src_h = len(frame) * 8

        src_pages = len(pages)
        if not pages or src_w == 0:
            return

        # ── Compute visible region ────────────────────────
        # Source region to draw
        src_x0 = max(0, -x)
        src_y0 = max(0, -y)
        src_x1 = min(src_w, self.width - x)
        src_y1 = min(src_h, self.height - y)

        if src_x0 >= src_x1 or src_y0 >= src_y1:
            return  # nothing visible

        # Destination on OLED
        dst_x0 = max(0, x)
        dst_y0 = max(0, y)
        draw_w = src_x1 - src_x0
        draw_h = src_y1 - src_y0

        # ── Page-aligned fast path ────────────────────────
        if (src_y0 & 7) == 0 and (dst_y0 & 7) == 0:
            sp0 = src_y0 // 8
            dp0 = dst_y0 // 8
            np = (draw_h + 7) // 8
            for p in range(np):
                sp = sp0 + p
                dp = dp0 + p
                if sp >= src_pages or dp >= self.pages:
                    break
                src = pages[sp]
                off = dp * self.width + dst_x0
                for c in range(draw_w):
                    self.buffer[off + c] |= src[src_x0 + c]
        else:
            # ── Unaligned path ────────────────────────────
            for col in range(draw_w):
                sx = src_x0 + col
                dx = dst_x0 + col
                for row in range(draw_h):
                    sy = src_y0 + row
                    dy = dst_y0 + row
                    sp = sy // 8
                    sb = sy & 7
                    dp = dy // 8
                    db = dy & 7
                    if sp < src_pages and dp < self.pages:
                        if (pages[sp][sx] >> sb) & 1:
                            self.buffer[dp * self.width + dx] |= (1 << db)

    def blit_naf(self, naf, x=0, y=0, interval=None):
        """
        Play all frames of a NAF animation with automatic timing.

        Args:
            naf:      NAF instance
            x, y:     Top-left position (supports negative for clipping)
            interval: Frame interval in ms. None = use naf.default_delay.
        """
        if naf.frames == 0:
            return

        ms = interval if interval is not None else naf.default_delay

        for i in range(naf.frames):
            self.fill(0)
            self.blit_naf_frame(naf[i], x, y)
            self.show()
            if ms > 0:
                time.sleep_ms(ms)
