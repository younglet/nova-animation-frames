# NAF + SSD1306 Usage

将 `usage/` 目录上传到 ESP32 即可运行。

## 结构

```
usage/
├── lib/
│   ├── naf.py            # NAF 解码器
│   └── ssd1306_naf.py    # SSD1306 驱动 (内置 blit)
├── main.py               # 入口脚本
├── demo.png              # 128×64 预览图
├── demo.naf              # 示例 NAF 文件
└── README.md
```

## 接线

```
ESP32       SSD1306
GPIO22  →   SCL
GPIO21  →   SDA
3.3V    →   VCC
GND     →   GND
```

## 上传

```bash
# 用 mpremote 或 ampy 上传
mpremote cp -r usage/lib :
mpremote cp usage/main.py :main.py

# 如果有 .naf 文件
mpremote cp animation.naf :animation.naf
```

## 运行

```python
# main.py 自带示例，上电自动运行
# 或手动：
from ssd1306_naf import SSD1306
from naf import NAF
from machine import I2C, Pin

i2c = I2C(1, scl=Pin(22), sda=Pin(21))
oled = SSD1306(128, 64, i2c)

naf = NAF("animation.naf")     # 文件
# naf = NAF(b'\x4E\x41...')    # 或内存 bytes

oled.blit_naf_frame(naf[0])             # 第 0 帧，全屏
oled.blit_naf_frame(naf[3], x=16, y=8)  # 第 3 帧，偏移
oled.show()

# 播放完整动画
oled.blit_naf(naf)                      # 全屏，自动帧间隔
```
