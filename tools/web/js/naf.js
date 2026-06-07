/**
 * naf.js — NAF Encoder & Image Converter v1.0
 *
 * Browser-side NAF (Nova Animation Frames) encoding + image conversion.
 * Zero dependencies for encoding; omggif.js needed for GIF frame extraction.
 *
 * Usage:
 *   <script src="omggif.js"></script>
 *   <script src="naf.js"></script>
 *
 *   // Encode from image
 *   const encoder = new NAFEncoder(128, 64, { defaultDelay: 100, loopCount: 0 });
 *   const pages = imageToPages(canvas, 128, 64, { dither: true, threshold: 128 });
 *   encoder.addFrameRle(pages);
 *   const nafBuffer = encoder.encode(); // ArrayBuffer
 *
 *   // Decode GIF frames
 *   const frames = decodeGIFFrames(arrayBuffer); // Array<{canvas, delay}>
 */

(function (root, factory) {
  if (typeof define === 'function' && define.amd) {
    define([], factory);
  } else if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    // Export to window
    root.NAFEncoder = factory().NAFEncoder;
    root.imageToPages = factory().imageToPages;
    root.floydSteinberg = factory().floydSteinberg;
    root.decodeGIFFrames = factory().decodeGIFFrames;
    root.canvasToPages = factory().canvasToPages;
  }
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // ════════════════════════════════════════════════════════════
  //  NAFEncoder — NAF binary encoder
  // ════════════════════════════════════════════════════════════

  const MAGIC = new Uint8Array([0x4E, 0x41, 0x46, 0x1A]); // "NAF\x1a"
  const VERSION = 1;

  const TYPE_RAW   = 0;
  const TYPE_RLE   = 1;
  const TYPE_DELTA = 2;
  const TYPE_D_RLE = 3;

  const MAX_REPEAT  = 127;
  const MAX_LITERAL = 127;
  const MIN_REPEAT  = 3;

  class NAFEncoder {
    /**
     * @param {number} width  1~65535 (0 = 1024)
     * @param {number} height 1~65535 (0 = 1024)
     * @param {object} opts
     * @param {number} opts.defaultDelay  ms (default 100)
     * @param {number} opts.loopCount     0=forever (default 0)
     */
    constructor(width, height, opts) {
      opts = opts || {};
      this.width = width;
      this.height = height;
      this.pages = Math.ceil(height / 8);
      this.defaultDelay = opts.defaultDelay || 100;
      this.loopCount = opts.loopCount != null ? opts.loopCount : 0;

      // _frames: [{type, delay, pages: [Uint8Array...]}]
      this._frames = [];
    }

    /** Add a RAW (uncompressed) frame. */
    addFrameRaw(pages, delay) {
      this._validatePages(pages);
      this._frames.push({ type: TYPE_RAW, delay: delay || 0, pages: pages.map(p => new Uint8Array(p)) });
    }

    /** Add an RLE-compressed frame. */
    addFrameRle(pages, delay) {
      this._validatePages(pages);
      this._frames.push({ type: TYPE_RLE, delay: delay || 0, pages: pages.map(p => new Uint8Array(p)) });
    }

    /** Add a DELTA frame (changed pages only, raw). */
    addFrameDelta(pages, delay) {
      this._validatePages(pages);
      this._frames.push({ type: TYPE_DELTA, delay: delay || 0, pages: pages.map(p => new Uint8Array(p)) });
    }

    /** Add a DELTA+RLE frame. */
    addFrameDeltaRle(pages, delay) {
      this._validatePages(pages);
      this._frames.push({ type: TYPE_D_RLE, delay: delay || 0, pages: pages.map(p => new Uint8Array(p)) });
    }

    /**
     * Encode all frames into a .naf file buffer.
     * @returns {ArrayBuffer}
     */
    encode() {
      // First pass: compute encoded frame data
      const frameDataList = [];
      const offsets = [];
      let prevPages = null;

      for (let i = 0; i < this._frames.length; i++) {
        const f = this._frames[i];
        const { blob, pageSizes } = this._encodePages(f.pages, prevPages, f.type);

        frameDataList.push({
          type: f.type,
          delay: f.delay,
          pageSizes: pageSizes,
          blob: blob,
        });

        if (f.type === TYPE_DELTA || f.type === TYPE_D_RLE) {
          prevPages = f.pages;
        } else if (prevPages === null) {
          prevPages = f.pages;
        }
      }

      // Calculate total size
      const HEADER_SIZE = 18;
      const OFFSET_TABLE_SIZE = 4 * this._frames.length;

      let totalSize = HEADER_SIZE + OFFSET_TABLE_SIZE;
      for (const fd of frameDataList) {
        offsets.push(totalSize);
        // frame header: type(1) + delay(2) + page table(2*pages) + blob
        totalSize += 1 + 2 + 2 * this.pages + fd.blob.length;
      }

      const buf = new ArrayBuffer(totalSize);
      const view = new DataView(buf);
      const u8 = new Uint8Array(buf);
      let pos = 0;

      // Header
      u8.set(MAGIC, pos); pos += 4;
      u8[pos++] = VERSION;

      const wVal = (this.width === 1024) ? 0 : this.width;
      const hVal = (this.height === 1024) ? 0 : this.height;
      view.setUint16(pos, wVal, false); pos += 2;  // BE
      view.setUint16(pos, hVal, false); pos += 2;
      u8[pos++] = this.pages;
      view.setUint16(pos, this._frames.length, false); pos += 2;
      view.setUint16(pos, this.defaultDelay, false); pos += 2;
      u8[pos++] = this.loopCount;
      u8[pos++] = 0x00; // flags (LE offsets)
      pos += 2; // reserved

      // Offset table (LE)
      for (let i = 0; i < offsets.length; i++) {
        view.setUint32(pos, offsets[i], true); pos += 4;
      }

      // Frame data
      for (let i = 0; i < offsets.length; i++) {
        const fd = frameDataList[i];

        u8[pos++] = fd.type;
        view.setUint16(pos, fd.delay, false); pos += 2;

        // Page table
        for (let p = 0; p < this.pages; p++) {
          view.setUint16(pos, fd.pageSizes[p], false); pos += 2;
        }

        // Blob
        u8.set(fd.blob, pos); pos += fd.blob.length;
      }

      return buf;
    }

    // ── Internal ────────────────────────────────────────

    _validatePages(pages) {
      if (pages.length !== this.pages) {
        throw new Error(`Expected ${this.pages} pages, got ${pages.length}`);
      }
      for (let i = 0; i < pages.length; i++) {
        if (pages[i].length !== this.width) {
          throw new Error(`Page ${i}: expected ${this.width} bytes, got ${pages[i].length}`);
        }
      }
    }

    _rleEncodePage(data) {
      const out = [];
      const n = data.length;
      let i = 0;

      while (i < n) {
        // Measure repeat run
        let runLen = 1;
        while (i + runLen < n && data[i + runLen] === data[i] && runLen < MAX_REPEAT) {
          runLen++;
        }

        if (runLen >= MIN_REPEAT) {
          out.push(0x80 + runLen, data[i]);
          i += runLen;
        } else {
          const litStart = i;
          i++;
          while (i < n && (i - litStart) < MAX_LITERAL) {
            let ahead = 1;
            while (i + ahead < n && data[i + ahead] === data[i] && ahead < MAX_REPEAT) {
              ahead++;
            }
            if (ahead >= MIN_REPEAT) break;
            i++;
          }
          const litLen = i - litStart;
          out.push(litLen);
          for (let j = litStart; j < litStart + litLen; j++) out.push(data[j]);
        }
      }
      out.push(0x00); // terminator
      return new Uint8Array(out);
    }

    _encodePages(pages, prevPages, frameType) {
      const parts = [];
      const pageSizes = [];
      const isDelta = (frameType === TYPE_DELTA || frameType === TYPE_D_RLE);
      const useRle  = (frameType === TYPE_RLE   || frameType === TYPE_D_RLE);

      for (let i = 0; i < pages.length; i++) {
        const data = pages[i];

        // All-zero?
        if (isAllZero(data)) {
          pageSizes.push(0x0000);
          continue;
        }

        // Delta same-as-previous?
        if (isDelta && prevPages && arraysEqual(data, prevPages[i])) {
          pageSizes.push(0xFFFF);
          continue;
        }

        const encoded = useRle ? this._rleEncodePage(data) : data;
        pageSizes.push(encoded.length);
        parts.push(encoded);
      }

      const blob = concatUint8Arrays(parts);
      return { blob, pageSizes };
    }
  }

  // ════════════════════════════════════════════════════════════
  //  Image → Pages conversion
  // ════════════════════════════════════════════════════════════

  /**
   * Floyd-Steinberg dithering on a grayscale ImageData (0-255).
   * Modifies ImageData in-place and returns it.
   * @param {ImageData} imgData
   * @param {number} threshold 0-255
   * @returns {ImageData}
   */
  function floydSteinberg(imgData, threshold) {
    threshold = threshold || 128;
    const w = imgData.width, h = imgData.height;
    const d = imgData.data;
    // Use a float buffer for error diffusion
    const buf = new Float32Array(w * h);
    for (let i = 0; i < w * h; i++) {
      buf[i] = d[i * 4]; // R channel (all same for grayscale)
    }

    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const idx = y * w + x;
        const old = buf[idx];
        const newVal = old >= threshold ? 255 : 0;
        const err = old - newVal;
        buf[idx] = newVal;

        if (x + 1 < w)               buf[idx + 1]       += err * 7 / 16;
        if (y + 1 < h) {
          if (x - 1 >= 0)            buf[idx + w - 1]   += err * 3 / 16;
          buf[idx + w]               += err * 5 / 16;
          if (x + 1 < w)             buf[idx + w + 1]   += err * 1 / 16;
        }
      }
    }

    // Write back to ImageData
    for (let i = 0; i < w * h; i++) {
      const v = buf[i] >= 128 ? 255 : 0;
      const p = i * 4;
      d[p] = v; d[p + 1] = v; d[p + 2] = v;
    }
    return imgData;
  }

  /**
   * Convert an HTML Canvas (or ImageData) to NAF page bytes.
   * @param {HTMLCanvasElement|ImageData} source
   * @param {number} targetWidth
   * @param {number} targetHeight
   * @param {object} opts
   * @param {boolean} opts.dither    Apply Floyd-Steinberg dithering (default false)
   * @param {number}  opts.threshold Monochrome threshold 0-255 (default 128)
   * @param {boolean} opts.invert    Invert black/white (default false for canvasToPages)
   * @returns {Uint8Array[]} Array of page byte arrays
   */
  function canvasToPages(source, targetWidth, targetHeight, opts) {
    opts = opts || {};

    // Get ImageData from source
    let imgData;
    if (source instanceof ImageData) {
      imgData = source;
    } else {
      // Canvas
      const ctx = source.getContext('2d', { willReadFrequently: true });
      imgData = ctx.getImageData(0, 0, source.width, source.height);
    }

    // Create a temp canvas for resizing
    const tmpCanvas = document.createElement('canvas');
    tmpCanvas.width = targetWidth;
    tmpCanvas.height = targetHeight;
    const tmpCtx = tmpCanvas.getContext('2d');

    // Draw resized
    if (source instanceof HTMLCanvasElement) {
      tmpCtx.drawImage(source, 0, 0, targetWidth, targetHeight);
    } else {
      // ImageData → temp full-size canvas → resize
      const fullCanvas = document.createElement('canvas');
      fullCanvas.width = imgData.width;
      fullCanvas.height = imgData.height;
      fullCanvas.getContext('2d').putImageData(imgData, 0, 0);
      tmpCtx.drawImage(fullCanvas, 0, 0, targetWidth, targetHeight);
    }

    const resizedData = tmpCtx.getImageData(0, 0, targetWidth, targetHeight);

    // Dithering
    if (opts.dither) {
      floydSteinberg(resizedData, opts.threshold || 128);
    } else {
      // Simple threshold
      const d = resizedData.data;
      const th = opts.threshold || 128;
      for (let i = 0; i < d.length; i += 4) {
        const v = d[i] >= th ? 255 : 0;
        d[i] = v; d[i + 1] = v; d[i + 2] = v;
      }
    }

    // Invert
    if (opts.invert) {
      const d = resizedData.data;
      for (let i = 0; i < d.length; i += 4) {
        d[i] = 255 - d[i];
        d[i + 1] = 255 - d[i + 1];
        d[i + 2] = 255 - d[i + 2];
      }
    }

    return imageDataToPages(resizedData, targetWidth, targetHeight);
  }

  /**
   * Convert ImageData to NAF pages (MONO_VLSB format).
   * page[p][col].bit[b] = pixel at row (p*8 + b), column (col)
   */
  function imageDataToPages(imgData, width, height) {
    const pagesCount = Math.ceil(height / 8);
    const pages = new Array(pagesCount);
    for (let p = 0; p < pagesCount; p++) {
      pages[p] = new Uint8Array(width);
    }

    const d = imgData.data;
    for (let y = 0; y < height; y++) {
      const pageIdx = y >>> 3;
      const bit = y & 7;
      for (let x = 0; x < width; x++) {
        const px = (y * width + x) * 4;
        if (d[px] > 127) { // white pixel → bit set
          pages[pageIdx][x] |= (1 << bit);
        }
      }
    }

    return pages;
  }

  /**
   * Legacy alias — convert ImageData + dimensions to NAF pages.
   */
  function imageToPages(imgData, width, height, opts) {
    // imgData is ImageData, width/height are target dimensions
    if (opts && opts.dither) {
      floydSteinberg(imgData, opts.threshold || 128);
    }
    if (opts && opts.invert) {
      const d = imgData.data;
      for (let i = 0; i < d.length; i += 4) {
        d[i] = 255 - d[i];
        d[i + 1] = 255 - d[i + 1];
        d[i + 2] = 255 - d[i + 2];
      }
    }
    return imageDataToPages(imgData, width, height);
  }

  // ════════════════════════════════════════════════════════════
  //  GIF Frame Decoder (requires omggif.js)
  // ════════════════════════════════════════════════════════════

  /**
   * Decode all frames from a GIF ArrayBuffer.
   * Requires omggif.js to be loaded.
   * @param {ArrayBuffer} buffer
   * @returns {{ frames: Array<{canvas: HTMLCanvasElement, delay: number}>, width: number, height: number }}
   */
  function decodeGIFFrames(buffer) {
    if (typeof GifReader === 'undefined') {
      throw new Error('omggif.js is required for GIF decoding. Include <script src="js/omggif.js"></script>');
    }

    const u8 = new Uint8Array(buffer);
    const reader = new GifReader(u8);
    const numFrames = reader.numFrames();
    const gifWidth = reader.width;
    const gifHeight = reader.height;

    const frames = [];

    // Accumulate frames (GIF frames may only update a sub-rectangle)
    const accumCanvas = document.createElement('canvas');
    accumCanvas.width = gifWidth;
    accumCanvas.height = gifHeight;
    const accumCtx = accumCanvas.getContext('2d');

    let prevInfo = null;

    for (let i = 0; i < numFrames; i++) {
      const info = reader.frameInfo(i);

      // Decode sub-rect RGBA pixels at the frame's position within full buffer
      const fullPixels = new Uint8Array(gifWidth * gifHeight * 4);
      reader.decodeAndBlitFrameRGBA(i, fullPixels);

      // Handle disposal of previous frame
      if (prevInfo && prevInfo.disposal === 2) {
        accumCtx.clearRect(prevInfo.x, prevInfo.y, prevInfo.width, prevInfo.height);
      }

      // Extract just the sub-rect from fullPixels
      const subW = info.width, subH = info.height;
      const subPixels = new Uint8ClampedArray(subW * subH * 4);
      for (let row = 0; row < subH; row++) {
        const srcOff = ((info.y + row) * gifWidth + info.x) * 4;
        const dstOff = row * subW * 4;
        subPixels.set(fullPixels.subarray(srcOff, srcOff + subW * 4), dstOff);
      }

      // Draw sub-rect onto accumulator at correct position
      const tmpCanvas = document.createElement('canvas');
      tmpCanvas.width = subW;
      tmpCanvas.height = subH;
      tmpCanvas.getContext('2d').putImageData(new ImageData(subPixels, subW, subH), 0, 0);
      accumCtx.drawImage(tmpCanvas, info.x, info.y);

      // Snapshot accumulator into a clean frame canvas
      const frameCanvas = document.createElement('canvas');
      frameCanvas.width = gifWidth;
      frameCanvas.height = gifHeight;
      frameCanvas.getContext('2d').drawImage(accumCanvas, 0, 0);

      // Delay in ms (GIF delay unit is 1/100s)
      let delay = (info.delay || 10) * 10;
      if (delay < 20) delay = 100;

      frames.push({
        canvas: frameCanvas,
        delay: delay,
        width: gifWidth,
        height: gifHeight,
      });

      prevInfo = info;
    }

    return { frames, width: gifWidth, height: gifHeight };
  }

  // ════════════════════════════════════════════════════════════
  //  Invert a parsed NAF buffer (returns new ArrayBuffer)
  //  Requires NAFRender.Parser for decoding
  // ════════════════════════════════════════════════════════════

  NAFEncoder.invertNAF = function(parser) {
    const enc = new NAFEncoder(parser.width, parser.height, {
      defaultDelay: parser.defaultDelay || 100,
      loopCount: parser.loopCount || 0,
    });
    for (let i = 0; i < parser.frameCount; i++) {
      const src = parser.getFrame(i);
      const inv = new Uint8Array(src.length);
      for (let j = 0; j < src.length; j++) inv[j] = ~src[j] & 0xFF;
      if (i === 0) enc.addFrameRle(inv, parser.defaultDelay || 100);
      else enc.addFrameDeltaRle(inv, parser.defaultDelay || 100);
    }
    return enc.encode();
  };

  // ════════════════════════════════════════════════════════════
  //  Helpers
  // ════════════════════════════════════════════════════════════

  function isAllZero(data) {
    for (let i = 0; i < data.length; i++) {
      if (data[i] !== 0) return false;
    }
    return true;
  }

  function arraysEqual(a, b) {
    if (a.length !== b.length) return false;
    for (let i = 0; i < a.length; i++) {
      if (a[i] !== b[i]) return false;
    }
    return true;
  }

  function concatUint8Arrays(arrays) {
    let totalLen = 0;
    for (const a of arrays) totalLen += a.length;
    const out = new Uint8Array(totalLen);
    let offset = 0;
    for (const a of arrays) {
      out.set(a, offset);
      offset += a.length;
    }
    return out;
  }

  // ════════════════════════════════════════════════════════════
  //  Export
  // ════════════════════════════════════════════════════════════

  return {
    NAFEncoder: NAFEncoder,
    imageToPages: imageToPages,
    canvasToPages: canvasToPages,
    floydSteinberg: floydSteinberg,
    decodeGIFFrames: decodeGIFFrames,
  };
}));
