// Meme Stickers Playground JS
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
let currentGeneratedImageUri = null;

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
  // Preview
  previewContainer: document.getElementById("preview-container"),
  placeholderBox: document.getElementById("placeholder-box"),
  previewImage: document.getElementById("preview-image"),
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
  elements.logConsole.textContent = `[${time}] ${msg}\n` + elements.logConsole.textContent;
}

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

// Real-time Preview Scheduler & Concurrency Control
let liveDebounceTimer = null;
let currentRenderSeq = 0;

function scheduleLivePreview(delayMs = 120) {
  if (elements.livePreviewCheck && !elements.livePreviewCheck.checked) {
    return;
  }
  clearTimeout(liveDebounceTimer);
  liveDebounceTimer = setTimeout(() => {
    generateSticker(true);
  }, delayMs);
}

// Sync Color Pickers
elements.textColorPicker.addEventListener("input", (e) => {
  elements.textColorHex.value = e.target.value;
  scheduleLivePreview(60);
});
elements.textColorHex.addEventListener("input", (e) => {
  elements.textColorPicker.value = e.target.value;
  scheduleLivePreview(120);
});
elements.textColorHex.addEventListener("change", (e) => {
  elements.textColorPicker.value = e.target.value;
  scheduleLivePreview(0);
});
elements.strokeColorPicker.addEventListener("input", (e) => {
  elements.strokeColorHex.value = e.target.value;
  scheduleLivePreview(60);
});
elements.strokeColorHex.addEventListener("input", (e) => {
  elements.strokeColorPicker.value = e.target.value;
  scheduleLivePreview(120);
});
elements.strokeColorHex.addEventListener("change", (e) => {
  elements.strokeColorPicker.value = e.target.value;
  scheduleLivePreview(0);
});

// Sync Sliders
elements.fontSizeRange.addEventListener("input", (e) => {
  elements.fontSizeVal.textContent = `${e.target.value}px`;
  scheduleLivePreview(60);
});
elements.rotateRange.addEventListener("input", (e) => {
  elements.rotateVal.textContent = `${e.target.value}°`;
  scheduleLivePreview(60);
});
elements.strokeWidthRange.addEventListener("input", (e) => {
  elements.strokeWidthVal.textContent = e.target.value;
  scheduleLivePreview(60);
});

// Load Status & Config
async function loadStatus() {
  try {
    const data = await client.apiGet("status");
    // Emoji Font Badge
    if (data.emoji_font && data.emoji_font.exists) {
      elements.emojiStatusBadge.textContent = `已就绪 (${data.emoji_font.size_mb} MB)`;
      elements.emojiStatusBadge.className = "badge badge-success";
      elements.emojiStatusDesc.textContent = `路径: ${data.emoji_font.path}`;
    } else {
      elements.emojiStatusBadge.textContent = "未下载";
      elements.emojiStatusBadge.className = "badge badge-warning";
      elements.emojiStatusDesc.textContent = "缺少 Emoji 字体，输入表情时将自动回退到常规字体";
    }

    // Primary Font Badge
    if (data.primary_font && data.primary_font.exists) {
      elements.primaryStatusBadge.textContent = "已就绪";
      elements.primaryStatusBadge.className = "badge badge-success";
      elements.primaryStatusDesc.textContent = `路径: ${data.primary_font.path}`;
    } else {
      elements.primaryStatusBadge.textContent = "未安装 (通过 PJSK 贴纸包获取)";
      elements.primaryStatusBadge.className = "badge badge-warning";
    }

    // Mirrors display
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

// Load Packs Tree for Playground
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

    // 默认选中第一个
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

function rgbaToHex(rgba) {
  if (!rgba || rgba.length < 3) return "#000000";
  const r = rgba[0].toString(16).padStart(2, "0");
  const g = rgba[1].toString(16).padStart(2, "0");
  const b = rgba[2].toString(16).padStart(2, "0");
  return `#${r}${g}${b}`;
}

function onStickerChange() {
  const packSlug = elements.packSelect.value;
  const cat = elements.categorySelect.value;
  const stickerName = elements.stickerSelect.value;

  const stickers = globalPacksTree[packSlug]?.categories?.[cat] || [];
  currentSelectedSticker = stickers.find((s) => s.name === stickerName);

  if (!currentSelectedSticker) return;

  // 填入贴纸默认值
  elements.textInput.value = currentSelectedSticker.text || "";
  elements.fontSizeRange.value = currentSelectedSticker.font_size || 48;
  elements.fontSizeVal.textContent = `${currentSelectedSticker.font_size || 48}px`;

  if (currentSelectedSticker.text_align) {
    elements.textAlignSelect.value = currentSelectedSticker.text_align;
  }

  const txtHex = rgbaToHex(currentSelectedSticker.text_color);
  elements.textColorPicker.value = txtHex;
  elements.textColorHex.value = txtHex;

  const strokeHex = rgbaToHex(currentSelectedSticker.stroke_color);
  elements.strokeColorPicker.value = strokeHex;
  elements.strokeColorHex.value = strokeHex;

  elements.textXInput.value = currentSelectedSticker.text_x ?? "";
  elements.textYInput.value = currentSelectedSticker.text_y ?? "";
  elements.rotateRange.value = currentSelectedSticker.text_rotate_degrees || 0;
  elements.rotateVal.textContent = `${currentSelectedSticker.text_rotate_degrees || 0}°`;
  elements.strokeWidthRange.value = currentSelectedSticker.stroke_width_factor ?? 0.08;
  elements.strokeWidthVal.textContent = currentSelectedSticker.stroke_width_factor ?? 0.08;

  if (currentSelectedSticker.font_style) {
    elements.fontStyleSelect.value = currentSelectedSticker.font_style;
  }

  // 选定贴纸后立即在画布上实时渲染初始预览
  scheduleLivePreview(0);
}

// Generate Sticker Action
async function generateSticker(isLive = false) {
  const packSlug = elements.packSelect.value;
  const stickerName = elements.stickerSelect.value;

  if (!packSlug || !stickerName) {
    if (!isLive) {
      alert("请先选择贴纸包与贴纸！");
    }
    return;
  }

  const renderSeq = ++currentRenderSeq;
  const startTime = performance.now();

  if (!isLive) {
    elements.btnGenerate.disabled = true;
    elements.btnGenerate.innerHTML = `<span class="spinner"></span> 渲染中...`;
  }
  elements.previewImage.classList.add("rendering");
  elements.renderTimeBadge.textContent = isLive ? "⚡ 实时渲染中..." : "渲染中...";
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

  if (elements.textXInput.value !== "") {
    payload.text_x = parseFloat(elements.textXInput.value);
  }
  if (elements.textYInput.value !== "") {
    payload.text_y = parseFloat(elements.textYInput.value);
  }

  try {
    const data = await client.apiPost("generate", payload);
    // 丢弃并发过程中过期的渲染请求响应
    if (renderSeq !== currentRenderSeq) {
      return;
    }

    const duration = Math.round(performance.now() - startTime);

    if (data.data_uri) {
      currentGeneratedImageUri = data.data_uri;
      elements.previewImage.src = data.data_uri;
      elements.previewImage.style.display = "block";
      elements.placeholderBox.style.display = "none";

      elements.renderTimeBadge.textContent = isLive ? `⚡ 实时 (${duration}ms)` : `就绪 (${duration}ms)`;
      elements.renderTimeBadge.className = "badge badge-success";

      elements.badgePack.textContent = `包: ${packSlug} / ${stickerName}`;
      elements.badgeSize.textContent = `分辨率: ${data.width} × ${data.height}`;
      elements.badgeFilesize.textContent = `大小: ${(data.size_bytes / 1024).toFixed(1)} KB (${data.format.toUpperCase()})`;
      elements.metaTagsBox.style.display = "flex";

      elements.btnDownload.disabled = false;
      elements.btnCopy.disabled = false;
    }
  } catch (err) {
    if (renderSeq !== currentRenderSeq) return;
    elements.renderTimeBadge.textContent = "渲染失败";
    elements.renderTimeBadge.className = "badge badge-warning";
    if (!isLive) {
      alert(`生成失败: ${err.message}`);
    }
    logToConsole(`生成失败: ${err.message}`);
  } finally {
    if (renderSeq === currentRenderSeq) {
      elements.previewImage.classList.remove("rendering");
    }
    if (!isLive) {
      elements.btnGenerate.disabled = false;
      elements.btnGenerate.innerHTML = `<span>🎨 立即渲染 / 刷新</span>`;
    }
  }
}

// Download image
elements.btnDownload.addEventListener("click", () => {
  if (!currentGeneratedImageUri) return;
  const a = document.createElement("a");
  a.href = currentGeneratedImageUri;
  const ext = elements.imageFormatSelect.value || "png";
  a.download = `sticker_${elements.stickerSelect.value}_${Date.now()}.${ext}`;
  a.click();
});

// Copy image to clipboard
elements.btnCopy.addEventListener("click", async () => {
  if (!currentGeneratedImageUri) return;
  try {
    const res = await fetch(currentGeneratedImageUri);
    const blob = await res.blob();
    await navigator.clipboard.write([
      new ClipboardItem({ [blob.type]: blob }),
    ]);
    const oldText = elements.btnCopy.innerHTML;
    elements.btnCopy.innerHTML = `<span>✅ 已复制！</span>`;
    setTimeout(() => {
      elements.btnCopy.innerHTML = oldText;
    }, 2000);
  } catch (err) {
    alert("复制图片失败（浏览器权限限制），请直接使用下载功能或右键另存为。");
  }
});

// Reset params
elements.btnReset.addEventListener("click", () => {
  if (currentSelectedSticker) {
    onStickerChange();
  }
});

// Event Listeners for selects & buttons
elements.packSelect.addEventListener("change", onPackChange);
elements.categorySelect.addEventListener("change", onCategoryChange);
elements.stickerSelect.addEventListener("change", onStickerChange);
elements.btnGenerate.addEventListener("click", () => generateSticker(false));

// 实时监听输入与配置变动
elements.textInput.addEventListener("input", () => scheduleLivePreview(150));
elements.textAlignSelect.addEventListener("change", () => scheduleLivePreview(0));
elements.textXInput.addEventListener("input", () => scheduleLivePreview(120));
elements.textYInput.addEventListener("input", () => scheduleLivePreview(120));
elements.fontStyleSelect.addEventListener("change", () => scheduleLivePreview(0));
elements.imageFormatSelect.addEventListener("change", () => scheduleLivePreview(0));
elements.autoResizeCheck.addEventListener("change", () => scheduleLivePreview(0));
elements.debugCheck.addEventListener("change", () => scheduleLivePreview(0));
if (elements.livePreviewCheck) {
  elements.livePreviewCheck.addEventListener("change", (e) => {
    if (e.target.checked) scheduleLivePreview(0);
  });
}

elements.textInput.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault();
    generateSticker(false);
  }
});

// Pull Emoji Font
elements.btnPullEmojiFont.addEventListener("click", async () => {
  const chosenUrl = elements.emojiFontSourceSelect.value;
  elements.btnPullEmojiFont.disabled = true;
  elements.btnPullEmojiFont.innerHTML = `<span class="spinner"></span> 正在拉取...`;
  logToConsole(`正在通过 ${chosenUrl} 拉取 Emoji 字体...`);

  try {
    const res = await client.apiPost("fetch_emoji_font", {
      force: true,
      url: chosenUrl,
    });
    logToConsole(`Emoji 字体获取成功！大小: ${res.size_mb} MB，路径: ${res.path}`);
    await loadStatus();
  } catch (err) {
    logToConsole(`拉取 Emoji 字体失败: ${err.message}`);
    alert(`拉取 Emoji 字体失败: ${err.message}`);
  } finally {
    elements.btnPullEmojiFont.disabled = false;
    elements.btnPullEmojiFont.innerHTML = `<span>⬇️ 重新拉取字体</span>`;
  }
});

// Load Packs Table & Hub
async function loadResourcesTable() {
  elements.packsTableBody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted);"><span class="spinner"></span> 正在加载资源数据...</td></tr>`;

  try {
    const statusData = await client.apiGet("status");
    const installedList = statusData.installed_packs || [];
    const installedMap = {};
    installedList.forEach((p) => {
      installedMap[p.slug] = p;
    });

    let hubList = [];
    try {
      hubList = (await client.apiGet("hub")) || [];
    } catch (e) {
      logToConsole(`获取在线 Hub 列表警告: ${e.message}`);
    }

    const allSlugs = new Set([
      ...installedList.map((x) => x.slug),
      ...hubList.map((x) => x.slug),
    ]);

    elements.packsTableBody.innerHTML = "";
    if (allSlugs.size === 0) {
      elements.packsTableBody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">暂无任何贴纸包数据</td></tr>`;
      return;
    }

    allSlugs.forEach((slug) => {
      const inst = installedMap[slug];
      const hubItem = hubList.find((x) => x.slug === slug);
      const isInstalled = !!inst;

      const tr = document.createElement("tr");

      const nameText = inst ? inst.name : (hubItem ? `${slug} (在线)` : slug);
      const statusBadge = isInstalled
        ? `<span class="badge badge-success">已安装</span>`
        : `<span class="badge badge-warning">未安装</span>`;
      const stickerCount = inst ? inst.stickers_count : "-";
      const catList = inst ? (inst.categories || []).join(", ") : "-";

      let actionBtn = "";
      if (isInstalled) {
        actionBtn = `<button class="btn btn-secondary btn-sm" onclick="window.installPack('${slug}', true)">🔄 重新更新</button>`;
      } else {
        actionBtn = `<button class="btn btn-primary btn-sm" onclick="window.installPack('${slug}', false)">⬇️ 在线安装</button>`;
      }

      tr.innerHTML = `
        <td style="font-weight: 600;">${slug}</td>
        <td>${nameText}</td>
        <td>${statusBadge}</td>
        <td>${stickerCount}</td>
        <td style="max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${catList}">${catList}</td>
        <td>${actionBtn}</td>
      `;
      elements.packsTableBody.appendChild(tr);
    });
  } catch (err) {
    elements.packsTableBody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--danger-color);">加载失败: ${err.message}</td></tr>`;
  }
}

// Expose install function to window
window.installPack = async function (slug, isUpdate) {
  const actionText = isUpdate ? "更新" : "安装";
  logToConsole(`开始${actionText}贴纸包 ${slug}...`);
  try {
    const res = await client.apiPost("install", { slugs: [slug] });
    logToConsole(`${actionText}贴纸包 ${slug} 结果: 成功: ${res.succeed?.length || 0}, 失败: ${res.failed?.length || 0}`);
    await loadStatus();
    await loadPacksDetail();
    await loadResourcesTable();
  } catch (err) {
    logToConsole(`${actionText}失败: ${err.message}`);
    alert(`${actionText}失败: ${err.message}`);
  }
};

// Reload packs
elements.btnReloadPacks.addEventListener("click", async () => {
  elements.btnReloadPacks.disabled = true;
  logToConsole("正在重新加载本地所有贴纸包索引...");
  try {
    const res = await client.apiPost("reload");
    logToConsole(`重载完成！成功: ${res.succeed}, 失败: ${res.failed}`);
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

// Init
async function bootstrap() {
  await client.init();
  await loadStatus();
  await loadPacksDetail();
  await loadResourcesTable();
  logToConsole("Playground 工作台已就绪");
}

bootstrap();
