# NAF — Nova Animation Frames

> 紧凑单色动画格式，专为嵌入式 OLED 设计。  
> 1×1 ~ 65535×65535，多帧 + Delta + RLE 压缩。

## 项目结构

```
naf.py                      # MicroPython 解码器（ESP32）
NAF_Specification.md        # 二进制格式规范
examples/                   # 示例 NAF 文件
  expressions/              #   表情动画
  animations/               #   Bad Apple 等
tools/
  img2naf.py                # 图片 → NAF
  gif2naf.py                # GIF → NAF
  naf2img.py / naf2gif.py   # NAF → 图片/GIF
  naf2c.py                  # NAF → C 数组（嵌入固件）
  naf_encoder.py            # Python NAF 编码库
  web/
    demo.html               # 浏览器工具（转换器 + 画廊 + 播放器）
    naf-render.js           # JS NAF 解码 + Canvas 渲染
    server.py               # 一键 HTTP 服务器
    js/
      naf.js                # NAF 编码 + 图像二值化 + Floyd-Steinberg 抖动
      omggif.js             # GIF 解码器
      esp32-serial.js       # Web Serial → ESP32 MicroPython raw REPL
      gallery-data.js       # 画廊静态数据
      notyf.min.js/css      # Toast 通知
usage/                      # ESP32 使用示例
```

## 快速开始

### 浏览器工具

```bash
cd tools/web
python server.py 6789
# 打开 http://localhost:6789/tools/web/demo.html
```

- **转换器**：拖入 JPG/PNG/GIF 或粘贴 URL → 裁剪 `--fit stretch|contain|cover` → 编码 NAF
- **画廊**：38 个示例自动播放，一键下载到 ESP32
- **播放器**：播放/暂停/逐帧/反色，写入 ESP32 时自动应用帧率和反色
- **ESP32**：右上角 Web Serial 连接，通过 raw REPL 写文件到 `/nafs/`

### Python CLI

```bash
# 单张图片
python tools/img2naf photo.png -o out.naf -W 128 -H 64 --dither --fit contain

# GIF 动画
python tools/gif2naf anim.gif -o out.naf -W 128 -H 64 --dither --fit cover

# 反编译
python tools/naf2img out.naf -o frame.png
python tools/naf2gif out.naf -o anim.gif
```

### MicroPython

```python
from naf import NAF

naf = NAF("icon.naf")
frame = naf[0]
print(frame.width, frame.height)

# 像素级操作
frame.get_pixel(10, 20)         # → 0 | 1
frame.set_pixel(10, 20, 1)

# 反转
inverted = ~frame
frame.invert()

# SSD1306 渲染
oled.blit_naf(naf)              # 播放动画
oled.show()
```

## 格式

见 `NAF_Specification.md`。核心特性：RAW / RLE / Delta / Delta+RLE 四种帧类型，MONO_VLSB 页面布局。

## License

MIT
