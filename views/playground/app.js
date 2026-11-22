// Meme Stickers Playground JS - Enhanced with 60FPS Pure Frontend Canvas 2D + CDN/CacheStorage Font Loading
const PLUGIN_NAME = "astrbot_plugin_meme_stickers";

// Bridge Adapter: 优先使用 AstrBotPluginView/AstrBotPluginPage，否则降级使用 fetch
class BridgeClient {
  constructor() {
    this.bridge = window.AstrBotPluginView || window.AstrBotPluginPage || null;
  }

  async init() {
    if (this.bridge && typeof this.bridge.ready === "function") {
      try {
        await this.bridge.ready();
        console.log("[Bridge] AstrBot Bridge initialized successfully.");
      } catch (err) {
        console.warn("[Bridge] Bridge ready warning:", err);
      }
    }
  }

  async apiGet(endpoint, params = {}) {
    if (this.bridge && typeof this.bridge.apiGet === "function") {
      return await this.bridge.apiGet(endpoint, params);
    }
    const cleanEp = endpoint.replace(/^\/+/, "");
    const q = new URLSearchParams(params).toString();
    const url = `/api/plug/${PLUGIN_NAME}/${cleanEp}${q ? "?" + q : ""}`;
    const res = await fetch(url);
    if (!res.ok) {
      let errDetail = res.statusText;
      try {
        const j = await res.json();
        errDetail = j.message || j.error || j.detail || JSON.stringify(j);
      } catch (_) {}
      throw new Error(`HTTP ${res.status}: ${errDetail}`);
    }
    const json = await res.json();
    return json.data !== undefined ? json.data : json;
  }

  async apiPost(endpoint, body = {}) {
    if (this.bridge && typeof this.bridge.apiPost === "function") {
      return await this.bridge.apiPost(endpoint, body);
    }
    const cleanEp = endpoint.replace(/^\/+/, "");
    const url = `/api/plug/${PLUGIN_NAME}/${cleanEp}`;
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      let errDetail = res.statusText;
      try {
        const j = await res.json();
        errDetail = j.message || j.error || j.detail || JSON.stringify(j);
      } catch (_) {
        try {
          errDetail = await res.text();
        } catch (_) {}
      }
      throw new Error(`HTTP ${res.status}: ${errDetail}`);
    }
    const json = await res.json();
    return json.data !== undefined ? json.data : json;
  }
}

const client = new BridgeClient();

// State
let globalPacksTree = {};
let currentSelectedSticker = null;
let currentBaseImage = null;
let currentGeneratedImageUri = null;
let fontLoaded = false;
let rafId = null;
let liveDebounceTimer = null;
let currentRenderSeq = 0;
const clientImageCache = new Map();

// Reusable offscreen canvas to avoid GC pauses during 60FPS dragging
let offscreenCanvas = null;
let offscreenCtx = null;
function getOffscreenCanvas(w, h) {
  if (!offscreenCanvas) {
    offscreenCanvas = document.createElement("canvas");
    offscreenCtx = offscreenCanvas.getContext("2d", { willReadFrequently: true });
  }
  if (offscreenCanvas.width !== w || offscreenCanvas.height !== h) {
    offscreenCanvas.width = w;
    offscreenCanvas.height = h;
  } else {
    offscreenCtx.clearRect(0, 0, w, h);
  }
  return { offscreenCanvas, offCtx: offscreenCtx };
}

// DOM Elements
const elements = {
  // Tabs
  tabs: document.querySelectorAll(".nav-tab"),
  tabContents: document.querySelectorAll(".tab-content"),
  // Playground Form
  packSelect: document.getElementById("pack-select"),
  categorySelect: document.getElementById("category-select"),
  stickerSelect: document.getElementById("sticker-select"),
  textInput: document.getElementById("text-input"),
  fontSizeRange: document.getElementById("font-size-range"),
  fontSizeVal: document.getElementById("font-size-val"),
  textAlignSelect: document.getElementById("text-align-select"),
  textColorPicker: document.getElementById("text-color-picker"),
  textColorHex: document.getElementById("text-color-hex"),
  strokeColorPicker: document.getElementById("stroke-color-picker"),
  strokeColorHex: document.getElementById("stroke-color-hex"),
  textXInput: document.getElementById("text-x-input"),
  textYInput: document.getElementById("text-y-input"),
  rotateRange: document.getElementById("rotate-range"),
  rotateVal: document.getElementById("rotate-val"),
  strokeWidthRange: document.getElementById("stroke-width-range"),
  strokeWidthVal: document.getElementById("stroke-width-val"),
  fontStyleSelect: document.getElementById("font-style-select"),
  imageFormatSelect: document.getElementById("image-format-select"),
  autoResizeCheck: document.getElementById("auto-resize-check"),
  debugCheck: document.getElementById("debug-check"),
  btnGenerate: document.getElementById("btn-generate"),
  btnDownload: document.getElementById("btn-download"),
  btnCopy: document.getElementById("btn-copy"),
  btnReset: document.getElementById("btn-reset"),
  btnResetParams: document.getElementById("btn-reset-params"),
  // Preview
  previewContainer: document.getElementById("preview-container"),
  placeholderBox: document.getElementById("placeholder-box"),
  previewImage: document.getElementById("preview-image"),
  previewCanvas: document.getElementById("preview-canvas"),
  clientRenderCheck: document.getElementById("client-render-check"),
  livePreviewCheck: document.getElementById("live-preview-check"),
  renderTimeBadge: document.getElementById("render-time-badge"),
  metaTagsBox: document.getElementById("meta-tags-box"),
  badgePack: document.getElementById("badge-pack"),
  badgeSize: document.getElementById("badge-size"),
  badgeFilesize: document.getElementById("badge-filesize"),
  // Resources
  emojiStatusBadge: document.getElementById("emoji-status-badge"),
  emojiStatusDesc: document.getElementById("emoji-status-desc"),
  emojiFontSourceSelect: document.getElementById("emoji-font-source-select"),
  btnPullEmojiFont: document.getElementById("btn-pull-emoji-font"),
  primaryStatusBadge: document.getElementById("primary-status-badge"),
  primaryStatusDesc: document.getElementById("primary-status-desc"),
  packsTableBody: document.getElementById("packs-table-body"),
  btnReloadPacks: document.getElementById("btn-reload-packs"),
  btnInstallAllHub: document.getElementById("btn-install-all-hub"),
  logConsole: document.getElementById("log-console"),
  // Mirrors
  btnMirrors: document.querySelectorAll(".btn-mirror"),
  cfgMirrorPreset: document.getElementById("cfg-mirror-preset"),
  cfgEmojiFontUrl: document.getElementById("cfg-emoji-font-url"),
  cfgHubManifestUrl: document.getElementById("cfg-hub-manifest-url"),
  cfgGithubUrlTemplate: document.getElementById("cfg-github-url-template"),
  cfgProxy: document.getElementById("cfg-proxy"),
};

function logToConsole(msg) {
  const time = new Date().toLocaleTimeString();
  if (elements.logConsole) {
    elements.logConsole.textContent = `[${time}] ${msg}\n` + elements.logConsole.textContent;
  }
}

// Color conversion helpers
function rgbaToHex(rgba) {
  if (typeof rgba === "string") return rgba;
  if (!Array.isArray(rgba)) return "#000000";
  const [r, g, b] = rgba;
  return "#" + [r, g, b].map(x => Math.round(x || 0).toString(16).padStart(2, "0")).join("").toUpperCase();
}

function hexToRgba(hex) {
  let c = hex.replace("#", "").trim();
  if (c.length === 3) c = c.split("").map(x => x + x).join("");
  const num = parseInt(c.slice(0, 6), 16);
  const a = c.length >= 8 ? parseInt(c.slice(6, 8), 16) : 255;
  return [(num >> 16) & 255, (num >> 8) & 255, num & 255, a];
}

// Math helpers for rotation
function rotatePoint(x, y, ox, oy, rad) {
  const cos = Math.cos(rad);
  const sin = Math.sin(rad);
  const dx = x - ox;
  const dy = y - oy;
  return {
    x: ox + dx * cos - dy * sin,
    y: oy + dx * sin + dy * cos,
  };
}

function calcRotatedAABB(box, origin, deg) {
  const rad = (deg * Math.PI) / 180;
  const [bx, by, bw, bh] = box;
  const corners = [
    rotatePoint(bx, by, origin.x, origin.y, rad),
    rotatePoint(bx + bw, by, origin.x, origin.y, rad),
    rotatePoint(bx + bw, by + bh, origin.x, origin.y, rad),
    rotatePoint(bx, by + bh, origin.x, origin.y, rad),
  ];
  const xs = corners.map(p => p.x);
  const ys = corners.map(p => p.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  return { minX, minY, maxX, maxY, width: maxX - minX, height: maxY - minY };
}

function getResizeContain(srcW, srcH, dstW, dstH) {
  const ratio = Math.min(dstW / srcW, dstH / srcH);
  const w = srcW * ratio;
  const h = srcH * ratio;
  return { x: (dstW - w) / 2, y: (dstH - h) / 2, w, h };
}

// Fill enclosed inner loops/counters (e.g. inside 'o', 'g', 'e', 'a') to prevent background leakage
function fillInnerCounters(ctx, w, h, strokeRgba) {
  const imgData = ctx.getImageData(0, 0, w, h);
  const data = imgData.data;
  const visited = new Uint8Array(w * h);
  const queue = new Int32Array(w * h);
  let qHead = 0;
  let qTail = 0;

  // Boundary seed check
  for (let x = 0; x < w; x++) {
    const topIdx = x;
    if (data[topIdx * 4 + 3] === 0) { visited[topIdx] = 1; queue[qTail++] = topIdx; }
    const botIdx = (h - 1) * w + x;
    if (data[botIdx * 4 + 3] === 0) { visited[botIdx] = 1; queue[qTail++] = botIdx; }
  }
  for (let y = 0; y < h; y++) {
    const leftIdx = y * w;
    if (data[leftIdx * 4 + 3] === 0 && !visited[leftIdx]) { visited[leftIdx] = 1; queue[qTail++] = leftIdx; }
    const rightIdx = y * w + (w - 1);
    if (data[rightIdx * 4 + 3] === 0 && !visited[rightIdx]) { visited[rightIdx] = 1; queue[rightIdx] = 1; queue[qTail++] = rightIdx; }
  }

  // BFS
  while (qHead < qTail) {
    const curr = queue[qHead++];
    const cx = curr % w;
    const cy = Math.floor(curr / w);
    if (cx > 0) {
      const idx = curr - 1;
      if (!visited[idx] && data[idx * 4 + 3] === 0) { visited[idx] = 1; queue[qTail++] = idx; }
    }
    if (cx < w - 1) {
      const idx = curr + 1;
      if (!visited[idx] && data[idx * 4 + 3] === 0) { visited[idx] = 1; queue[qTail++] = idx; }
    }
    if (cy > 0) {
      const idx = curr - w;
      if (!visited[idx] && data[idx * 4 + 3] === 0) { visited[idx] = 1; queue[qTail++] = idx; }
    }
    if (cy < h - 1) {
      const idx = curr + w;
      if (!visited[idx] && data[idx * 4 + 3] === 0) { visited[idx] = 1; queue[qTail++] = idx; }
    }
  }

  const [sr, sg, sb, sa = 255] = strokeRgba;
  for (let i = 0; i < w * h; i++) {
    if (!visited[i]) {
      const a = data[i * 4 + 3];
      if (a === 0) {
        data[i * 4] = sr;
        data[i * 4 + 1] = sg;
        data[i * 4 + 2] = sb;
        data[i * 4 + 3] = sa;
      } else if (a < 255) {
        const topAlpha = a / 255;
        const botAlpha = (sa / 255) * (1 - topAlpha);
        const outAlpha = topAlpha + botAlpha;
        if (outAlpha > 0) {
          data[i * 4] = Math.round((data[i * 4] * topAlpha + sr * botAlpha) / outAlpha);
          data[i * 4 + 1] = Math.round((data[i * 4 + 1] * topAlpha + sg * botAlpha) / outAlpha);
          data[i * 4 + 2] = Math.round((data[i * 4 + 2] * topAlpha + sb * botAlpha) / outAlpha);
          data[i * 4 + 3] = Math.round(outAlpha * 255);
        }
      }
    }
  }
  ctx.putImageData(imgData, 0, 0);
}

// -------------------------------------------------------------
// Font Loading: CDN / GitHub Prioritized + CacheStorage Offline
// -------------------------------------------------------------
const FONT_NAME = "YurukaFangTang";
const FONT_CDN_SOURCES = [
  "https://cdn.jsdelivr.net/gh/kyuphoenix/pjsk-stickers-server@main/fonts/YurukaFangTang.ttf",
  "https://ghfast.top/https://raw.githubusercontent.com/kyuphoenix/pjsk-stickers-server/main/fonts/YurukaFangTang.ttf",
  "https://cdn.jsdelivr.net/gh/lgc-NB2Dev/meme-stickers-hub@main/pjsk/YurukaFangTang.ttf",
  "https://raw.githubusercontent.com/kyuphoenix/pjsk-stickers-server/main/fonts/YurukaFangTang.ttf",
];

async function initWebFont() {
  if (document.fonts && document.fonts.check(`16px "${FONT_NAME}"`)) {
    fontLoaded = true;
    return;
  }

  const CACHE_NAME = "meme-stickers-fonts-v1";
  const CACHE_KEY = "/fonts/YurukaFangTang.ttf";
  let fontBuffer = null;

  // 1. Try browser CacheStorage (0ms instant load across sessions)
  try {
    if (typeof caches !== "undefined") {
      const cache = await caches.open(CACHE_NAME);
      const cachedResp = await cache.match(CACHE_KEY);
      if (cachedResp && cachedResp.ok) {
        fontBuffer = await cachedResp.arrayBuffer();
        logToConsole(`[字体] 从浏览器本地离线缓存加载 ${FONT_NAME}.ttf 成功 (0ms)`);
      }
    }
  } catch (err) {
    console.warn("[Font] CacheStorage check failed:", err);
  }

  // 2. Fetch from CDN / GitHub mirrors in sequence (avoids hitting user server bandwidth)
  if (!fontBuffer) {
    for (const url of FONT_CDN_SOURCES) {
      try {
        logToConsole(`[字体] 优先从 CDN 拉取字体: ${url.slice(0, 60)}...`);
        const resp = await fetch(url, { mode: "cors" });
        if (resp.ok) {
          const buf = await resp.arrayBuffer();
          if (buf && buf.byteLength > 100000) {
            fontBuffer = buf;
            logToConsole(`[字体] CDN 加载成功! 体积: ${(buf.byteLength / 1024 / 1024).toFixed(2)} MB`);
            // Persist into CacheStorage so next visits never download again
            try {
              if (typeof caches !== "undefined") {
                const cache = await caches.open(CACHE_NAME);
                await cache.put(CACHE_KEY, new Response(buf.slice(0), {
                  headers: { "Content-Type": "font/ttf" }
                }));
              }
            } catch (_) {}
            break;
          }
        }
      } catch (err) {
        console.warn(`[Font] CDN ${url} error:`, err);
      }
    }
  }

  // 3. Fallback to local AstrBot server only if all CDNs failed
  if (!fontBuffer) {
    try {
      logToConsole("[字体] CDN 无法访问，降级请求本地 AstrBot 服务器获取字体...");
      const res = await client.apiGet("font/primary");
      if (res && res.data_uri) {
        const b64 = res.data_uri.split(",")[1];
        const binary = atob(b64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        fontBuffer = bytes.buffer;
        logToConsole("[字体] 本地服务器主字体加载成功！");
      }
    } catch (err) {
      logToConsole(`[字体] 本地服务器字体兜底失败: ${err.message}`);
    }
  }

  // 4. Register FontFace with browser
  if (fontBuffer) {
    try {
      const fontFace = new FontFace(FONT_NAME, fontBuffer);
      await fontFace.load();
      document.fonts.add(fontFace);
      fontLoaded = true;
      logToConsole(`[字体] "${FONT_NAME}" 已成功注册到浏览器引擎`);
      requestRender();
    } catch (err) {
      console.error("[Font] FontFace registration error:", err);
    }
  }
}

// -------------------------------------------------------------
// Image Preloader: CDN + Cache + Local API Fallback
// -------------------------------------------------------------
async function loadClientImage(cdnUrl, packSlug, baseImageRel) {
  const cacheKey = cdnUrl || `${packSlug}/${baseImageRel}`;
  if (!cacheKey) return null;
  if (clientImageCache.has(cacheKey)) {
    return clientImageCache.get(cacheKey);
  }

  const urlsToTry = [];
  if (cdnUrl) {
    urlsToTry.push(cdnUrl);
    if (cdnUrl.includes("raw.githubusercontent.com")) {
      urlsToTry.push(cdnUrl.replace("raw.githubusercontent.com/lgc-NB2Dev/meme-stickers-hub/main", "cdn.jsdelivr.net/gh/lgc-NB2Dev/meme-stickers-hub@main"));
      urlsToTry.push(cdnUrl.replace("https://raw.githubusercontent.com", "https://ghfast.top/https://raw.githubusercontent.com"));
    }
  }
  if (packSlug && baseImageRel) {
    urlsToTry.push(`https://cdn.jsdelivr.net/gh/lgc-NB2Dev/meme-stickers-hub@main/${packSlug}/${baseImageRel}`);
    urlsToTry.push(`https://ghfast.top/https://raw.githubusercontent.com/lgc-NB2Dev/meme-stickers-hub/main/${packSlug}/${baseImageRel}`);
  }

  // 1. Try loading from CDN / GitHub
  for (const u of urlsToTry) {
    try {
      const img = await new Promise((resolve, reject) => {
        const i = new Image();
        i.crossOrigin = "anonymous";
        i.onload = () => resolve(i);
        i.onerror = reject;
        i.src = u;
      });
      clientImageCache.set(cacheKey, img);
      return img;
    } catch (_) {}
  }

  // 2. Fallback: Fetch raw image from AstrBot local API
  if (packSlug && baseImageRel) {
    try {
      const res = await client.apiGet("sticker_image", { pack: packSlug, file: baseImageRel });
      if (res && res.data_uri) {
        const img = await new Promise((resolve, reject) => {
          const i = new Image();
          i.onload = () => resolve(i);
          i.onerror = reject;
          i.src = res.data_uri;
        });
        clientImageCache.set(cacheKey, img);
        return img;
      }
    } catch (_) {}
  }
  return null;
}

// -------------------------------------------------------------
// Pure Frontend 60FPS Canvas 2D Real-time Renderer (0ms)
// -------------------------------------------------------------
function renderClientCanvasSync() {
  const t0 = performance.now();
  if (!elements.previewCanvas) return;

  elements.previewCanvas.style.display = "block";
  elements.previewImage.style.display = "none";
  elements.placeholderBox.style.display = "none";

  const canvas = elements.previewCanvas;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });

  const width = currentSelectedSticker?.width || 296;
  const height = currentSelectedSticker?.height || 256;
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  ctx.clearRect(0, 0, width, height);

  // 1. Draw base image
  if (currentBaseImage) {
    const fit = getResizeContain(currentBaseImage.width, currentBaseImage.height, width, height);
    ctx.drawImage(currentBaseImage, fit.x, fit.y, fit.w, fit.h);
  } else {
    ctx.fillStyle = "#1e2229";
    ctx.fillRect(0, 0, width, height);
  }

  const text = elements.textInput.value;
  if (!text) {
    const t1 = performance.now();
    updatePreviewMeta(width, height, (t1 - t0).toFixed(1), "前端 Canvas 2D (0ms)");
    return;
  }

  // 2. Measure & layout
  let curFontSize = parseFloat(elements.fontSizeRange.value) || 48;
  const strokeWidthFactor = parseFloat(elements.strokeWidthRange.value) || 0.22;
  const rotateDeg = parseFloat(elements.rotateRange.value) || 0;
  const textAlign = elements.textAlignSelect.value || "center";
  const autoResize = elements.autoResizeCheck.checked;

  let lines = text.split("\n");
  const fontFamilies = `"${FONT_NAME}", "Segoe UI Emoji", "Noto Color Emoji", -apple-system, sans-serif`;

  if (autoResize) {
    for (let iter = 0; iter < 15 && curFontSize > 12; iter++) {
      ctx.font = `${curFontSize}px ${fontFamilies}`;
      const lineMetrics = lines.map(line => {
        const m = ctx.measureText(line);
        const ascent = m.actualBoundingBoxAscent || curFontSize * 0.8;
        const descent = m.actualBoundingBoxDescent || curFontSize * 0.2;
        return { w: m.width, h: ascent + descent, ascent, descent };
      });
      const maxLineW = Math.max(...lineMetrics.map(m => m.w), 1);
      const totalH = lineMetrics.reduce((acc, m) => acc + m.h, 0);

      const strokeW = curFontSize * strokeWidthFactor;
      const pad = strokeW * 2 + 10;
      const offW = Math.ceil(maxLineW + pad * 2);
      const offH = Math.ceil(totalH + pad * 2);
      const cx = offW / 2;
      const cy = offH / 2;

      let drawOffsetX = -cx;
      if (textAlign === "left") drawOffsetX = -pad;
      else if (textAlign === "right") drawOffsetX = -offW + pad;

      const curX = elements.textXInput.value !== "" ? parseFloat(elements.textXInput.value) : (currentSelectedSticker?.text_x ?? 148);
      const curY = elements.textYInput.value !== "" ? parseFloat(elements.textYInput.value) : (currentSelectedSticker?.text_y ?? 58);

      const aabb = calcRotatedAABB(
        [curX + drawOffsetX, curY - cy, offW, offH],
        { x: curX, y: curY },
        rotateDeg
      );

      const overflowX = aabb.minX < 0 || aabb.maxX > width;
      const overflowY = aabb.minY < 0 || aabb.maxY > height;
      if (overflowX || overflowY) {
        curFontSize = Math.floor(curFontSize * 0.92);
      } else {
        break;
      }
    }
  }

  // 3. Render onto offscreen canvas
  ctx.font = `${curFontSize}px ${fontFamilies}`;
  const strokeW = curFontSize * strokeWidthFactor;
  const lineMetrics = lines.map(line => {
    const m = ctx.measureText(line);
    const ascent = m.actualBoundingBoxAscent || curFontSize * 0.8;
    const descent = m.actualBoundingBoxDescent || curFontSize * 0.2;
    return { w: m.width, h: ascent + descent, ascent, descent };
  });
  const maxLineW = Math.max(...lineMetrics.map(m => m.w), 1);
  const totalH = lineMetrics.reduce((acc, m) => acc + m.h, 0);

  const pad = strokeW * 2 + 16;
  const offW = Math.ceil(maxLineW + pad * 2);
  const offH = Math.ceil(totalH + pad * 2);
  const cx = offW / 2;
  const cy = offH / 2;

  const { offCtx } = getOffscreenCanvas(offW, offH);
  offCtx.font = `${curFontSize}px ${fontFamilies}`;
  offCtx.textBaseline = "middle";
  offCtx.textAlign = "center";

  let startY = cy - totalH / 2;
  const textColorHex = elements.textColorHex.value || "#1a1a1a";
  const strokeColorHex = elements.strokeColorHex.value || "#ffffff";

  // Stroke pass
  if (strokeW > 0) {
    offCtx.strokeStyle = strokeColorHex;
    offCtx.lineWidth = strokeW * 2;
    offCtx.lineJoin = "round";
    offCtx.lineCap = "round";
    let curY = startY;
    for (let i = 0; i < lines.length; i++) {
      const lineH = lineMetrics[i].h;
      offCtx.strokeText(lines[i], cx, curY + lineH / 2);
      curY += lineH;
    }
  }

  // Fill pass
  offCtx.fillStyle = textColorHex;
  let curY = startY;
  for (let i = 0; i < lines.length; i++) {
    const lineH = lineMetrics[i].h;
    offCtx.fillText(lines[i], cx, curY + lineH / 2);
    curY += lineH;
  }

  // Fill inner enclosed loops to prevent background leakage
  if (strokeW > 0) {
    fillInnerCounters(offCtx, offW, offH, hexToRgba(strokeColorHex));
  }

  // 4. Draw rotated onto target canvas
  const curX = elements.textXInput.value !== "" ? parseFloat(elements.textXInput.value) : (currentSelectedSticker?.text_x ?? 148);
  const curYPos = elements.textYInput.value !== "" ? parseFloat(elements.textYInput.value) : (currentSelectedSticker?.text_y ?? 58);

  ctx.save();
  ctx.translate(curX, curYPos);
  ctx.rotate((rotateDeg * Math.PI) / 180);

  let drawOffsetX = -cx;
  if (textAlign === "left") drawOffsetX = -pad;
  else if (textAlign === "right") drawOffsetX = -offW + pad;

  ctx.drawImage(offscreenCanvas, drawOffsetX, -cy);
  ctx.restore();

  // Debug border
  if (elements.debugCheck && elements.debugCheck.checked) {
    ctx.strokeStyle = "rgba(239, 68, 68, 0.8)";
    ctx.lineWidth = 1;
    ctx.strokeRect(curX + drawOffsetX, curYPos - cy, offW, offH);
  }

  const t1 = performance.now();
  updatePreviewMeta(width, height, (t1 - t0).toFixed(1), "前端 Canvas 2D (0ms)");
}

function updatePreviewMeta(width, height, durationMs, engineText) {
  elements.renderTimeBadge.textContent = `⚡ ${engineText} · ${durationMs}ms`;
  elements.renderTimeBadge.className = "badge badge-success";

  elements.badgePack.textContent = `包: ${elements.packSelect.value} / ${elements.stickerSelect.value}`;
  elements.badgeSize.textContent = `分辨率: ${width} × ${height}`;
  elements.badgeFilesize.textContent = `引擎: ${engineText}`;
  elements.metaTagsBox.style.display = "flex";

  elements.btnDownload.disabled = false;
  elements.btnCopy.disabled = false;
}

// -------------------------------------------------------------
// Real-time Animation Frame Dispatcher
// -------------------------------------------------------------
function requestRender() {
  if (elements.livePreviewCheck && !elements.livePreviewCheck.checked) return;

  if (elements.clientRenderCheck && elements.clientRenderCheck.checked) {
    // Pure Frontend Rendering (GPU-accelerated, 0ms)
    if (rafId) return;
    rafId = requestAnimationFrame(() => {
      rafId = null;
      renderClientCanvasSync();
    });
  } else {
    // Server API Rendering
    clearTimeout(liveDebounceTimer);
    liveDebounceTimer = setTimeout(() => {
      generateSticker(true);
    }, 150);
  }
}

function scheduleLivePreview(delayMs = 0) {
  requestRender();
}

// -------------------------------------------------------------
// UI Event Bindings
// -------------------------------------------------------------
// Tab Switching
elements.tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    const target = tab.dataset.tab;
    elements.tabs.forEach((t) => t.classList.remove("active"));
    elements.tabContents.forEach((c) => c.classList.remove("active"));
    tab.classList.add("active");
    const activePanel = document.getElementById(target);
    if (activePanel) activePanel.classList.add("active");
  });
});

// Color Pickers
elements.textColorPicker.addEventListener("input", (e) => {
  elements.textColorHex.value = e.target.value;
  requestRender();
});
elements.textColorHex.addEventListener("input", (e) => {
  elements.textColorPicker.value = e.target.value;
  requestRender();
});
elements.strokeColorPicker.addEventListener("input", (e) => {
  elements.strokeColorHex.value = e.target.value;
  requestRender();
});
elements.strokeColorHex.addEventListener("input", (e) => {
  elements.strokeColorPicker.value = e.target.value;
  requestRender();
});

// Sliders & Number inputs
elements.fontSizeRange.addEventListener("input", (e) => {
  elements.fontSizeVal.textContent = `${e.target.value}px`;
  requestRender();
});
elements.rotateRange.addEventListener("input", (e) => {
  elements.rotateVal.textContent = `${e.target.value}°`;
  requestRender();
});
elements.strokeWidthRange.addEventListener("input", (e) => {
  elements.strokeWidthVal.textContent = e.target.value;
  requestRender();
});

elements.textInput.addEventListener("input", requestRender);
elements.textAlignSelect.addEventListener("change", requestRender);
elements.textXInput.addEventListener("input", requestRender);
elements.textYInput.addEventListener("input", requestRender);
elements.fontStyleSelect.addEventListener("change", requestRender);
elements.imageFormatSelect.addEventListener("change", requestRender);
elements.autoResizeCheck.addEventListener("change", requestRender);
elements.debugCheck.addEventListener("change", requestRender);

if (elements.clientRenderCheck) {
  elements.clientRenderCheck.addEventListener("change", () => {
    requestRender();
  });
}
if (elements.livePreviewCheck) {
  elements.livePreviewCheck.addEventListener("change", (e) => {
    if (e.target.checked) requestRender();
  });
}

// Reset parameters button (keeps text input content!)
function resetParameters() {
  if (!currentSelectedSticker) return;
  const sticker = currentSelectedSticker;

  elements.fontSizeRange.value = sticker.font_size || 48;
  elements.fontSizeVal.textContent = `${sticker.font_size || 48}px`;
  elements.rotateRange.value = Math.round(sticker.text_rotate_degrees || 0);
  elements.rotateVal.textContent = `${elements.rotateRange.value}°`;
  elements.strokeWidthRange.value = sticker.stroke_width_factor !== undefined ? sticker.stroke_width_factor : 0.22;
  elements.strokeWidthVal.textContent = elements.strokeWidthRange.value;
  elements.textAlignSelect.value = sticker.text_align || "center";
  elements.textXInput.value = sticker.text_x !== undefined ? sticker.text_x : 148;
  elements.textYInput.value = sticker.text_y !== undefined ? sticker.text_y : 58;

  const txtHex = rgbaToHex(sticker.text_color || [0, 0, 0, 255]);
  elements.textColorPicker.value = txtHex;
  elements.textColorHex.value = txtHex;

  const strokeHex = rgbaToHex(sticker.stroke_color || [255, 255, 255, 255]);
  elements.strokeColorPicker.value = strokeHex;
  elements.strokeColorHex.value = strokeHex;

  elements.imageFormatSelect.value = "png";
  elements.autoResizeCheck.checked = true;

  // Do NOT touch elements.textInput.value!

  requestRender();
}

if (elements.btnResetParams) {
  elements.btnResetParams.addEventListener("click", resetParameters);
}
if (elements.btnReset) {
  elements.btnReset.addEventListener("click", resetParameters);
}

// -------------------------------------------------------------
// Packs & Stickers Navigation
// -------------------------------------------------------------
async function loadPacksDetail() {
  try {
    const packs = await client.apiGet("packs");
    globalPacksTree = packs || {};
    const packKeys = Object.keys(globalPacksTree);

    elements.packSelect.innerHTML = "";
    if (packKeys.length === 0) {
      elements.packSelect.innerHTML = `<option value="">无可用贴纸包 (请在资源管理中安装)</option>`;
      elements.categorySelect.disabled = true;
      elements.stickerSelect.disabled = true;
      return;
    }

    elements.packSelect.innerHTML = `<option value="">-- 请选择贴纸包 --</option>`;
    packKeys.forEach((key) => {
      const p = globalPacksTree[key];
      const opt = document.createElement("option");
      opt.value = key;
      opt.textContent = `${p.name} (${key})`;
      elements.packSelect.appendChild(opt);
    });

    elements.packSelect.selectedIndex = 1;
    onPackChange();
  } catch (err) {
    logToConsole(`获取贴纸包详情失败: ${err.message}`);
  }
}

function onPackChange() {
  const packSlug = elements.packSelect.value;
  elements.categorySelect.innerHTML = `<option value="">-- 请选择分类 --</option>`;
  elements.stickerSelect.innerHTML = `<option value="">-- 请选择贴纸 --</option>`;

  if (!packSlug || !globalPacksTree[packSlug]) {
    elements.categorySelect.disabled = true;
    elements.stickerSelect.disabled = true;
    return;
  }

  const categories = Object.keys(globalPacksTree[packSlug].categories || {});
  elements.categorySelect.disabled = false;
  categories.forEach((cat) => {
    const opt = document.createElement("option");
    opt.value = cat;
    opt.textContent = cat;
    elements.categorySelect.appendChild(opt);
  });

  if (categories.length > 0) {
    elements.categorySelect.selectedIndex = 1;
    onCategoryChange();
  }
}

function onCategoryChange() {
  const packSlug = elements.packSelect.value;
  const cat = elements.categorySelect.value;
  elements.stickerSelect.innerHTML = `<option value="">-- 请选择贴纸 --</option>`;

  if (!packSlug || !cat || !globalPacksTree[packSlug]?.categories?.[cat]) {
    elements.stickerSelect.disabled = true;
    return;
  }

  const stickers = globalPacksTree[packSlug].categories[cat];
  elements.stickerSelect.disabled = false;
  stickers.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s.name;
    opt.textContent = s.name;
    elements.stickerSelect.appendChild(opt);
  });

  if (stickers.length > 0) {
    elements.stickerSelect.selectedIndex = 1;
    onStickerChange();
  }
}

async function onStickerChange() {
  const packSlug = elements.packSelect.value;
  const cat = elements.categorySelect.value;
  const stickerName = elements.stickerSelect.value;

  const stickers = globalPacksTree[packSlug]?.categories?.[cat] || [];
  currentSelectedSticker = stickers.find((s) => s.name === stickerName);

  if (!currentSelectedSticker) return;

  // Apply defaults
  elements.textInput.value = "something";
  elements.fontSizeRange.value = currentSelectedSticker.font_size || 48;
  elements.fontSizeVal.textContent = `${elements.fontSizeRange.value}px`;

  if (currentSelectedSticker.text_align) {
    elements.textAlignSelect.value = currentSelectedSticker.text_align;
  }

  const txtHex = rgbaToHex(currentSelectedSticker.text_color);
  elements.textColorPicker.value = txtHex;
  elements.textColorHex.value = txtHex;

  const strokeHex = rgbaToHex(currentSelectedSticker.stroke_color);
  elements.strokeColorPicker.value = strokeHex;
  elements.strokeColorHex.value = strokeHex;

  elements.textXInput.value = currentSelectedSticker.text_x ?? 148;
  elements.textYInput.value = currentSelectedSticker.text_y ?? 58;
  elements.rotateRange.value = Math.round(currentSelectedSticker.text_rotate_degrees || 0);
  elements.rotateVal.textContent = `${elements.rotateRange.value}°`;
  elements.strokeWidthRange.value = currentSelectedSticker.stroke_width_factor ?? 0.22;
  elements.strokeWidthVal.textContent = elements.strokeWidthRange.value;

  if (currentSelectedSticker.font_style) {
    elements.fontStyleSelect.value = currentSelectedSticker.font_style;
  }

  // Preload base image
  const cdn = currentSelectedSticker.cdn_url;
  const baseImg = currentSelectedSticker.base_image;
  loadClientImage(cdn, packSlug, baseImg).then(img => {
    currentBaseImage = img;
    requestRender();
  });

  requestRender();
}

// -------------------------------------------------------------
// Server-Side Generate Action (for Testing Backend API)
// -------------------------------------------------------------
async function generateSticker(isLive = false) {
  const packSlug = elements.packSelect.value;
  const stickerName = elements.stickerSelect.value;

  if (!packSlug || !stickerName) {
    if (!isLive) alert("请先选择贴纸包与贴纸！");
    return;
  }

  const renderSeq = ++currentRenderSeq;
  const startTime = performance.now();

  if (!isLive) {
    elements.btnGenerate.disabled = true;
    elements.btnGenerate.innerHTML = `<span class="spinner"></span> 后端生成中...`;
  }
  elements.renderTimeBadge.textContent = "后端 Skia 渲染中...";
  elements.renderTimeBadge.className = "badge badge-warning";

  const payload = {
    pack_slug: packSlug,
    sticker_name: stickerName,
    text: elements.textInput.value,
    font_size: parseFloat(elements.fontSizeRange.value),
    text_align: elements.textAlignSelect.value,
    text_color: elements.textColorHex.value,
    stroke_color: elements.strokeColorHex.value,
    stroke_width_factor: parseFloat(elements.strokeWidthRange.value),
    text_rotate_degrees: parseFloat(elements.rotateRange.value),
    font_style: elements.fontStyleSelect.value,
    image_format: elements.imageFormatSelect.value,
    auto_resize: elements.autoResizeCheck.checked,
    debug: elements.debugCheck.checked,
  };

  if (elements.textXInput.value !== "") payload.text_x = parseFloat(elements.textXInput.value);
  if (elements.textYInput.value !== "") payload.text_y = parseFloat(elements.textYInput.value);

  try {
    const data = await client.apiPost("generate", payload);
    if (renderSeq !== currentRenderSeq) return;

    const duration = Math.round(performance.now() - startTime);
    if (data.data_uri) {
      currentGeneratedImageUri = data.data_uri;
      elements.previewImage.src = data.data_uri;
      elements.previewImage.style.display = "block";
      elements.previewCanvas.style.display = "none";
      elements.placeholderBox.style.display = "none";

      updatePreviewMeta(data.width, data.height, duration, "后端 Skia API");
    }
  } catch (err) {
    if (renderSeq !== currentRenderSeq) return;
    elements.renderTimeBadge.textContent = "后端渲染失败";
    elements.renderTimeBadge.className = "badge badge-warning";
    logToConsole(`生成失败: ${err.message}`);
    if (!isLive) alert(`生成失败: ${err.message}`);
  } finally {
    if (!isLive) {
      elements.btnGenerate.disabled = false;
      elements.btnGenerate.innerHTML = `<span>🧪 测试后端 Skia 生成</span>`;
    }
  }
}

// Download image
elements.btnDownload.addEventListener("click", () => {
  const isCanvas = elements.previewCanvas && elements.previewCanvas.style.display !== "none";
  if (isCanvas) {
    const format = elements.imageFormatSelect.value || "png";
    const url = elements.previewCanvas.toDataURL(`image/${format}`);
    const a = document.createElement("a");
    a.href = url;
    a.download = `sticker_${elements.stickerSelect.value}_${Date.now()}.${format}`;
    a.click();
  } else if (currentGeneratedImageUri || elements.previewImage.src) {
    const a = document.createElement("a");
    a.href = currentGeneratedImageUri || elements.previewImage.src;
    const ext = elements.imageFormatSelect.value || "png";
    a.download = `sticker_${elements.stickerSelect.value}_${Date.now()}.${ext}`;
    a.click();
  }
});

// Copy image to clipboard
elements.btnCopy.addEventListener("click", async () => {
  const isCanvas = elements.previewCanvas && elements.previewCanvas.style.display !== "none";
  try {
    let blob = null;
    if (isCanvas) {
      blob = await new Promise(resolve => elements.previewCanvas.toBlob(resolve, "image/png"));
    } else if (currentGeneratedImageUri) {
      const res = await fetch(currentGeneratedImageUri);
      blob = await res.blob();
    }
    if (!blob) throw new Error("无可用图片数据");
    await navigator.clipboard.write([
      new ClipboardItem({ "image/png": blob }),
    ]);
    const oldText = elements.btnCopy.innerHTML;
    elements.btnCopy.innerHTML = `<span>✅ 已复制！</span>`;
    setTimeout(() => {
      elements.btnCopy.innerHTML = oldText;
    }, 2000);
  } catch (err) {
    console.warn("Clipboard write failed:", err);
    alert("复制图片失败（浏览器权限限制），请直接使用下载功能或右键另存为。");
  }
});

// Event Listeners for selects & buttons
elements.packSelect.addEventListener("change", onPackChange);
elements.categorySelect.addEventListener("change", onCategoryChange);
elements.stickerSelect.addEventListener("change", onStickerChange);
elements.btnGenerate.addEventListener("click", () => generateSticker(false));

elements.textInput.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault();
    if (elements.clientRenderCheck && elements.clientRenderCheck.checked) {
      requestRender();
    } else {
      generateSticker(false);
    }
  }
});

// -------------------------------------------------------------
// Resources Tab Management
// -------------------------------------------------------------
async function loadStatus() {
  try {
    const data = await client.apiGet("status");
    if (data.emoji_font && data.emoji_font.exists) {
      elements.emojiStatusBadge.textContent = `已就绪 (${data.emoji_font.size_mb} MB)`;
      elements.emojiStatusBadge.className = "badge badge-success";
      elements.emojiStatusDesc.textContent = `路径: ${data.emoji_font.path}`;
    } else {
      elements.emojiStatusBadge.textContent = "未下载";
      elements.emojiStatusBadge.className = "badge badge-warning";
      elements.emojiStatusDesc.textContent = "缺少 Emoji 字体，输入表情时将自动回退到常规字体";
    }

    if (data.primary_font && data.primary_font.exists) {
      elements.primaryStatusBadge.textContent = "已就绪";
      elements.primaryStatusBadge.className = "badge badge-success";
      elements.primaryStatusDesc.textContent = `路径: ${data.primary_font.path}`;
    } else {
      elements.primaryStatusBadge.textContent = "未安装 (通过 PJSK 贴纸包获取)";
      elements.primaryStatusBadge.className = "badge badge-warning";
    }

    if (data.config) {
      elements.cfgMirrorPreset.textContent = data.config.mirror_preset || "-";
      elements.cfgEmojiFontUrl.textContent = data.config.emoji_font_url || "-";
      elements.cfgHubManifestUrl.textContent = data.config.hub_manifest_url || "-";
      elements.cfgGithubUrlTemplate.textContent = data.config.github_url_template || "-";
      elements.cfgProxy.textContent = data.config.proxy || "(未设置)";
    }
  } catch (err) {
    logToConsole(`加载状态失败: ${err.message}`);
  }
}

// Pull Emoji Font
elements.btnPullEmojiFont.addEventListener("click", async () => {
  const chosenUrl = elements.emojiFontSourceSelect.value;
  elements.btnPullEmojiFont.disabled = true;
  elements.btnPullEmojiFont.innerHTML = `<span class="spinner"></span> 正在拉取...`;
  logToConsole(`正在从所选源拉取 Emoji 字体: ${chosenUrl}...`);

  try {
    const res = await client.apiPost("fetch_emoji_font", {
      url: chosenUrl,
      force: true,
    });
    logToConsole(`拉取结果: ${res.message || "完成"} (耗时: ${res.elapsed_seconds || 0}s)`);
    await loadStatus();
  } catch (err) {
    logToConsole(`拉取失败: ${err.message}`);
    alert(`下载失败: ${err.message}`);
  } finally {
    elements.btnPullEmojiFont.disabled = false;
    elements.btnPullEmojiFont.innerHTML = `<span>⬇️ 重新拉取字体</span>`;
  }
});

// Load Hub and Local Resources
async function loadResourcesTable() {
  try {
    const statusData = await client.apiGet("status");
    const localPacks = statusData.packs || [];
    const localMap = {};
    localPacks.forEach((p) => { localMap[p.slug] = p; });

    let hubPacks = [];
    try {
      const hubRes = await client.apiGet("hub");
      hubPacks = hubRes.packs || [];
    } catch (e) {
      logToConsole(`获取 Hub 失败: ${e.message}`);
    }

    const allSlugs = Array.from(new Set([...Object.keys(localMap), ...hubPacks.map(p => p.slug)]));
    elements.packsTableBody.innerHTML = "";

    allSlugs.forEach((slug) => {
      const lp = localMap[slug];
      const hp = hubPacks.find(p => p.slug === slug);
      const name = lp?.name || hp?.name || slug;
      const desc = lp?.description || hp?.description || "-";
      const count = lp ? lp.stickers_count : (hp?.stickers_count || 0);

      let statusBadge = "";
      if (lp) {
        if (lp.unavailable) {
          statusBadge = `<span class="badge badge-warning">异常/未下载全</span>`;
        } else if (lp.disabled) {
          statusBadge = `<span class="badge badge-muted">已禁用</span>`;
        } else {
          statusBadge = `<span class="badge badge-success">已安装 (${count}款)</span>`;
        }
      } else {
        statusBadge = `<span class="badge badge-primary">在线 Hub 可用</span>`;
      }

      let actionBtn = "";
      if (lp) {
        actionBtn = `
          <button class="btn btn-secondary btn-sm" onclick="installPack('${slug}', true)">🔄 重新下载</button>
        `;
      } else {
        actionBtn = `
          <button class="btn btn-primary btn-sm" onclick="installPack('${slug}', false)">⬇️ 安装</button>
        `;
      }

      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td style="font-weight: 600;">${slug}</td>
        <td>${name}</td>
        <td>${desc}</td>
        <td>${statusBadge}</td>
        <td style="text-align: right;">${actionBtn}</td>
      `;
      elements.packsTableBody.appendChild(tr);
    });
  } catch (err) {
    logToConsole(`加载资源表格失败: ${err.message}`);
  }
}

window.installPack = async function (slug, reinstall = false) {
  logToConsole(`正在${reinstall ? "重新下载" : "安装"}贴纸包: ${slug}...`);
  try {
    const res = await client.apiPost("install", { slug });
    logToConsole(`贴纸包 ${slug} 安装完成: ${res.message || "成功"}`);
    await loadStatus();
    await loadPacksDetail();
    await loadResourcesTable();
  } catch (err) {
    logToConsole(`安装失败: ${err.message}`);
    alert(`安装失败: ${err.message}`);
  }
};

// Reload packs
elements.btnReloadPacks.addEventListener("click", async () => {
  elements.btnReloadPacks.disabled = true;
  logToConsole("正在重载本地贴纸包与字体缓存...");
  try {
    const res = await client.apiPost("reload");
    logToConsole(`重载完成！已加载: ${res.loaded_packs_count} 个贴纸包`);
    await loadStatus();
    await loadPacksDetail();
    await loadResourcesTable();
  } catch (err) {
    logToConsole(`重载失败: ${err.message}`);
  } finally {
    elements.btnReloadPacks.disabled = false;
  }
});

// Install all hub packs
elements.btnInstallAllHub.addEventListener("click", async () => {
  if (!confirm("确定要一次性安装在线 Hub 中的全部贴纸包吗？这可能需要一些时间下载图片和资源。")) return;
  elements.btnInstallAllHub.disabled = true;
  logToConsole("正在拉取在线 Hub 并下载安装所有贴纸包...");
  try {
    const res = await client.apiPost("install", { all: true });
    logToConsole(`全量安装完成！成功: ${res.succeed?.length || 0}, 失败: ${res.failed?.length || 0}`);
    await loadStatus();
    await loadPacksDetail();
    await loadResourcesTable();
  } catch (err) {
    logToConsole(`安装全部失败: ${err.message}`);
    alert(`安装失败: ${err.message}`);
  } finally {
    elements.btnInstallAllHub.disabled = false;
  }
});

// Switch Mirrors
elements.btnMirrors.forEach((btn) => {
  btn.addEventListener("click", async () => {
    const preset = btn.dataset.preset;
    logToConsole(`正在切换预设镜像源为: ${preset}...`);
    try {
      const res = await client.apiPost("switch_mirror", { preset });
      logToConsole(`镜像源已切换成功！当前模板: ${res.github_url_template}`);
      await loadStatus();
      alert(`镜像预设已成功切换为 [${preset}]！`);
    } catch (err) {
      logToConsole(`切换镜像失败: ${err.message}`);
      alert(`切换失败: ${err.message}`);
    }
  });
});

// Bootstrap
async function bootstrap() {
  await client.init();
  initWebFont(); // Load font from CDN / CacheStorage asynchronously
  await loadStatus();
  await loadPacksDetail();
  await loadResourcesTable();
  logToConsole("Playground 工作台已就绪 (纯前端 Canvas 2D 实时加速已开启)");
}

bootstrap();
