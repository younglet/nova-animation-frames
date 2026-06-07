/**
 * esp32-serial.js — Web Serial + MicroPython raw REPL v3.0
 *
 * Connects to ESP32 running MicroPython via Web Serial API.
 * Enters raw REPL mode, writes files to the device filesystem.
 *
 * Reference: esptool-js Transport patterns for robust serial handling.
 * Bundled esptool-js.js available for advanced flashing operations.
 *
 * Usage:
 *   <script src="js/esp32-serial.js"></script>
 *   const esp = new ESP32Serial();
 *   await esp.connect();
 *   await esp.writeFile('/nafs/demo.naf', arrayBuffer, pct => {});
 *   await esp.disconnect();
 */

(function (root, factory) {
  if (typeof define === 'function' && define.amd) { define([], factory); }
  else if (typeof module === 'object' && module.exports) { module.exports = factory(); }
  else { root.ESP32Serial = factory(); }
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const CTRL_C = '\r\x03';       // Interrupt
  const CTRL_A = '\r\x01';       // Enter raw REPL
  const CTRL_B = '\r\x02';       // Exit raw REPL
  const CTRL_D = '\x04';         // Execute

  const BAUD_RATE = 115200;

  class ESP32Serial {
    constructor() {
      this._port = null;
      this._writer = null;
      this._readerClosed = false;
      this._connected = false;
      // Incoming data buffer
      this._inBuf = new Uint8Array(0);
    }

    get isConnected() { return this._connected; }

    // ═══ Connect ═══════════════════════════════════════

    async connect() {
      if (!('serial' in navigator)) {
        throw new Error('当前浏览器不支持 Web Serial API。请使用 Chrome 或 Edge 浏览器。');
      }

      let port;
      try {
        port = await navigator.serial.requestPort();
      } catch (e) {
        if ((e.message && e.message.includes('cancelled')) || e.name === 'AbortError' || e.name === 'NotFoundError') {
          throw new Error('未选择设备。请确认：\n1. ESP32 已通过 USB 连接\n2. 已安装 CH340/CP2102 驱动\n3. 设备管理器中可见 COM 端口');
        }
        if (e.message && e.message.includes('SecurityError')) {
          throw new Error('需要用户手势触发。请直接点击按钮连接，不要用快捷键。');
        }
        throw new Error('无法打开串口: ' + (e.message || e));
      }

      await port.open({ baudRate: BAUD_RATE, dataBits: 8, stopBits: 1, parity: 'none' });
      this._port = port;
      this._writer = port.writable.getWriter();

      // Start non-blocking read loop
      this._readerClosed = false;
      this._startReaderLoop(port);

      this._connected = true;

      // Drain any boot noise
      await sleep(300);
      await this._drain();

      const info = await this._enterRawRepl();
      return { port, info };
    }

    async disconnect() {
      this._connected = false;
      this._readerClosed = true;

      try { if (this._writer) { await this._sendRaw(CTRL_B); await sleep(50); } } catch (e) {}
      try { if (this._writer) { this._writer.releaseLock(); } } catch (e) {}
      try { if (this._port) { await this._port.close(); } } catch (e) {}

      this._writer = null;
      this._port = null;
      this._inBuf = new Uint8Array(0);
    }

    // ═══ Write File ════════════════════════════════════

    async writeFile(remotePath, data, onProgress) {
      if (!this._connected) throw new Error('ESP32 未连接');

      const u8 = new Uint8Array(data);
      const b64 = bytesToBase64(u8);
      const CHUNK = 8000;

      // Ensure directory
      const dir = remotePath.substring(0, remotePath.lastIndexOf('/'));
      if (dir) {
        await this._execRaw(`try:\n import os\n os.mkdir('${dir}')\nexcept:\n pass`);
        await sleep(30);
      }

      // Open file
      await this._execRaw(`f=open('${remotePath}','wb')`);
      await sleep(30);

      let sent = 0;
      for (let i = 0; i < b64.length; i += CHUNK) {
        const chunk = b64.substring(i, Math.min(i + CHUNK, b64.length));
        await this._execRaw(`f.write(__import__('ubinascii').a2b_base64('${chunk}'))`);
        sent += chunk.length;
        if (onProgress) onProgress(Math.min(100, Math.round(sent / b64.length * 100)));
        await sleep(10);
      }

      await this._execRaw('f.close()');
      await this._execRaw(`print('OK %d -> ${remotePath}' % ${u8.length})`);

      if (onProgress) onProgress(100);
    }

    // ═══ Internal: raw REPL ═════════════════════════════

    async _enterRawRepl() {
      await this._sendRaw(CTRL_C + CTRL_C);
      await sleep(400);
      await this._drain();

      await this._sendRaw(CTRL_A);
      await sleep(300);

      const resp = await this._readUntil('>', 5000);
      return resp.includes('raw REPL') ? resp : 'raw REPL ready';
    }

    async _execRaw(code) {
      await this._sendRaw(code + CTRL_D);
      await sleep(80);

      const resp = await this._readUntil('\x04>', 15000);

      if (resp.includes('Traceback') || resp.includes('Error') || resp.includes('SyntaxError')) {
        throw new Error('MicroPython: ' + resp.replace(/\x04/g, '').substring(0, 200));
      }

      return resp;
    }

    // ═══ Internal: I/O ══════════════════════════════════

    _startReaderLoop(port) {
      (async () => {
        const reader = port.readable.getReader();
        try {
          while (!this._readerClosed) {
            const { value, done } = await reader.read();
            if (done) break;
            if (value && value.length) {
              const merged = new Uint8Array(this._inBuf.length + value.length);
              merged.set(this._inBuf, 0);
              merged.set(value, this._inBuf.length);
              this._inBuf = merged;
            }
          }
        } catch (e) {
          // Reader closed or error
        } finally {
          try { reader.releaseLock(); } catch (e) {}
        }
      })();
    }

    async _readUntil(marker, timeoutMs) {
      const start = Date.now();
      const markerStr = typeof marker === 'string' ? marker : marker;

      while (Date.now() - start < timeoutMs) {
        if (this._inBuf.length > 0) {
          const text = new TextDecoder().decode(this._inBuf);
          const idx = text.indexOf(markerStr);
          if (idx >= 0) {
            const result = text.substring(0, idx + markerStr.length);
            // Remove consumed bytes
            const consumed = new TextEncoder().encode(result).length;
            this._inBuf = this._inBuf.slice(consumed);
            return result;
          }
        }
        await sleep(20);
      }

      // Timeout: return whatever is in buffer
      if (this._inBuf.length > 0) {
        const text = new TextDecoder().decode(this._inBuf);
        this._inBuf = new Uint8Array(0);
        return text;
      }
      return '';
    }

    async _sendRaw(str) {
      if (!this._writer) throw new Error('未连接');
      await this._writer.write(new TextEncoder().encode(str));
    }

    async _drain() {
      await sleep(200);
      if (this._inBuf.length > 0) {
        this._inBuf = new Uint8Array(0);
      }
    }
  }

  // ═══ Helpers ════════════════════════════════════════════

  function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

  function bytesToBase64(bytes) {
    const CHUNK_SZ = 0x8000;
    let result = '';
    for (let i = 0; i < bytes.length; i += CHUNK_SZ) {
      result += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK_SZ));
    }
    return btoa(result);
  }

  return ESP32Serial;
}));
