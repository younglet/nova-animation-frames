#!/usr/bin/env python3
"""
naf2c — NAF binary ↔ text literal converter.

CLI:
  python naf2c input.naf -o anim.h              # NAF → C header
  python naf2c input.naf -o anim.py --py         # NAF → Python bytes
  python naf2c input.naf --hex                   # NAF → hex string (stdout)
  python naf2c anim.h -o output.naf              # C header → NAF
  python naf2c --hex 4E41461A... -o output.naf   # hex string → NAF

LIB:
  from naf2c import naf_to_c, naf_to_py, naf_to_hex, c_to_naf, hex_to_naf
"""

import argparse, re, sys, os


# ══════════════════════════════════════════════════════════════
#  Binary → Text
# ══════════════════════════════════════════════════════════════

def naf_to_c(input_path, output_path=None, var_name='naf_data'):
    """Convert .naf file to C header with const uint8_t array."""
    data = _read_file(input_path)
    lines = _format_bytes(data, 12)

    header = f"""// Auto-generated from {os.path.basename(input_path)}
// Size: {len(data)} bytes ({len(data)/1024:.1f} KB)
#ifndef NAF_DATA_H
#define NAF_DATA_H
#include <stdint.h>
#define NAF_DATA_LEN {len(data)}
const uint8_t {var_name}[] = {{
{lines}
}};
#endif
"""
    if output_path:
        with open(output_path, 'w') as f:
            f.write(header)
    return header


def naf_to_py(input_path, output_path=None, var_name='naf_data'):
    """Convert .naf file to Python bytes literal."""
    data = _read_file(input_path)
    lines = _format_bytes(data, 16)

    py = f"""# Auto-generated from {os.path.basename(input_path)}
# Size: {len(data)} bytes
{var_name} = (
{lines}
)
"""
    if output_path:
        with open(output_path, 'w') as f:
            f.write(py)
    return py


def naf_to_hex(input_path):
    """Convert .naf file to hex string."""
    return _read_file(input_path).hex()


def naf_to_base64(input_path):
    """Convert .naf file to base64 string."""
    import base64
    return base64.b64encode(_read_file(input_path)).decode()


# ══════════════════════════════════════════════════════════════
#  Text → Binary
# ══════════════════════════════════════════════════════════════

def hex_to_naf(hex_str, output_path):
    """Convert hex string to .naf binary file."""
    hex_str = hex_str.strip().replace(' ', '').replace('\n', '')
    if hex_str.startswith('0x') or hex_str.startswith('0X'):
        hex_str = hex_str[2:]
    data = bytes.fromhex(hex_str)
    with open(output_path, 'wb') as f:
        f.write(data)
    return len(data)


def c_to_naf(input_path, output_path):
    """Extract byte array from C source and save as .naf."""
    text = _read_text(input_path)
    # Match patterns like: 0x4E, 0x41, ... or 0x4E,0x41,...
    hex_bytes = re.findall(r'0x([0-9a-fA-F]{2})', text)
    if not hex_bytes:
        raise ValueError("No hex bytes found in C source (expected 0xNN format)")
    data = bytes(int(b, 16) for b in hex_bytes)
    with open(output_path, 'wb') as f:
        f.write(data)
    return len(data)


# ══════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════

def _read_file(path):
    with open(path, 'rb') as f:
        return f.read()


def _read_text(path):
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()


def _format_bytes(data, per_line):
    """Format bytes as comma-separated 0xNN hex literals."""
    lines = []
    for i in range(0, len(data), per_line):
        chunk = data[i:i + per_line]
        hexes = ', '.join(f'0x{b:02X}' for b in chunk)
        lines.append(f'    {hexes},')
    return '\n'.join(lines)


# ══════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='NAF ↔ C/Python/Hex converter')
    parser.add_argument('input', nargs='?', help='Input file or hex string (with --hex)')
    parser.add_argument('-o', '--output', help='Output file')
    parser.add_argument('--c', action='store_true', help='Output as C header (default for .h output)')
    parser.add_argument('--py', action='store_true', help='Output as Python bytes literal')
    parser.add_argument('--hex', action='store_true', help='Input is hex string, or output hex to stdout')
    parser.add_argument('--b64', action='store_true', help='Output base64')
    parser.add_argument('--name', default='naf_data', help='Variable name (default: naf_data)')

    args = parser.parse_args()

    # ── Hex string → Binary ──────────────────────────────
    if args.hex and args.input:
        size = hex_to_naf(args.input, args.output)
        print(f"  Hex → Binary: {size} bytes → {args.output}")
        return

    # ── Binary → Something ──────────────────────────────
    if not args.input:
        parser.print_help()
        return

    # Detect input type: .naf → text output, .c/.h → binary output
    ext = os.path.splitext(args.input)[1].lower()

    if ext in ('.c', '.h') and args.output:
        size = c_to_naf(args.input, args.output)
        print(f"  C source → Binary: {size} bytes → {args.output}")
        return

    # .naf → text
    in_size = os.path.getsize(args.input)
    if args.hex and not args.output:
        print(naf_to_hex(args.input))
    elif args.b64:
        print(naf_to_base64(args.input))
    elif args.py or (args.output and args.output.endswith('.py')):
        code = naf_to_py(args.input, args.output, args.name)
        if not args.output:
            print(code)
        else:
            print(f"  NAF → Python: {in_size:,}B → {os.path.getsize(args.output):,}B ({args.output})")
    else:
        # Default: C header
        out = args.output or (os.path.splitext(args.input)[0] + '.h')
        code = naf_to_c(args.input, out, args.name)
        print(f"  NAF → C header: {in_size:,}B → {os.path.getsize(out):,}B ({out})")


if __name__ == '__main__':
    main()
