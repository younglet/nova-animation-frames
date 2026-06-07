#!/usr/bin/env python3
"""
NAF Web Tools — Simple HTTP Server

Usage:
    python server.py              # Default: port 8080
    python server.py 3000         # Custom port
    python server.py --open       # Auto-open browser
"""

import http.server
import json
import os
import re
import struct
import sys
import webbrowser
from pathlib import Path

PORT = 8080
OPEN_BROWSER = False

for arg in sys.argv[1:]:
    if arg == '--open':
        OPEN_BROWSER = True
    elif arg.isdigit():
        PORT = int(arg)

WEB_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = WEB_DIR.parent.parent  # ssd1306_view/
os.chdir(str(PROJECT_ROOT))

# ═══════════════════════════════════════════════════════
#  NAF 文件元信息扫描
# ═══════════════════════════════════════════════════════

def scan_examples_dir():
    """扫描 examples/ 目录，返回所有 .naf 文件的元信息列表。"""
    examples = []
    ex_dir = PROJECT_ROOT / 'examples'
    if not ex_dir.is_dir():
        return examples

    for fp in sorted(ex_dir.rglob('*.naf')):
        rel = fp.relative_to(PROJECT_ROOT).as_posix()
        try:
            with open(fp, 'rb') as f:
                data = f.read(36)  # 头部足够解析关键字段
            if data[:4] != b'NAF\x1a':
                continue
            w = struct.unpack('>H', data[5:7])[0]
            h = struct.unpack('>H', data[7:9])[0]
            frames = struct.unpack('>H', data[10:12])[0]
            delay = struct.unpack('>H', data[12:14])[0]
            size = fp.stat().st_size
            # 分类：根目录 / 子目录
            parent = fp.relative_to(ex_dir).parent
            section = parent.as_posix() if parent.as_posix() != '.' else ''
            name = fp.stem
            examples.append({
                'path': f'/{rel}',
                'name': name,
                'width': 1024 if w == 0 else w,
                'height': 1024 if h == 0 else h,
                'frames': frames,
                'delay': delay,
                'size': size,
                'section': section,
            })
        except Exception as e:
            print(f"  skip {rel}: {e}")
    return examples


class CORSHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cross-Origin-Resource-Policy', 'cross-origin')
        super().end_headers()

    def do_GET(self):
        if self.path == '/api/ping':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'pong v2')
            return
        if self.path == '/api/examples':
            try:
                data = scan_examples_dir()
                body = json.dumps(data, ensure_ascii=False, indent=2).encode()
            except Exception as e:
                body = json.dumps({'error': str(e)}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, format, *args):
        print(f"  {args[0]}")


if __name__ == '__main__':
    print(f"\n  ═══════════════════════════════════════════")
    print(f"   NAF Web Tools Server")
    print(f"   Root:  {PROJECT_ROOT}")
    print(f"   Page:  http://localhost:{PORT}/tools/web/demo.html")
    print(f"   API:   http://localhost:{PORT}/api/examples")
    print(f"  ═══════════════════════════════════════════\n")

    if OPEN_BROWSER:
        webbrowser.open(f'http://localhost:{PORT}/tools/web/demo.html')

    with http.server.HTTPServer(('', PORT), CORSHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Server stopped.")
