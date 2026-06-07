/**
 * naf-render.js — Nova Animation Frames Renderer v1.1
 *
 * Lightweight NAF decoder + Canvas renderer. Zero dependencies.
 * Specify a target DOM element, load a .naf file, play/pause/seek.
 *
 * 配合 naf.js 使用：naf.js 提供编码/转换，naf-render.js 提供解码/播放。
 * 加载顺序：先 naf.js（编码），后 naf-render.js（解码+播放）。
 *
 * Usage:
 *   // ES module
 *   import { NAFRender } from './naf-render.js';
 *
 *   // Standalone (adds window.NAFRender, window.NAFParser)
 *   <script src="js/naf.js"></script>
 *   <script src="naf-render.js"></script>
 *
 * API:
 *   const player = new NAFRender('#my-div', { scale: 2, fps: 10 });
 *   await player.load('anim.naf');       // from URL
 *   player.loadBuffer(arrayBuffer);      // from raw data
 *   player.play();
 *   player.pause();
 *   player.seek(5);
 *   player.on('frame', (i) => { ... });
 *   player.destroy();
 *
 *   // Also exports NAFParser for raw decoding
 *   const parser = new NAFParser(arrayBuffer);
 */

(function (root, factory) {
  if (typeof define === 'function' && define.amd) {
    define([], factory);
  } else if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.NAFRender = factory();
  }
}(typeof self !== 'undefined' ? self : this, function () {

  'use strict';

  // ════════════════════════════════════════════════════════════
  //  NAF Binary Parser
  // ════════════════════════════════════════════════════════════

  const TYPE_RAW = 0, TYPE_RLE = 1, TYPE_DELTA = 2, TYPE_D_RLE = 3;

  class NAFParser {
    constructor(buffer) {
      this.buf = new Uint8Array(buffer);
      this.pos = 0;
      this._parse();
    }

    _read(n) { const v = this.buf.slice(this.pos, this.pos + n); this.pos += n; return v; }
    _u8()    { return this.buf[this.pos++]; }
    _u16be() { const v = (this.buf[this.pos] << 8) | this.buf[this.pos + 1]; this.pos += 2; return v; }
    _u32le() { const v = this.buf[this.pos] | (this.buf[this.pos + 1] << 8) | (this.buf[this.pos + 2] << 16) | (this.buf[this.pos + 3] << 24); this.pos += 4; return v >>> 0; }

    _parse() {
      const magic = this._read(4);
      if (String.fromCharCode(...magic) !== 'NAF\x1a') {
        throw new Error('Not a valid NAF file (bad magic)');
      }
      this.version = this._u8();
      if (this.version !== 1) throw new Error('Unsupported NAF version: ' + this.version);

      const w = this._u16be(); this.width  = w === 0 ? 1024 : w;
      const h = this._u16be(); this.height = h === 0 ? 1024 : h;
      this.pages = this._u8();
      this.frameCount = this._u16be();
      this.defaultDelay = this._u16be();
      this.loopCount = this._u8();
      this.flags = this._u8();
      this._read(2); // reserved

      this.offsets = [];
      for (let i = 0; i < this.frameCount; i++) this.offsets.push(this._u32le());
      this._cache = [];
    }

    getFrame(index) {
      if (index < 0 || index >= this.frameCount) return null;
      if (this._cache[index]) return this._cache[index];

      // Find nearest cached frame to decode forward from
      let start = 0, prev = null;
      for (let i = index; i >= 0; i--) {
        if (this._cache[i]) { start = i + 1; prev = this._cache[i]; break; }
      }
      for (let i = start; i <= index; i++) {
        prev = this._decodeFrameAt(i, prev);
        this._cache[i] = prev;
      }
      return prev;
    }

    _decodeFrameAt(index, prevFrame) {
      this.pos = this.offsets[index];
      const ftype = this._u8();
      /* delay */ this._u16be();

      const pageSizes = [];
      for (let p = 0; p < this.pages; p++) pageSizes.push(this._u16be());

      const isDelta = ftype === TYPE_DELTA || ftype === TYPE_D_RLE;
      const useRle  = ftype === TYPE_RLE   || ftype === TYPE_D_RLE;

      const frame = new Uint8Array(this.pages * this.width);
      for (let p = 0; p < this.pages; p++) {
        const ps = pageSizes[p];
        const dst = new Uint8Array(frame.buffer, p * this.width, this.width);

        if (ps === 0x0000) {
          dst.fill(0);
        } else if (ps === 0xFFFF && isDelta && prevFrame) {
          const src = new Uint8Array(prevFrame.buffer, p * this.width, this.width);
          dst.set(src);
        } else {
          const raw = this._read(ps);
          if (useRle) {
            this._rleDecode(raw, dst);
          } else {
            dst.set(raw.subarray(0, Math.min(raw.length, this.width)));
          }
        }
      }

      // Last-page mask for non-multiple-of-8 heights
      const trailing = this.height & 7;
      if (trailing) {
        const mask = (1 << trailing) - 1;
        const lastOff = (this.pages - 1) * this.width;
        for (let x = 0; x < this.width; x++) frame[lastOff + x] &= mask;
      }
      return frame;
    }

    _rleDecode(src, dst) {
      let si = 0, di = 0;
      const slen = src.length, dlen = dst.length;
      while (di < dlen && si < slen) {
        const ctrl = src[si++];
        if (ctrl === 0x00 || ctrl === 0x80) break;
        if (ctrl <= 0x7F) {
          const n = Math.min(ctrl, slen - si, dlen - di);
          dst.set(src.subarray(si, si + n), di);
          si += n; di += n;
        } else {
          const n = Math.min(ctrl - 0x80, dlen - di);
          if (si < slen) { dst.fill(src[si], di, di + n); si++; }
          di += n;
        }
      }
    }
  }

  // ════════════════════════════════════════════════════════════
  //  NAFRender
  // ════════════════════════════════════════════════════════════

  class NAFRender {
    /**
     * @param {string|HTMLElement} target  CSS selector or DOM element
     * @param {object}             opts
     * @param {number}             opts.scale     Pixel scale (default: 2)
     * @param {number}             opts.fps       Playback fps, 0 = use NAF timing (default: 0)
     * @param {boolean}            opts.autoplay  Auto-play after load (default: true)
     * @param {boolean}            opts.loop      Loop playback (default: true)
     */
    constructor(target, opts) {
      opts = opts || {};
      this._el = typeof target === 'string' ? document.querySelector(target) : target;
      if (!this._el) throw new Error('NAFRender: target element not found');

      this._scale    = opts.scale    || 2;
      this._fps      = opts.fps      || 0;
      this._autoplay = opts.autoplay !== false;
      this._loop     = opts.loop     !== false;
      this._invert   = false;

      this._naf      = null;
      this._frame    = 0;
      this._playing  = false;
      this._timer    = null;
      this._events   = {};

      this._buildDOM();
    }

    // ── DOM ──────────────────────────────────────────────

    _buildDOM() {
      this._canvas = document.createElement('canvas');
      this._canvas.style.display = 'block';
      this._canvas.style.imageRendering = 'pixelated';
      this._ctx = this._canvas.getContext('2d');
      this._el.appendChild(this._canvas);
    }

    // ── Load ─────────────────────────────────────────────

    /**
     * Load .naf from a URL.
     * @param {string} url
     * @returns {Promise<object>} info { width, height, frameCount, defaultDelay }
     */
    async load(url) {
      const resp = await fetch(url);
      if (!resp.ok) throw new Error('NAFRender: failed to fetch ' + url);
      const buf = await resp.arrayBuffer();
      return this.loadBuffer(buf);
    }

    /**
     * Load .naf from an ArrayBuffer or Uint8Array.
     * @param {ArrayBuffer|Uint8Array} buffer
     * @returns {object} info
     */
    loadBuffer(buffer) {
      this._naf = new NAFParser(buffer);
      this._frame = 0;
      this._canvas.width  = this._naf.width * this._scale;
      this._canvas.height = this._naf.height * this._scale;
      this._render();

      const info = {
        width:        this._naf.width,
        height:       this._naf.height,
        frameCount:   this._naf.frameCount,
        defaultDelay: this._naf.defaultDelay,
      };

      this._emit('load', info);

      if (this._autoplay && this._naf.frameCount > 1) {
        this.play();
      }

      return info;
    }

    // ── Playback ─────────────────────────────────────────

    play() {
      if (!this._naf || this._naf.frameCount < 2) return;
      if (this._playing) return;
      this._playing = true;
      this._emit('play');
      this._tick();
    }

    pause() {
      if (!this._playing) return;
      this._playing = false;
      if (this._timer) { clearTimeout(this._timer); this._timer = null; }
      this._emit('pause');
    }

    toggle() {
      this._playing ? this.pause() : this.play();
    }

    /**
     * Jump to a specific frame.
     * @param {number} index  Frame index (0-based)
     */
    seek(index) {
      if (!this._naf) return;
      this._frame = Math.max(0, Math.min(index, this._naf.frameCount - 1));
      this._render();
    }

    /** Step forward one frame. */
    step() {
      if (!this._naf) return;
      this._frame = (this._frame + 1) % this._naf.frameCount;
      this._render();
    }

    _tick() {
      if (!this._playing || !this._naf) return;

      const interval = this._fps > 0
        ? Math.round(1000 / this._fps)
        : this._naf.defaultDelay || 100;

      this._timer = setTimeout(() => {
        if (!this._playing) return;

        const next = this._frame + 1;
        if (next >= this._naf.frameCount) {
          if (this._loop) {
            this._frame = 0;
            this._emit('loop');
          } else {
            this.pause();
            this._emit('end');
            return;
          }
        } else {
          this._frame = next;
        }

        this._render();
        this._tick();
      }, interval);
    }

    // ── Render ───────────────────────────────────────────

    _render() {
      if (!this._naf) return;
      const frame = this._naf.getFrame(this._frame);
      if (!frame) return;

      const w = this._naf.width, h = this._naf.height, s = this._scale;
      const imgData = this._ctx.createImageData(w * s, h * s);
      const px = imgData.data;

      const invert = this._invert;
      for (let y = 0; y < h; y++) {
        const page = y >>> 3, bit = y & 7;
        for (let x = 0; x < w; x++) {
          let val = (frame[page * w + x] >> bit) & 1 ? 255 : 0;
          if (invert) val = 255 - val;
          for (let sy = 0; sy < s; sy++) {
            for (let sx = 0; sx < s; sx++) {
              const i = ((y * s + sy) * w * s + (x * s + sx)) * 4;
              px[i] = val; px[i + 1] = val; px[i + 2] = val; px[i + 3] = 255;
            }
          }
        }
      }
      this._ctx.putImageData(imgData, 0, 0);
      this._emit('frame', this._frame);
    }

    // ── Events ───────────────────────────────────────────

    /**
     * Subscribe to an event.
     * @param {'load'|'play'|'pause'|'loop'|'end'|'frame'} event
     * @param {function} callback
     */
    on(event, callback) {
      if (!this._events[event]) this._events[event] = [];
      this._events[event].push(callback);
      return this;
    }

    /** Toggle invert mode (black ↔ white). Re-renders current frame. */
    setInvert(on) {
      this._invert = !!on;
      this._render();
    }
    get invert() { return this._invert; }

    /** Remove an event listener. */
    off(event, callback) {
      if (!this._events[event]) return this;
      this._events[event] = this._events[event].filter(cb => cb !== callback);
      return this;
    }

    _emit(event, data) {
      if (!this._events[event]) return;
      for (const cb of this._events[event]) {
        try { cb(data); } catch (e) { console.error('NAFRender event error:', e); }
      }
    }

    // ── Info ─────────────────────────────────────────────

    /** Current frame index. */
    get currentFrame() { return this._frame; }

    /** Total frame count (0 if not loaded). */
    get frameCount() { return this._naf ? this._naf.frameCount : 0; }

    /** Is animation currently playing? */
    get isPlaying() { return this._playing; }

    // ── Cleanup ──────────────────────────────────────────

    /** Pause and remove canvas from DOM. */
    destroy() {
      this.pause();
      if (this._canvas && this._canvas.parentNode) {
        this._canvas.parentNode.removeChild(this._canvas);
      }
      this._naf = null;
      this._events = {};
    }
  }

  // ════════════════════════════════════════════════════════════
  //  Export
  // ════════════════════════════════════════════════════════════

  // Attach NAFParser to NAFRender for external use (gallery, etc.)
  NAFRender.Parser = NAFParser;

  return NAFRender;
}));
