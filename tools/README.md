# NAF Tools

## Image/Video → NAF

```bash
python tools/gif2naf anim.gif -o out.naf -W 128 -H 64          # GIF 动画
python tools/img2naf icon.png -o icon.naf -W 32 -H 32          # 单张图片
python tools/mp42naf video.mp4 -o out.naf -W 128 -H 64 --fps 12 # 视频
```

## 二值化方式（二选一）

| 参数 | 方法 | 特点 | 适用场景 |
|------|------|------|----------|
| `--dither` | Floyd-Steinberg 抖动 | 误差扩散，保留灰度渐变，细节丰富 | 视频、照片、写实画面 |
| `-t 128` | 阈值二值化（默认） | 直接黑白切分，画面干净无噪点 | 图标、文字、线条、纯色图 |

> 抖动通过将量化误差扩散到相邻像素来模拟灰度，128×64 小屏上能看到更多层次；
> 阈值直接以 `-t` 指定分界线（0~255），越高画面越暗/越少点亮。

## 其他参数

```
  --fit contain      填充方式: stretch(默认) | contain(适应) | cover(裁剪)
  --delay 50         帧间隔 ms (默认 100)
  --no-invert        关闭默认反相（黑底白图源用此项）
  --no-delta         禁用帧间 Delta 压缩
  -l 0               循环次数 (0=无限)
```

## NAF → 其他格式

```bash
python tools/naf2gif input.naf -o out.gif -s 4                 # → GIF, 4x 放大
python tools/naf2img input.naf -o out.png --frame 0 -s 2       # → PNG 单帧
python tools/naf2img input.naf -o seq.png                      # → PNG 全部帧
python tools/naf2c input.naf -o anim.h                         # → C 头文件
python tools/naf2c input.naf -o anim.py --py                   # → Python bytes
python tools/naf2c input.naf --hex                             # → hex 字符串
python tools/naf2c input.naf --b64                             # → base64
```

## 浏览器预览

```bash
open tools/web/demo.html    # 拖入 .naf 文件即可播放
```

## 编码库 (import)

```python
from naf_encoder import NAFEncoder
from naf_convert import image_to_pages, floyd_steinberg
```
