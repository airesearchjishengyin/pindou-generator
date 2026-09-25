/* 拼豆图纸生成器 — 前端逻辑 */
const $ = (s) => document.querySelector(s);
const state = {
  file: null, fileURL: null, job: null, stats: null, pattern: null,
  // 施工图纸 canvas
  gz: 1,
  // 按色施工
  colorSel: null, doneSet: new Set(), hideDone: true,
  // 精修
  editSel: null, editHistory: [], editBase: null,
  // 熨烫
  ironSel: "semi",
  ironMethods: [],
};

/* ================= 上传 ================= */
const dropZone = $("#dropZone"), fileInput = $("#fileInput");
dropZone.addEventListener("click", () => fileInput.click());
$("#btnChange").addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => setFile(fileInput.files[0]));
["dragover", "dragenter"].forEach(ev =>
  dropZone.addEventListener(ev, e => { e.preventDefault(); dropZone.classList.add("drag"); }));
["dragleave", "drop"].forEach(ev =>
  dropZone.addEventListener(ev, e => { e.preventDefault(); dropZone.classList.remove("drag"); }));
dropZone.addEventListener("drop", e => setFile(e.dataTransfer.files[0]));

function setFile(f) {
  if (!f || !f.type.startsWith("image/")) { showError("请选择图片文件"); return; }
  hideError();
  state.file = f;
  if (state.fileURL) URL.revokeObjectURL(state.fileURL);
  state.fileURL = URL.createObjectURL(f);
  $("#previewImg").src = state.fileURL;
  $("#cmpOrig").src = state.fileURL;
  dropZone.classList.add("hidden");
  $("#previewWrap").classList.remove("hidden");
}

$("#mode").addEventListener("change", () => {
  $("#colorsLabel").classList.toggle("hidden", $("#mode").value !== "limited");
});

/* ================= 生成 ================= */
$("#btnGo").addEventListener("click", async () => {
  if (!state.file) { showError("先选一张图片"); return; }
  hideError();
  const btn = $("#btnGo");
  btn.disabled = true;
  $("#loading").classList.remove("hidden");

  const fd = new FormData();
  fd.append("image", state.file);
  fd.append("width", $("#width").value);
  fd.append("mode", $("#mode").value);
  fd.append("metric", $("#metric").value);
  fd.append("series", $("#series").value);
  fd.append("n_colors", $("#colors").value);
  fd.append("algo", $("#algo").value);
  fd.append("despeckle_n", $("#despeckle").value);
  fd.append("merge_th", $("#mergeTh").value);
  fd.append("bg_remove", $("#bgRemove").value);
  // AI 像素化 = 付费功能: 本地无有效码时弹付费面板 (服务端还会再强制校验扣次)
  const wantAi = $("#aiPixel").value === "1";
  const savedCode = localStorage.getItem("pindou_code") || "";
  if (wantAi && !savedCode) {
    $("#paywall").classList.remove("hidden");
    btn.disabled = false; $("#loading").classList.add("hidden");
    return;
  }
  fd.append("ai_pixel", $("#aiPixel").value);
  if (wantAi) fd.append("license_code", savedCode);

  try {
    const r = await fetch("/api/generate", { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "生成失败");
    state.job = data.job;
    state.stats = data;
    state.doneSet = new Set();
    state.editHistory = [];
    await loadPattern();
    renderResult();
  } catch (e) {
    showError(e.message);
  } finally {
    btn.disabled = false;
    $("#loading").classList.add("hidden");
  }
});

async function loadPattern() {
  const r = await fetch(`/api/pattern/${state.job}`);
  if (!r.ok) throw new Error("pattern.json 加载失败");
  state.pattern = await r.json();
  state.editBase = state.pattern.grid.map(r => [...r]);
}

/* ================= 兑换码 ================= */
$("#btnRedeem").addEventListener("click", async () => {
  const code = $("#redeemCode").value.trim();
  const msg = $("#redeemMsg");
  if (!code) { msg.textContent = "请输入兑换码"; return; }
  msg.textContent = "验证中…";
  try {
    const fd = new FormData(); fd.append("code", code);
    const r = await fetch("/api/license/redeem", { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) { msg.textContent = data.detail || "激活失败"; return; }
    localStorage.setItem("pindou_code", code);
    msg.textContent = `验证成功! 该码剩余 ${data.remaining} 次, 每次生成自动扣 1 次`;
    setTimeout(() => $("#paywall").classList.add("hidden"), 1500);
  } catch (e) {
    msg.textContent = "网络错误, 请重试";
  }
});
$("#pwClose").addEventListener("click", () => {
  $("#paywall").classList.add("hidden");
  $("#aiPixel").value = "0";   // 回落到免费模式
});
/* 首次尝鲜: 一键领体验码并自动填入 */
$("#btnTrial").addEventListener("click", async () => {
  const msg = $("#trialMsg");
  let cid = localStorage.getItem("pindou_cid");
  if (!cid) {
    cid = crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(36).slice(2);
    localStorage.setItem("pindou_cid", cid);
  }
  msg.textContent = "领取中…";
  try {
    const fd = new FormData(); fd.append("client_id", cid);
    const r = await fetch("/api/license/trial", { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) { msg.textContent = data.detail || "领取失败"; return; }
    $("#redeemCode").value = data.code;
    msg.textContent = "已领到! 点激活即可用";
  } catch (e) {
    msg.textContent = "网络错误, 请重试";
  }
});

/* ================= 结果渲染 ================= */
function renderResult() {
  const s = state.stats;
  $("#statsBar").innerHTML = `
    <span class="chip">${s.size[0]}×${s.size[1]} 豆</span>
    <span class="chip">${s.beads_total.toLocaleString()} 颗</span>
    <span class="chip">${s.colors_used} 色</span>
    <span class="chip gray">${modeName(s.mode)}${s.mode === "limited" ? " " + s.n_colors + " 色" : ""} · ${s.seconds}s</span>
    <span class="chip gray">${algoName(s.algo || "plain")}</span>
    ${s.bg_remove ? `<span class="chip gray">AI 抠图</span>` : ""}
    ${s.merged && s.merged.length ? `<span class="chip gray">合并 ${s.merged.length} 对近似色</span>` : ""}
    <span class="chip gray">${s.metric === "ciede2000" ? "CIEDE2000" : "Lab"} · ${s.series}</span>`;
  renderBeads();
  setLinks();
  renderColorList();
  loadEditPalette().then(() => { renderEditSeriesTabs(); renderEditColorList(); });
  loadIronTree();
  loadSvg("#svgOverview", "pattern_overview.svg");
  loadSvg("#svgPreview", "pattern.svg");
  $("#resultPanel").classList.remove("hidden");   // 先显示再量尺寸 (视口渲染需要真实 wrap 尺寸)
  $("#resultPanel").scrollIntoView({ behavior: "smooth" });
  drawGrid(); drawByColor(); drawEdit();          // 立即画 (后台标签 rAF 冻结也有内容)
  const redraw = () => { drawGrid(); drawByColor(); drawEdit(); };
  requestAnimationFrame(redraw);                  // 布局完成后校正尺寸 (wrap 才有真实高度)
  setTimeout(redraw, 350);                        // 兜底: 后台标签 rAF 冻结时仍会执行
}

function modeName(m) {
  return { plain: "逐点取色", dither: "误差抖动", limited: "限制颜色" }[m] || m;
}

function algoName(a) {
  return { plain: "LANCZOS", mode: "区域主流色", mode4: "4x超采样", edge: "内容自适应" }[a] || a;
}

async function loadSvg(sel, fname) {
  const el = $(sel);
  el.textContent = "";
  const r = await fetch(`/api/file/${state.job}/${fname}`);
  if (!r.ok) { el.innerHTML = `<p class="muted" style="padding:16px">加载失败</p>`; return; }
  el.innerHTML = await r.text();
}

/* ================= 施工图纸 (canvas, 放大始终清晰) ================= */
const gridCanvas = $("#gridCanvas"), gridWrap = $("#gridWrap");

/* 超大图纸视口渲染: 内容超过浏览器 canvas 上限 (8192px 边 / 16M 像素) 时,
   只把可视窗口画到固定大小的 canvas 上, 用 spacer 撑出原生滚动条 */
const MAX_CANVAS_SIDE = 8192, MAX_CANVAS_AREA = 16e6;
let gridSpacer = null;

function drawGrid() {
  if (!state.pattern) return;
  const { grid, legend } = state.pattern;
  const h = grid.length, w = grid[0].length;
  const rgbOf = Object.fromEntries(legend.map(([c, n, p, r, g, b]) => [c, [r, g, b]]));
  const scale = state.gz;                       // 1 格 = 40*scale px
  const cell = 40 * scale;
  const margin = Math.max(28, cell * 0.8);
  const VW = Math.round(w * cell + margin * 2), VH = Math.round(h * cell + margin * 2);
  // 视口模式判定: 整图一块 canvas 会超浏览器上限 → 只画可视区
  const vw = Math.max(200, gridWrap.clientWidth), vh = Math.max(200, gridWrap.clientHeight);
  const vp = VW > MAX_CANVAS_SIDE || VH > MAX_CANVAS_SIDE || VW * VH > MAX_CANVAS_AREA;
  let offX, offY, x0, x1, y0, y1, sx = 0, sy = 0;
  if (vp) {
    if (!gridSpacer) {
      gridSpacer = document.createElement("div");
      gridSpacer.id = "gridSpacer";
      gridWrap.appendChild(gridSpacer);
    }
    gridSpacer.style.width = Math.max(0, VW - vw) + "px";
    gridSpacer.style.height = Math.max(0, VH - vh) + "px";
    gridCanvas.classList.add("vp");
    sx = gridWrap.scrollLeft; sy = gridWrap.scrollTop;   // 尺寸变更后浏览器已钳到合法值
    gridCanvas.width = vw; gridCanvas.height = vh;
    offX = margin - sx; offY = margin - sy;
    x0 = Math.max(0, Math.floor((sx - margin) / cell));
    x1 = Math.min(w, Math.ceil((sx + vw - margin) / cell) + 1);
    y0 = Math.max(0, Math.floor((sy - margin) / cell));
    y1 = Math.min(h, Math.ceil((sy + vh - margin) / cell) + 1);
  } else {
    if (gridSpacer) { gridSpacer.style.width = "0px"; gridSpacer.style.height = "0px"; }
    gridCanvas.classList.remove("vp");
    gridCanvas.width = VW; gridCanvas.height = VH;
    offX = offY = margin;
    x0 = 0; x1 = w; y0 = 0; y1 = h;
  }
  const ctx = gridCanvas.getContext("2d");
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, gridCanvas.width, gridCanvas.height);
  ctx.imageSmoothingEnabled = false;

  // 色块 (只画可视窗口)
  for (let y = y0; y < y1; y++) {
    for (let x = x0; x < x1; x++) {
      const [r, g, b] = rgbOf[grid[y][x]];
      ctx.fillStyle = `rgb(${r},${g},${b})`;
      ctx.fillRect(Math.round(offX + x * cell), Math.round(offY + y * cell),
                   Math.ceil(cell), Math.ceil(cell));
    }
  }
  // 细网格线
  ctx.strokeStyle = "rgba(0,0,0,0.18)";
  ctx.lineWidth = Math.max(0.5, scale * 0.5);
  ctx.beginPath();
  for (let x = x0; x <= x1; x++) {
    ctx.moveTo(offX + x * cell, offY + y0 * cell);
    ctx.lineTo(offX + x * cell, offY + y1 * cell);
  }
  for (let y = y0; y <= y1; y++) {
    ctx.moveTo(offX + x0 * cell, offY + y * cell);
    ctx.lineTo(offX + x1 * cell, offY + y * cell);
  }
  ctx.stroke();

  if ($("#showBoards").checked) {
    // 29×29 板框 (黑) + 5×5 定位线 (红, 标准拼豆板定位)
    ctx.strokeStyle = "#111";
    ctx.lineWidth = Math.max(1.2, scale * 1.6);
    ctx.beginPath();
    for (let x = 0; x <= w; x += 29) {
      ctx.moveTo(offX + x * cell, offY + y0 * cell);
      ctx.lineTo(offX + x * cell, offY + y1 * cell);
    }
    for (let y = 0; y <= h; y += 29) {
      ctx.moveTo(offX + x0 * cell, offY + y * cell);
      ctx.lineTo(offX + x1 * cell, offY + y * cell);
    }
    ctx.stroke();
    ctx.strokeStyle = "#c0392b";
    ctx.lineWidth = Math.max(0.9, scale * 1.1);
    ctx.beginPath();
    for (let x = 5; x < w; x += 5) {
      if (x % 29 === 0) continue;
      ctx.moveTo(offX + x * cell, offY + y0 * cell);
      ctx.lineTo(offX + x * cell, offY + y1 * cell);
    }
    for (let y = 5; y < h; y += 5) {
      if (y % 29 === 0) continue;
      ctx.moveTo(offX + x0 * cell, offY + y * cell);
      ctx.lineTo(offX + x1 * cell, offY + y * cell);
    }
    ctx.stroke();
  }

  // 色号文字 (格子足够大才画; 只画可视窗口)
  if (cell >= 22) {
    const fs = Math.max(9, cell * 0.32);
    ctx.font = `600 ${fs}px Arial`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (let y = y0; y < y1; y++) {
      for (let x = x0; x < x1; x++) {
        const [r, g, b] = rgbOf[grid[y][x]];
        const lum = 0.299 * r + 0.587 * g + 0.114 * b;
        ctx.fillStyle = lum < 140 ? "rgba(255,255,255,0.92)" : "rgba(0,0,0,0.82)";
        ctx.fillText(grid[y][x], offX + (x + 0.5) * cell, offY + (y + 0.5) * cell);
      }
    }
  }
  // 坐标 (每5格)
  if (cell >= 12) {
    const fs = Math.min(13, Math.max(9, cell * 0.3));
    ctx.fillStyle = "#777";
    ctx.font = `${fs}px Arial`;
    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic";
    for (let x = 0; x < w; x += 5)
      ctx.fillText(x + 1, offX + x * cell + 2, offY - 6);
    ctx.textAlign = "right";
    for (let y = 0; y < h; y += 5)
      ctx.fillText(y + 1, offX - 5, offY + y * cell + fs);
  }
  gridCanvas.dataset.margin = margin;
  gridCanvas.dataset.cell = cell;
  gridCanvas.dataset.vp = vp ? "1" : "";
}
let gridDrawRaf = 0;
gridWrap.addEventListener("scroll", () => {
  if (!gridCanvas.classList.contains("vp")) return;
  if (gridDrawRaf) return;
  gridDrawRaf = requestAnimationFrame(() => { gridDrawRaf = 0; drawGrid(); });
});

$("#gzIn").addEventListener("click", () => setZoom(state.gz * 1.3));
$("#gzOut").addEventListener("click", () => setZoom(state.gz / 1.3));
$("#gz100").addEventListener("click", () => setZoom(1));
$("#gzFit").addEventListener("click", () => {
  if (!state.pattern) return;
  const w = state.pattern.grid[0].length;
  setZoom(Math.max(0.02, (gridWrap.clientWidth - 30) / (w * 40)));
});
function setZoom(z) {
  state.gz = Math.min(8, Math.max(0.05, z));   // 视口渲染下低倍率安全, 适应窗口对超大图才真实
  $("#gzVal").textContent = Math.round(state.gz * 100) + "%";
  drawGrid();
}
$("#showBoards").addEventListener("change", drawGrid);

// 悬停坐标提示 (视口模式要把滚动量算回去)
gridCanvas.addEventListener("mousemove", (e) => {
  if (!state.pattern) return;
  const rect = gridCanvas.getBoundingClientRect();
  const margin = +gridCanvas.dataset.margin, cell = +gridCanvas.dataset.cell;
  const sx = gridCanvas.dataset.vp ? gridWrap.scrollLeft : 0;
  const sy = gridCanvas.dataset.vp ? gridWrap.scrollTop : 0;
  const x = Math.floor((e.clientX - rect.left + sx - margin) / cell);
  const y = Math.floor((e.clientY - rect.top + sy - margin) / cell);
  const { grid } = state.pattern;
  if (x >= 0 && y >= 0 && y < grid.length && x < grid[0].length)
    $("#gridHover").textContent = `(${x + 1}, ${y + 1}) ${grid[y][x]}`;
});
gridCanvas.addEventListener("mouseleave", () => $("#gridHover").textContent = "");

/* ================= 按色施工 ================= */
function renderColorList() {
  const el = $("#colorList");
  el.innerHTML = "";
  state.pattern.legend.forEach(([code, n, pct, r, g, b]) => {
    const item = document.createElement("div");
    item.className = "color-item" + (state.colorSel === code ? " active" : "");
    item.dataset.code = code;
    item.innerHTML = `<span class="sw" style="background:rgb(${r},${g},${b})"></span>
      <span class="ci-code">${code}</span>
      <span class="ci-n">${n}</span>
      <span class="ci-check">${state.doneSet.has(code) ? "✓" : ""}</span>`;
    item.addEventListener("click", () => {
      const prev = state.colorSel;
      state.colorSel = state.colorSel === code ? null : code;
      renderColorList();
      drawByColor();
      if (prev === null && state.colorSel) bzFit();   // 首次选色 → 适应窗口
    });
    el.appendChild(item);
  });
  updateByColorTitle();
  updateProgress();
}

function updateByColorTitle() {
  const el = $("#bycolorTitle");
  if (!state.colorSel) { el.textContent = "选择左侧颜色"; return; }
  const entry = state.pattern.legend.find(([c]) => c === state.colorSel);
  const n = entry ? entry[1] : 0;
  const done = state.doneSet.has(state.colorSel);
  el.innerHTML = `施工中: <strong>${state.colorSel}</strong> × ${n} 颗
    <button class="ghost" id="btnDoneColor">${done ? "取消完成" : "标记完成"}</button>`;
  $("#btnDoneColor").addEventListener("click", () => {
    state.doneSet.has(state.colorSel)
      ? state.doneSet.delete(state.colorSel)
      : state.doneSet.add(state.colorSel);
    renderColorList();
    drawByColor();
  });
}

/* ================= 按色施工 (pan/zoom + 淡色底图) ================= */
const bzState = { zoom: 1, px: 0, py: 0 };      // 1=适应窗口
const byColorCanvas = $("#byColorCanvas");

function drawByColor() {
  const canvas = byColorCanvas;
  if (!state.pattern || !state.colorSel) {
    canvas.width = 600; canvas.height = 120;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#fafaf8"; ctx.fillRect(0, 0, 600, 120);
    ctx.fillStyle = "#999"; ctx.font = "15px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("← 从左侧选一个颜色开始施工", 300, 60);
    $("#bzVal").textContent = "适应";
    return;
  }
  const { grid, legend } = state.pattern;
  const h = grid.length, w = grid[0].length;
  const rgbOf = Object.fromEntries(legend.map(([c, n, p, r, g, b]) => [c, [r, g, b]]));

  // 逻辑尺寸: 1 格 40px + 边距; 再乘全局缩放
  const BASE = 40, MARGIN = 60;
  const lw = w * BASE + MARGIN * 2, lh = h * BASE + MARGIN * 2;
  const z = bzState.zoom;
  canvas.width = Math.round(lw * z);
  canvas.height = Math.round(lh * z);
  canvas.style.width = canvas.width + "px";
  canvas.style.height = canvas.height + "px";
  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  const cell = BASE * z, m = MARGIN * z;
  const rgb = rgbOf[state.colorSel];
  const doneOthers = state.hideDone && state.doneSet.size > 0;

  // 第一层: 淡色完整图纸做背景 (知道自己在拼哪一部分)
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const [r, g, b] = rgbOf[grid[y][x]];
      ctx.fillStyle = `rgba(${Math.round(r + (255 - r) * 0.82)},${Math.round(g + (255 - g) * 0.82)},${Math.round(b + (255 - b) * 0.82)},0.9)`;
      ctx.fillRect(Math.round(m + x * cell), Math.round(m + y * cell),
                   Math.ceil(cell), Math.ceil(cell));
    }
  }
  // 第二层: 当前色实色
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (grid[y][x] !== state.colorSel) continue;
      ctx.fillStyle = `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
      ctx.fillRect(Math.round(m + x * cell), Math.round(m + y * cell),
                   Math.ceil(cell), Math.ceil(cell));
    }
  }
  // 第三层: 已完成颜色盖深灰 (hideDone 开启时)
  if (doneOthers) {
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        if (grid[y][x] !== state.colorSel && state.doneSet.has(grid[y][x])) {
          ctx.fillStyle = "rgba(70,70,70,0.55)";
          ctx.fillRect(Math.round(m + x * cell), Math.round(m + y * cell),
                       Math.ceil(cell), Math.ceil(cell));
        }
      }
    }
  }
  // 网格线
  ctx.strokeStyle = "rgba(0,0,0,0.10)";
  ctx.lineWidth = Math.max(0.5, z);
  ctx.beginPath();
  for (let x = 0; x <= w; x++) { ctx.moveTo(m + x * cell, m); ctx.lineTo(m + x * cell, m + h * cell); }
  for (let y = 0; y <= h; y++) { ctx.moveTo(m, m + y * cell); ctx.lineTo(m + w * cell, m + y * cell); }
  ctx.stroke();
  // 5×5 定位线 (红) + 29 板框 (黑)
  ctx.strokeStyle = "#c0392b";
  ctx.lineWidth = Math.max(1, cell * 0.07);
  ctx.beginPath();
  for (let x = 5; x < w; x += 5) { ctx.moveTo(m + x * cell, m); ctx.lineTo(m + x * cell, m + h * cell); }
  for (let y = 5; y < h; y += 5) { ctx.moveTo(m, m + y * cell); ctx.lineTo(m + w * cell, m + y * cell); }
  ctx.stroke();
  ctx.strokeStyle = "#111";
  ctx.lineWidth = Math.max(1.5, cell * 0.09);
  ctx.beginPath();
  for (let x = 0; x <= w; x += 29) { ctx.moveTo(m + x * cell, m); ctx.lineTo(m + x * cell, m + h * cell); }
  for (let y = 0; y <= h; y += 29) { ctx.moveTo(m, m + y * cell); ctx.lineTo(m + w * cell, m + y * cell); }
  ctx.stroke();
  // 坐标
  if (cell >= 14) {
    ctx.fillStyle = "#888";
    ctx.font = `${Math.min(13, cell * 0.35)}px Arial`;
    ctx.textAlign = "left";
    for (let x = 0; x < w; x += 5) ctx.fillText(x + 1, m + x * cell + 2, m - 6);
    ctx.textAlign = "right";
    for (let y = 0; y < h; y += 5) ctx.fillText(y + 1, m - 5, m + y * cell + 12);
  }
  $("#bzVal").textContent = Math.round(z * 100) + "%";
  applyPan();
}

/* pan/zoom: wrap 内绝对定位 + transform */
function applyPan() {
  byColorCanvas.style.transform = `translate(${bzState.px}px, ${bzState.py}px)`;
}
/* 超大图纸: 画布不能超过浏览器上限 → 缩放上限随图案尺寸收缩 */
function bzCapZoom() {
  if (!state.pattern) return 4;
  const w = state.pattern.grid[0].length, h = state.pattern.grid.length;
  const lw = w * 40 + 120, lh = h * 40 + 120;
  return Math.max(0.02, Math.min(4, Math.sqrt(15.5e6 / (lw * lh)), 8192 / Math.max(lw, lh)));
}
function bzFit() {
  const { grid } = state.pattern;
  if (!grid) return;
  const wrap = $("#byColorWrap");
  const w = grid[0].length, h = grid.length;
  const fit = Math.min((wrap.clientWidth - 24) / (w * 40 + 120),
                       (wrap.clientHeight - 24) / (h * 40 + 120));
  const cap = bzCapZoom();
  bzState.zoom = Math.min(cap, Math.max(Math.min(0.1, cap), fit));
  bzState.px = bzState.py = 0;
  drawByColor();
}
function setBz(z) {
  bzState.zoom = Math.min(bzCapZoom(), Math.max(0.1, z));
  drawByColor();
}
$("#bzIn").addEventListener("click", () => setBz(bzState.zoom * 1.25));
$("#bzOut").addEventListener("click", () => setBz(bzState.zoom / 1.25));
$("#bzFit").addEventListener("click", bzFit);
$("#bzReset").addEventListener("click", () => setBz(1));
$("#byColorWrap").addEventListener("wheel", (e) => {
  if (!(e.ctrlKey || e.metaKey)) return;
  e.preventDefault();
  setBz(bzState.zoom * (e.deltaY < 0 ? 1.15 : 0.87));
}, { passive: false });
/* 拖拽移动 */
(() => {
  let drag = null;
  byColorCanvas.addEventListener("pointerdown", (e) => {
    drag = { x: e.clientX, y: e.clientY, px: bzState.px, py: bzState.py };
    byColorCanvas.setPointerCapture(e.pointerId);
    byColorCanvas.style.cursor = "grabbing";
  });
  byColorCanvas.addEventListener("pointermove", (e) => {
    if (!drag) return;
    bzState.px = drag.px + (e.clientX - drag.x);
    bzState.py = drag.py + (e.clientY - drag.y);
    applyPan();
  });
  byColorCanvas.addEventListener("pointerup", () => {
    drag = null;
    byColorCanvas.style.cursor = "grab";
  });
  byColorCanvas.style.cursor = "grab";
})();

$("#hideDone").addEventListener("change", () => { state.hideDone = $("#hideDone").checked; drawByColor(); });
$("#btnResetProgress").addEventListener("click", () => {
  state.doneSet.clear();
  renderColorList(); drawByColor();
});

function updateProgress() {
  const totalColors = state.pattern ? state.pattern.legend.length : 0;
  const done = state.doneSet.size;
  const pct = totalColors ? Math.round(done / totalColors * 100) : 0;
  $("#progressFill").style.width = pct + "%";
  const doneBeads = state.pattern
    ? state.pattern.legend.filter(([c]) => state.doneSet.has(c)).reduce((a, [, n]) => a + n, 0)
    : 0;
  const totalBeads = state.pattern ? state.pattern.beads_total : 0;
  $("#progressText").textContent =
    `${pct}% (${done}/${totalColors} 色 · ${doneBeads.toLocaleString()}/${totalBeads.toLocaleString()} 颗)`;
}

/* ================= 精修 ================= */
/* 全 291 色选色器: 系列(字母) × 色号(数字) 二层分类 */
state.editPalette = null;         // [{code, rgb}] 全 291 色
state.editSeries = "USED";        // USED=图中用色 | A/B/C/...M 系列
state.editQuery = "";

async function loadEditPalette() {
  if (state.editPalette) return;
  const r = await fetch("/api/palette");
  state.editPalette = await r.json();     // [{code, rgb:[r,g,b]}]
}

function editSeriesOf(code) {
  return code.replace(/\d+$/, "") || "?";
}

function renderEditSeriesTabs() {
  const el = $("#editSeriesTabs");
  el.innerHTML = "";
  const usedSeries = new Set(state.pattern.legend.map(([c]) => editSeriesOf(c)));
  const tabs = [["USED", "图中用色"],
                ...[...new Set(state.editPalette.map(p => editSeriesOf(p.code)))]
                    .sort().map(s => [s, s])];
  tabs.forEach(([id, label]) => {
    const b = document.createElement("button");
    b.className = "series-tab" + (state.editSeries === id ? " active" : "");
    b.textContent = label;
    b.addEventListener("click", () => { state.editSeries = id; renderEditSeriesTabs(); renderEditColorList(); });
    el.appendChild(b);
  });
}

function renderEditColorList() {
  const el = $("#editColorList");
  el.innerHTML = "";
  const usedN = Object.fromEntries(state.pattern.legend.map(([c, n]) => [c, n]));
  const q = state.editQuery.trim().toUpperCase();

  let items;
  if (q) {
    // 搜索模式: 全 291 色中匹配
    items = state.editPalette
      .filter(p => p.code.toUpperCase().includes(q))
      .sort((a, b) => a.code.localeCompare(b.code, undefined, {numeric: true}))
      .map(p => ({code: p.code, rgb: p.rgb, n: usedN[p.code] || 0}));
  } else if (state.editSeries === "USED") {
    items = state.pattern.legend.map(([code, n, pct, r, g, b]) =>
      ({code, rgb: [r, g, b], n}));
  } else {
    items = state.editPalette
      .filter(p => editSeriesOf(p.code) === state.editSeries)
      .sort((a, b) => a.code.localeCompare(b.code, undefined, {numeric: true}))
      .map(p => ({code: p.code, rgb: p.rgb, n: usedN[p.code] || 0}));
  }

  // 数字排序: 同系列内按数字升序 (字母序 M1 M10 M11 M2 → M1 M2 M10)
  items.forEach(({code, rgb, n}) => {
    const item = document.createElement("div");
    item.className = "color-item" + (state.editSel === code ? " active" : "");
    item.innerHTML = `<span class="sw" style="background:rgb(${rgb[0]},${rgb[1]},${rgb[2]})"></span>
      <span class="ci-code">${code}</span>${n ? `<span class="ci-n">${n}</span>` : `<span class="ci-n muted">—</span>`}`;
    item.addEventListener("click", () => {
      state.editSel = code;
      $("#editCurCode").textContent = code;
      $("#editCurSw").style.background = `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
      renderEditColorList();
    });
    el.appendChild(item);
  });
}

function setEditBrush(code, rgb) {
  state.editSel = code;
  $("#editCurCode").textContent = code;
  $("#editCurSw").style.background = `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
  renderEditColorList();
}

function drawEdit() {
  const canvas = $("#editCanvas");
  if (!state.pattern) return;
  const grid = state.pattern.grid;
  const h = grid.length, w = grid[0].length;
  const rgbOf = Object.fromEntries(state.pattern.legend.map(([c, n, p, r, g, b]) => [c, [r, g, b]]));
  const LW0 = w * 40 + 52, LH0 = h * 40 + 52;
  const scale = Math.min(1.4, Math.max(0.3, (window.innerWidth * 0.55) / (w * 40)),
                         Math.sqrt(15.5e6 / (LW0 * LH0)), 8192 / Math.max(LW0, LH0));
  const cell = 40 * scale;
  const margin = 26;
  canvas.width = Math.round(w * cell + margin * 2);
  canvas.height = Math.round(h * cell + margin * 2);
  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  const showAll = $("#editShowAll").checked;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const c = grid[y][x];
      if (showAll || c === state.editSel) {
        const [r, g, b] = rgbOf[c];
        ctx.fillStyle = `rgb(${r},${g},${b})`;
      } else ctx.fillStyle = "#f0eee9";
      ctx.fillRect(Math.round(margin + x * cell), Math.round(margin + y * cell),
                   Math.ceil(cell), Math.ceil(cell));
    }
  }
  ctx.strokeStyle = "rgba(0,0,0,0.12)";
  ctx.lineWidth = 0.5;
  ctx.beginPath();
  for (let x = 0; x <= w; x++) { ctx.moveTo(margin + x * cell, margin); ctx.lineTo(margin + x * cell, margin + h * cell); }
  for (let y = 0; y <= h; y++) { ctx.moveTo(margin, margin + y * cell); ctx.lineTo(margin + w * cell, margin + y * cell); }
  ctx.stroke();
  canvas.dataset.margin = margin;
  canvas.dataset.cell = cell;
}
$("#editShowAll").addEventListener("change", drawEdit);

// 点击精修画布 → 换色
$("#editCanvas").addEventListener("click", async (e) => {
  if (!state.pattern || !state.editSel) { showError("先在左侧选画笔颜色"); return; }
  const canvas = e.target;
  const rect = canvas.getBoundingClientRect();
  const margin = +canvas.dataset.margin, cell = +canvas.dataset.cell;
  const x = Math.floor((e.clientX - rect.left - margin) / cell);
  const y = Math.floor((e.clientY - rect.top - margin) / cell);
  const { grid } = state.pattern;
  if (!(x >= 0 && y >= 0 && y < grid.length && x < grid[0].length)) return;
  const old = grid[y][x];
  if (old === state.editSel) return;

  const r = await fetch("/api/edit-bead", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ job: state.job, x, y, code: state.editSel }),
  });
  const data = await r.json();
  if (!r.ok) { showError(data.detail || "修改失败"); return; }
  state.editHistory.push({ x, y, old, nw: data.new });
  state.pattern.grid[y][x] = data.new;
  state.pattern.legend = data.legend;
  state.pattern.colors_used = data.colors_used;
  logEdit(`(${x + 1},${y + 1}) ${old} → ${data.new}`);
  drawEdit();
  renderEditColorList();
  renderBeads();       // 清单同步
  drawByColor();       // 按色施工同步
});

function logEdit(msg) {
  const prev = $("#editLog").innerHTML.split("<br>").slice(0, 3).join("<br>");
  $("#editLog").innerHTML = `最近: ${msg}` + (prev ? `<br>${prev}` : "");
}
$("#btnUndo").addEventListener("click", async () => {
  const last = state.editHistory.pop();
  if (!last) return;
  await fetch("/api/edit-bead", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ job: state.job, x: last.x, y: last.y, code: last.old }),
  });
  state.pattern.grid[last.y][last.x] = last.old;
  await loadPattern();   // 从服务器刷新 legend
  drawEdit(); renderEditColorList(); renderBeads(); drawByColor(); drawGrid();
  logEdit(`撤销 (${last.x + 1},${last.y + 1}) → ${last.old}`);
});
$("#btnResetEdit").addEventListener("click", async () => {
  await loadPattern();
  state.editHistory = [];
  drawEdit(); renderEditColorList(); renderBeads(); drawByColor(); drawGrid();
  logEdit("已还原为自动生成结果");
});

$("#editSearch").addEventListener("input", () => {
  state.editQuery = $("#editSearch").value;
  renderEditColorList();
});

/* ================= 熨烫预览 (三轴分类树) ================= */
state.ironTree = null;
state.ironSelA = "semi";
state.ironSelB = "one";
state.ironSelC = "plain";

async function loadIronTree() {
  if (!state.ironTree) {
    const r = await fetch("/api/iron-methods");
    state.ironTree = await r.json();      // {axisA:[], axisB:[], axisC:[]}
  }
  renderIronAxis("A", state.ironTree.axisA, "ironSelA");
  renderIronAxis("B", state.ironTree.axisB, "ironSelB");
  renderIronAxis("C", state.ironTree.axisC, "ironSelC");
  showIron();
}

function renderIronAxis(axis, opts, selKey) {
  const el = $(`#ironAxis${axis} .iron-opts`);
  el.innerHTML = "";
  opts.forEach(m => {
    const active = state[selKey] === m.id;
    const b = document.createElement("button");
    b.className = "iron-btn" + (active ? " active" : "");
    b.innerHTML = `<strong>${m.name}</strong>` +
      (m.time && m.time !== "-" ? `<span>${m.time} · ${m.iron || ""}</span>` : "");
    b.title = m.desc;
    b.addEventListener("click", () => {
      state[selKey] = m.id;
      if (axis === "A" && m.id === "raw") { state.ironSelC = "plain"; }
      loadIronTree();
    });
    el.appendChild(b);
  });
}

async function showIron() {
  const all = [...state.ironTree.axisA, ...state.ironTree.axisB, ...state.ironTree.axisC];
  const a = all.find(x => x.id === state.ironSelA);
  const c = all.find(x => x.id === state.ironSelC);
  const combo = state.ironSelA === "raw"
    ? `<p class="tip-line">💧 无需加热 — 拼好即可展示或拆掉重拼</p>`
    : `<p class="tip-line">⏱ ${a.time} ｜ 🌡 ${a.iron} ｜ ${state.ironSelB === "two" ? "双面" : "单面"}</p>`;
  $("#ironInfo").innerHTML = `
    <h3>${a.name} · ${state.ironSelB === "two" ? "双面" : "单面"} · ${c.name}</h3>
    <p>${a.desc}</p><p>${c.desc}</p>
    ${combo}
    <p class="muted">${c.tip}</p>
    <p class="muted">${state.ironSelB === "two" ? "双面: 正面完成后冷却翻面, 垫纸再熨; 趁温热重物压平防翘。" : ""}</p>`;
  const r = await fetch(`/api/iron-svg/${state.job}?a=${state.ironSelA}&b=${state.ironSelB}&c=${state.ironSelC}`);
  if (r.ok) $("#ironView").innerHTML = await r.text();
}

/* ================= Tab 切换 ================= */
document.querySelectorAll(".tab").forEach(t => t.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
  document.querySelectorAll(".tabbody").forEach(x => x.classList.add("hidden"));
  t.classList.add("active");
  $(`#tab-${t.dataset.tab}`).classList.remove("hidden");
  if (t.dataset.tab === "grid") drawGrid();
  if (t.dataset.tab === "bycolor") drawByColor();
  if (t.dataset.tab === "edit") drawEdit();
}));

/* ================= 用豆清单 ================= */
function renderBeads() {
  const tb = $("#beadsTable tbody");
  tb.innerHTML = "";
  state.pattern.legend.forEach(([code, n, pct, r, g, b], i) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td class="num">${i + 1}</td>
      <td><span class="sw" style="background:rgb(${r},${g},${b})"></span></td>
      <td><strong>${code}</strong></td>
      <td class="num">${n.toLocaleString()}</td>
      <td class="num">${pct}</td>
      <td class="num muted">${r},${g},${b}</td>`;
    tb.appendChild(tr);
  });
  $("#statsBar").children[2].textContent = `${state.pattern.colors_used} 色`;
}

function setLinks() {
  const base = `/api/file/${state.job}/`;
  $("#dlCsv").href = base + "beads.csv";
  $("#dlGridSvg").href = base + "pattern_grid.svg";
  $("#dlOverviewSvg").href = base + "pattern_overview.svg";
  $("#dlHtml").href = base + "pattern.html";
  $("#dlPng").href = base + "pattern_grid.png";
  $("#dlJson").href = base + "pattern.json";
}

/* ================= 错误提示 ================= */
function showError(msg) {
  const el = $("#error");
  el.textContent = "⚠️ " + msg;
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 5000);
}
function hideError() { $("#error").classList.add("hidden"); }

window.addEventListener("resize", () => {
  if (state.pattern && !$("#tab-grid").classList.contains("hidden")) drawGrid();
  if (state.pattern && !$("#tab-bycolor").classList.contains("hidden") && state.colorSel) bzFit();
});
