#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pindou.py — 任意图 → 拼豆图纸生成器 (MARD 色卡)

用法:
  python3 pindou.py 图片 [-W 80] [--mode plain|dither|limited] [--metric ciede2000|lab]
                      [--series A-HM] [--colors 32] [-o 输出目录]

输出 (默认写入 ./output/<图名>_<宽度>):
  pattern.svg            矢量预览图 (无限放大不糊)
  pattern_overview.svg   总览页: 整图缩略 + 大字图例 (备料对色用)
  pattern_grid.svg       矢量施工图纸: 大格/每格色号/坐标/分板/图例
  pattern_grid.png       带网格线/坐标/色号标注/图例的位图图纸
  pattern.html           A4 可打印图纸 (分页 + 色卡清单)
  beads.csv              用料清单: 色号, RGB, 数量, 占比
  stats.json             本次转换参数与统计
"""
import argparse, csv, json, math, os, re, sys, time
from collections import Counter

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
PALETTE_CSV = os.path.join(HERE, "palettes", "mard.csv")

# ---------------------------------------------------------------- 色卡 ----
def load_palette(series=None):
    """解析 beadcolors v3 mard.csv: code,code,symbol,R,G,B,L*,a*,b*,..."""
    out = []
    with open(PALETTE_CSV, newline="", encoding="utf-8") as f:
        for r in csv.reader(f):
            if len(r) < 6 or not re.match(r"^[A-Z]+[0-9]+$", r[0]):
                continue
            code = r[0]
            if series and code.rstrip("0123456789") not in series:
                continue
            rgb = np.array([int(r[3]), int(r[4]), int(r[5])], dtype=np.float64)
            out.append((code, rgb))
    if not out:
        sys.exit("色卡为空: 检查 --series 参数 (可用: A B C D E F G H M P Q R T Y ZG)")
    return out

def parse_series(s):
    """'ABM' / 'A-HM' / 'A,B,M' -> {'A',...}; None 表示全部"""
    if not s:
        return None
    allowed = set()
    for part in re.split(r"[,，]", s):
        m = re.match(r"^([A-Z]+)-([A-Z]+)$", part)
        if m:
            a, b = m.group(1), m.group(2)
            letters = "ABCDEFGHIJKLMNOPQRSTY ZG".split()
            for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                if a <= ch <= b:
                    allowed.add(ch)
        else:
            allowed.update(re.findall(r"[A-Z]+", part))
    return allowed or None

# ------------------------------------------------------------ 颜色空间 ----
def srgb_to_lab(rgb):
    """rgb float [...,3] 0-255 -> CIE Lab"""
    c = rgb / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    x = lin @ np.array([0.4124564, 0.3575761, 0.1804375]) / 0.95047
    y = lin @ np.array([0.2126729, 0.7151522, 0.0721750]) / 1.00000
    z = lin @ np.array([0.0193339, 0.1191920, 0.9503041]) / 1.08883
    eps, kappa = 216 / 24389, 24389 / 27
    def _f(t):
        return np.where(t > eps, np.cbrt(t), (kappa * t + 16) / 116)
    fx, fy, fz = _f(x), _f(y), _f(z)
    L = 116 * fy - 16
    a = 500 * (fx - fy)
    b = 200 * (fy - fz)
    return np.stack([L, a, b], axis=-1)

def ciede2000(lab1, lab2):
    """向量化 CIEDE2000。lab1/lab2: [...,3]"""
    L1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    L2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]
    C1, C2 = np.hypot(a1, b1), np.hypot(a2, b2)
    Cb = (C1 + C2) / 2
    G = 0.5 * (1 - np.sqrt(Cb ** 7 / (Cb ** 7 + 25.0 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    dLp = L2 - L1
    dCp = C2p - C1p
    prod = C1p * C2p
    dhp = h2p - h1p
    dhp = np.where(dhp > 180, dhp - 360, dhp)
    dhp = np.where(dhp < -180, dhp + 360, dhp)
    dhp = np.where(prod == 0, 0.0, dhp)
    dHp = 2 * np.sqrt(np.maximum(prod, 0)) * np.sin(np.radians(dhp) / 2)
    Lbp = (L1 + L2) / 2
    Cbp = (C1p + C2p) / 2
    hsum = h1p + h2p
    hdiff = np.abs(h1p - h2p)
    hbp = np.where(hdiff <= 180, hsum / 2,
          np.where(hsum < 360, (hsum + 360) / 2, (hsum - 360) / 2))
    hbp = np.where(prod == 0, hsum, hbp)
    T = (1 - 0.17 * np.cos(np.radians(hbp - 30)) + 0.24 * np.cos(np.radians(2 * hbp))
         + 0.32 * np.cos(np.radians(3 * hbp + 6)) - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    Rc = 2 * np.sqrt(Cbp ** 7 / (Cbp ** 7 + 25.0 ** 7))
    Sl = 1 + 0.015 * (Lbp - 50) ** 2 / np.sqrt(20 + (Lbp - 50) ** 2)
    Sc = 1 + 0.045 * Cbp
    Sh = 1 + 0.015 * Cbp * T
    dtheta = 30 * np.exp(-(((hbp - 275) / 25) ** 2))
    Rt = -np.sin(np.radians(2 * dtheta)) * Rc
    return np.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2
                   + Rt * (dCp / Sc) * (dHp / Sh))

# -------------------------------------------------------------- 匹配 ----
def dark_penalty(lab_px, pal_lab, pal_c, W_L=0.7, W_C=0.4):
    """暗部感知保护惩罚矩阵 [n,M] (只惩罚比像素更亮/更艳的候选)。
    CIEDE2000 在极暗区 (L*<40) 会把近黑像素拉到明度/彩度都高得多的暗彩豆
    (如深棕映到亮紫 D10) — 数值最近但视觉色相跳变。惩罚项:
      - relu(ΔL* - tol)^1.5 × W_L, tol 分段 (L*<12→3, 其余→7)
      - relu(ΔC* - 6)^1.5 × W_C
    暗部层次由色卡中更暗的分档 (深棕/深灰/黑) 保留, 不一刀切成纯黑。"""
    Lp = lab_px[:, 0:1]                                 # [n,1]
    Cp = np.hypot(lab_px[:, 1], lab_px[:, 2])[:, None]
    tol = np.where(Lp < 12, 3.0, 7.0)                   # [n,1]
    dark = (Lp < 40).astype(np.float64)                 # [n,1]
    penL = np.maximum(pal_lab[None, :, 0] - Lp - tol, 0) ** 1.5 * W_L   # [n,M]
    penC = np.maximum(pal_c[None, :] - Cp - 6, 0) ** 1.5 * W_C          # [n,M]
    return dark * (penL + penC)                         # [n,M]

def build_matcher(palette, metric, dark_guard=True):
    pal_lab = srgb_to_lab(np.stack([p[1] for p in palette]))
    codes = [p[0] for p in palette]
    pal_c = np.hypot(pal_lab[:, 1], pal_lab[:, 2])      # 候选彩度 C*

    if metric == "lab":
        def match(lab_px):                       # lab_px: [N,3]
            d = np.linalg.norm(lab_px[:, None, :] - pal_lab[None, :, :], axis=2)
            if dark_guard:
                d = d + dark_penalty(lab_px, pal_lab, pal_c)
            return np.argmin(d, axis=1)
    else:
        def match(lab_px):
            best = np.full(len(lab_px), np.inf)
            idx = np.zeros(len(lab_px), dtype=np.int32)
            if dark_guard:
                pen = dark_penalty(lab_px, pal_lab, pal_c)   # [N,M] 预计算一次
            for j in range(len(pal_lab)):        # 逐色广播, N×M 总量不变
                chunk = np.arange(0, len(lab_px), 4096)
                for s in chunk:
                    e = min(s + 4096, len(lab_px))
                    d = ciede2000(lab_px[s:e], pal_lab[j])
                    if dark_guard:
                        d = d + pen[s:e, j]
                    upd = d < best[s:e]
                    best[s:e][upd] = d[upd]
                    idx[s:e][upd] = j
            return idx
    return match, pal_lab, codes

def kmeans_downsample(lab_px, k, iters=12, seed=0):
    """限色模式: 先把像素聚类成 k 个代表色"""
    rng = np.random.default_rng(seed)
    k = min(k, len(lab_px))
    cent = lab_px[rng.choice(len(lab_px), k, replace=False)]
    for _ in range(iters):
        d = np.linalg.norm(lab_px[:, None, :] - cent[None, :, :], axis=2)
        asg = np.argmin(d, axis=1)
        for j in range(k):
            m = lab_px[asg == j]
            if len(m):
                cent[j] = m.mean(axis=0)
    return cent, asg

def mode_downsample(rgb_img, W, H):
    """区域主流色采样: 每个输出格取源区域内出现最多的颜色。
    比平均色更锐利, 不会把细线平均掉, 也天然抑制单像素噪声。"""
    im = np.asarray(rgb_img, dtype=np.uint8)          # [h,w,3]
    sh, sw, _ = im.shape
    xs = (np.arange(W + 1) * sw / W).astype(int)      # 区域边界
    ys = (np.arange(H + 1) * sh / H).astype(int)
    out = np.zeros((H, W, 3), dtype=np.uint8)
    for yy in range(H):
        for xx in range(W):
            block = im[ys[yy]:max(ys[yy + 1], ys[yy] + 1),
                       xs[xx]:max(xs[xx + 1], xs[xx] + 1)].reshape(-1, 3)
            if block.shape[0] > 400:                  # 大块随机采样加速
                sel = np.random.default_rng(xx * 131 + yy).choice(
                    block.shape[0], 400, replace=False)
                block = block[sel]
            key = (block[:, 0].astype(np.int64) << 16) | \
                  (block[:, 1].astype(np.int64) << 8) | block[:, 2]
            uniq, cnts = np.unique(key, return_counts=True)
            out[yy, xx] = block[int(np.argmax(cnts))]
    return out

def despeckle(idx_map, min_run=2):
    """孤立豆清理: 连通域 < min_run 的色块并入周围最多的颜色。
    拼豆实操中孤立单豆在熨烫和搬运时最易脱落。"""
    from collections import deque
    h, w = idx_map.shape
    out = idx_map.copy()
    seen = np.zeros((h, w), dtype=bool)
    for y0 in range(h):
        for x0 in range(w):
            if seen[y0, x0]:
                continue
            c = idx_map[y0, x0]
            q = deque([(y0, x0)])
            comp = []
            seen[y0, x0] = True
            while q:
                y, x = q.popleft()
                comp.append((y, x))
                for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and not seen[ny, nx] \
                            and idx_map[ny, nx] == c:
                        seen[ny, nx] = True
                        q.append((ny, nx))
            if len(comp) < min_run:
                neigh = []
                for y, x in comp:
                    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < h and 0 <= nx < w and idx_map[ny, nx] != c:
                            neigh.append(idx_map[ny, nx])
                if neigh:
                    fill = Counter(neigh).most_common(1)[0][0]
                    for y, x in comp:
                        out[y, x] = fill
    return out

def edge_downsample(rgb_img, W, H):
    """内容自适应加权降采样 (Kopf & Shamir 内容自适应降采样思想的轻量实现):
    梯度大的边缘像素权重 5 倍, 让采样色向内容边界靠拢, 保形状。
    积分图实现, O(1) 每块。"""
    im = np.asarray(rgb_img, dtype=np.float64)        # [h,w,3]
    gray = im @ np.array([0.299, 0.587, 0.114])
    gx = np.abs(np.diff(gray, axis=1, prepend=gray[:, :1]))
    gy = np.abs(np.diff(gray, axis=0, prepend=gray[:1, :]))
    wgt = 1.0 + 4.0 * np.clip((gx + gy) / 96.0, 0, 1)  # 1~5x
    # 积分图: 4 张 (w, w·r, w·g, w·b), 前置 0 行/列
    def integral(a):
        ii = np.zeros((a.shape[0] + 1, a.shape[1] + 1, *a.shape[2:]))
        ii[1:, 1:] = np.cumsum(np.cumsum(a, axis=0), axis=1)
        return ii
    Iw = integral(wgt)
    Ic = integral(im * wgt[:, :, None])
    sh, sw, _ = im.shape
    xs = np.minimum((np.arange(W + 1) * sw / W).astype(int), sw)
    ys = np.minimum((np.arange(H + 1) * sh / H).astype(int), sh)
    out = np.zeros((H, W, 3), dtype=np.uint8)
    for yy in range(H):
        y0, y1 = ys[yy] + 1, min(ys[yy + 1] + 1, sh)
        for xx in range(W):
            x0, x1 = xs[xx] + 1, min(xs[xx + 1] + 1, sw)
            wsum = Iw[y1, x1] - Iw[y0, x1] - Iw[y1, x0] + Iw[y0, x0]
            csum = Ic[y1, x1] - Ic[y0, x1] - Ic[y1, x0] + Ic[y0, x0]
            out[yy, xx] = np.clip(csum / max(wsum, 1e-9), 0, 255).astype(np.uint8)
    return out

def merge_similar_codes(codes, pal_rgb, idx_map, threshold):
    """相似色合并: 把图里 CIEDE2000 距离 < threshold 的颜色对中,
    用量少的并入用量多的, 重新映射整个图案。返回 (new_idx_map, merged_info)。"""
    used = sorted(set(int(j) for j in idx_map.ravel()))
    if len(used) < 2:
        return idx_map, []
    lab = srgb_to_lab(pal_rgb[used])
    remap = {j: j for j in used}
    # 按用量从大到小定锚, 近邻往锚上并
    cnt = Counter(int(j) for j in idx_map.ravel())
    anchors = sorted(used, key=lambda j: -cnt[j])
    merged = []
    for i, a in enumerate(anchors):
        if remap[a] != a:
            continue
        for b in anchors[i + 1:]:
            if remap[b] != b:
                continue
            la, lb = lab[used.index(a)], lab[used.index(b)]
            if ciede2000(np.array([la]), np.array([lb]))[0] < threshold:
                remap[b] = a
                merged.append((codes[b], codes[a]))
    if not merged:
        return idx_map, []
    lut = np.arange(len(codes), dtype=np.int32)
    for b, a in remap.items():
        if b != a:
            lut[b] = a
    return lut[idx_map], merged

# ------------------------------------------------------------ 抖动 ----
def floyd_steinberg(lab_img, pal_lab, dark_guard=True, pal_c=None,
                    chroma_diffusion=0.0):
    """在 Lab 空间做 FS 误差扩散, 蛇形扫描。lab_img: [H,W,3] -> 索引图
    dark_guard: 与 build_matcher 一致的暗部保护 (FS 逐像素匹配也要防暗部跳色)
    chroma_diffusion: 彩度/色相误差扩散比例 (0=只扩散明度误差)。
    拼豆场景色相误差扩散会产生明显色点噪声 (暗部发紫的元凶之一), 默认只扩散明度。"""
    h, w, _ = lab_img.shape
    buf = lab_img.astype(np.float64).copy()
    idx_map = np.zeros((h, w), dtype=np.int32)
    for y in range(h):
        rng = range(w) if y % 2 == 0 else range(w - 1, -1, -1)
        sign = 1 if y % 2 == 0 else -1
        for x in rng:
            px = buf[y, x]
            d = ciede2000(np.tile(px, (len(pal_lab), 1)), pal_lab)
            if dark_guard:
                px_lab = px.reshape(1, 3)
                d = d + dark_penalty(px_lab, pal_lab, pal_c)[0]
            j = int(np.argmin(d))
            idx_map[y, x] = j
            err = px - pal_lab[j]
            if chroma_diffusion <= 0:
                err = np.array([err[0], 0.0, 0.0])
            elif chroma_diffusion < 1:
                err = np.array([err[0], err[1] * chroma_diffusion,
                                err[2] * chroma_diffusion])
            for dx, wt in ((1, 7),):
                xx = x + sign * dx
                if 0 <= xx < w:
                    buf[y, xx] += err * wt / 16
            if y + 1 < h:
                for dx, wt in ((-1, 3), (0, 5), (1, 1)):
                    xx = x + sign * dx
                    if 0 <= xx < w:
                        buf[y + 1, xx] += err * wt / 16
    return idx_map

# ------------------------------------------------------------ 输出 ----
def render_svg(idx_map, codes, pal_rgb, path, counts, src, params, layout="grid"):
    """矢量 SVG。layout:
    preview  → 纯色块预览 (无限放大)
    overview → 总览页: 整图缩小 + 右侧大图例 (备料对色用)
    grid     → 施工图纸: 大格/每格色号/坐标/分板/图例"""
    from xml.sax.saxutils import escape
    h, w = idx_map.shape
    total = int(idx_map.size)
    order = sorted(counts, key=lambda c: -counts[c])
    lookup = {c: i for i, c in enumerate(codes)}
    lum = pal_rgb @ np.array([0.299, 0.587, 0.114])
    flat = idx_map.ravel()

    if layout == "preview":
        cell, fs = 40, 13
        used = sorted(set(int(j) for j in flat))
        defs = []
        for j in used:
            r, g, b = (int(v) for v in pal_rgb[j])
            defs.append(f'<g id="p{j}"><rect x="0" y="0" width="{cell}" height="{cell}" '
                        f'fill="#{r:02x}{g:02x}{b:02x}" stroke="#8a8a8a" stroke-width="0.6"/></g>')
        s = ['<?xml version="1.0" encoding="UTF-8"?>',
             f'<svg xmlns="http://www.w3.org/2000/svg" '
             f'xmlns:xlink="http://www.w3.org/1999/xlink" width="{w*cell}" '
             f'height="{h*cell}" viewBox="0 0 {w*cell} {h*cell}">',
             '<defs>', *defs, '</defs>',
             f'<rect width="{w*cell}" height="{h*cell}" fill="#ffffff"/>',
             '<g shape-rendering="crispEdges">']
        for yy in range(h):
            base = yy * w
            s.append("".join(
                f'<use xlink:href="#p{int(flat[base+xx])}" href="#p{int(flat[base+xx])}" '
                f'x="{xx*cell}" y="{yy*cell}"/>' for xx in range(w)))
        s.append('</g></svg>')
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(s))
        return

    if layout == "overview":
        cell = 12
        pw, ph = w * cell, h * cell
        scale = min(1.0, 1400 / pw, 1000 / ph)      # 整图不超过 ~1400×1000
        pw, ph = int(pw * scale), int(ph * scale)
        lcol_w, row_h, lsw, lh = 210, 34, 24, 18
        lrows_cap = max(6, (ph + 60) // row_h)
        lcols = max(1, math.ceil(len(order) / lrows_cap))
        lw = lcols * lcol_w + 30
        Wt, Ht = 30 + pw + 26 + lw, max(ph, len(order) * row_h if lcols == 1 else 0) + 90
        s = ['<?xml version="1.0" encoding="UTF-8"?>',
             f'<svg xmlns="http://www.w3.org/2000/svg" '
             f'xmlns:xlink="http://www.w3.org/1999/xlink" width="{Wt}" height="{Ht}" '
             f'viewBox="0 0 {Wt} {Ht}" font-family="Arial, \'Hiragino Sans GB\', sans-serif">',
             f'<rect width="{Wt}" height="{Ht}" fill="#ffffff"/>',
             f'<text x="30" y="30" font-size="20" font-weight="bold" fill="#111">'
             f'总览 · {escape(os.path.basename(src))}</text>',
             f'<text x="30" y="52" font-size="13" fill="#666">{w}×{h} 豆 · {total} 颗 · '
             f'{len(counts)} 色 · 缩略仅对色, 施工请用 pattern_grid.svg</text>']
        used = sorted(set(int(j) for j in flat))
        s.append('<defs>')
        for j in used:
            r, g, b = (int(v) for v in pal_rgb[j])
            s.append(f'<g id="o{j}"><rect x="0" y="0" width="{cell}" height="{cell}" '
                     f'fill="#{r:02x}{g:02x}{b:02x}"/></g>')
        s.append('</defs>')
        s.append(f'<g shape-rendering="crispEdges" transform="translate(30,70) scale({scale})">')
        for yy in range(h):
            base = yy * w
            s.append("".join(
                f'<use xlink:href="#o{int(flat[base+xx])}" href="#o{int(flat[base+xx])}" '
                f'x="{xx*cell}" y="{yy*cell}"/>' for xx in range(w)))
        s.append('</g>')
        s.append(f'<rect x="30" y="70" width="{pw}" height="{ph}" fill="none" '
                 f'stroke="#333" stroke-width="2"/>')
        lx = 30 + pw + 26
        s.append(f'<text x="{lx}" y="84" font-size="17" font-weight="bold" fill="#111">'
                 f'图例 — 色号 / 数量 / 占比</text>')
        for i, c in enumerate(order):
            col, row = divmod(i, lrows_cap)
            ex, ey = lx + col * lcol_w, 104 + row * row_h
            j = lookup[c]
            r, g, b = (int(v) for v in pal_rgb[j])
            s.append(f'<rect x="{ex}" y="{ey}" width="{lsw}" height="{lsw}" '
                     f'fill="#{r:02x}{g:02x}{b:02x}" stroke="#888" stroke-width="1"/>')
            s.append(f'<text x="{ex + lsw + 8}" y="{ey + 12}" font-size="15" font-weight="bold" '
                     f'fill="#111">{c}</text>')
            pct = counts[c] / total * 100
            pct_txt = f"{pct:.1f}%" if pct >= 0.05 else "&lt;0.1%"
            s.append(f'<text x="{ex + lsw + 8}" y="{ey + 26}" font-size="13" fill="#555">'
                     f'{counts[c]} · {pct_txt}</text>')
        s.append('</svg>')
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(s))
        return

    # ---- layout == "grid": 施工图纸 ----
    cell, fs = 40, 13
    lum_ = pal_rgb @ np.array([0.299, 0.587, 0.114])
    used = sorted(set(int(j) for j in flat))
    defs = []
    for j in used:
        r, g, b = (int(v) for v in pal_rgb[j])
        fill = f"#{r:02x}{g:02x}{b:02x}"
        fg = "#ffffff" if lum_[j] < 140 else "#111111"
        label = codes[j] if len(codes[j]) <= 3 else codes[j][:3]
        defs.append(f'<g id="p{j}"><rect x="0" y="0" width="{cell}" height="{cell}" '
                    f'fill="{fill}" stroke="#8a8a8a" stroke-width="0.6"/>'
                    f'<text x="{cell/2}" y="{cell/2 + fs*0.35}" text-anchor="middle" '
                    f'font-size="{fs}" fill="{fg}" font-weight="600">{label}</text></g>')
    s = ['<?xml version="1.0" encoding="UTF-8"?>']

    # ---- 施工图纸布局: 标准拼豆板 29×29 分板 + 5×5 定位线 + 图例 ----
    bw, bh = min(w, 29), min(h, 29)
    nv, nh = math.ceil(h / bh), math.ceil(w / bw)
    gap, ml, mt = 34, 46, 46
    gw = nh * (bw * cell + gap) - gap
    gh = nv * (bh * cell + gap) - gap
    order = sorted(counts, key=lambda c: -counts[c])
    row_h, lcol_w, lsw = 40, 200, 30           # 图例行高/列宽/色块边长
    # 宽图 → 图例放下方横排; 窄高图 → 图例放右侧
    if gw >= 2400:
        lcols_fit = max(1, int(gw // lcol_w))
        lrows = math.ceil(len(order) / lcols_fit)
        Wt, Ht = ml + gw + 46, mt + gh + 96 + lrows * row_h
        lx, ly0, rows_cap = ml, mt + gh + 74, lrows
    else:
        rows_cap = max(8, int((gh - 40) / row_h))
        lcols = max(1, math.ceil(len(order) / rows_cap))
        lw = lcols * lcol_w + 10
        Wt, Ht = ml + gw + 42 + lw + 18, mt + gh + 40
        lx, ly0, rows_cap = ml + gw + 42, mt + 32, rows_cap

    s.append(f'<svg xmlns="http://www.w3.org/2000/svg" '
             f'xmlns:xlink="http://www.w3.org/1999/xlink" width="{Wt}" height="{Ht}" '
             f'viewBox="0 0 {Wt} {Ht}" font-family="Arial, \'Hiragino Sans GB\', sans-serif">')
    s.append('<defs>'); s.extend(defs); s.append('</defs>')
    s.append(f'<rect width="{Wt}" height="{Ht}" fill="#ffffff"/>')
    s.append(f'<text x="{ml}" y="30" font-size="20" font-weight="bold" fill="#111">'
             f'拼豆图纸 — {escape(os.path.basename(src))}</text>')
    s.append(f'<text x="{ml}" y="40" font-size="13" fill="#666">{w}×{h} 豆 · 共 {total} 颗 · '
             f'{len(counts)} 色 · 模式 {params["mode"]} · 匹配 {params["metric"]} · '
             f'MARD 色卡 · 每格 1 豆</text>')
    s.append('<g shape-rendering="crispEdges">')
    y0 = mt
    for bv in range(nv):
        x0 = ml
        for bhh in range(nh):
            wl, hl = min(bw, w - bhh * bw), min(bh, h - bv * bh)
            s.append(f'<g transform="translate({x0},{y0})">')
            for yy in range(hl):
                gy = bv * bh + yy
                row = []
                for xx in range(wl):
                    gx = bhh * bw + xx
                    j = int(idx_map[gy, gx])
                    row.append(f'<use xlink:href="#p{j}" href="#p{j}" '
                               f'x="{xx*cell}" y="{yy*cell}"/>')
                s.append("".join(row))
            s.append(f'<rect x="0" y="0" width="{wl*cell}" height="{hl*cell}" '
                     f'fill="none" stroke="#333" stroke-width="2"/>')
            for k in range(5, wl, 5):
                heavy = (k % 29 == 0)
                s.append(f'<line x1="{k*cell}" y1="0" x2="{k*cell}" y2="{hl*cell}" '
                         f'stroke="#333" stroke-width="{1.4 if heavy else 0.7}"/>')
            for k in range(5, hl, 5):
                heavy = (k % 29 == 0)
                s.append(f'<line x1="0" y1="{k*cell}" x2="{wl*cell}" y2="{k*cell}" '
                         f'stroke="#333" stroke-width="{1.4 if heavy else 0.7}"/>')
            s.append('</g>')
            step = 5 if wl > 40 else (10 if wl > 20 else 5)
            for k in range(0, wl, step):
                s.append(f'<text x="{x0 + k*cell + 2}" y="{y0 - 5}" font-size="11" '
                         f'fill="#555">{bhh*bw + k + 1}</text>')
            for k in range(0, hl, step):
                s.append(f'<text x="{x0 - 5}" y="{y0 + k*cell + 12}" font-size="11" '
                         f'fill="#555" text-anchor="end">{bv*bh + k + 1}</text>')
            x0 += bw * cell + gap
        y0 += bh * cell + gap
    s.append('</g>')
    # ---- 图例 ----
    lookup = {c: i for i, c in enumerate(codes)}
    s.append(f'<text x="{lx}" y="{ly0 - 14}" font-size="17" font-weight="bold" fill="#111">'
             f'图例 — 色号 / 数量 / 占比</text>')
    for i, c in enumerate(order):
        col, row = divmod(i, rows_cap)
        ex, ey = lx + col * lcol_w, ly0 + row * row_h
        j = lookup[c]
        r, g, b = (int(v) for v in pal_rgb[j])
        s.append(f'<rect x="{ex}" y="{ey}" width="{lsw}" height="{lsw}" '
                 f'fill="#{r:02x}{g:02x}{b:02x}" stroke="#888" stroke-width="1"/>')
        s.append(f'<text x="{ex + lsw + 8}" y="{ey + 14}" font-size="15" font-weight="bold" '
                 f'fill="#111">{c}</text>')
        s.append(f'<text x="{ex + lsw + 8}" y="{ey + 28}" font-size="13" fill="#555">'
                 f'{counts[c]} · {counts[c]/total*100:.1f}%</text>')
    s.append('</svg>')
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(s))

def render_grid(idx_map, codes, pal_rgb, path):
    """位图施工图纸: 网格/坐标/色号 + 右侧图例面板"""
    h, w = idx_map.shape
    cell = min(max(26, 3000 // max(w, 1)), 60)
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf",
                              max(9, int(cell * 0.30)))
    margin_l, margin_t = int(cell * 1.2), int(cell * 1.2)
    counts = Counter(codes[j] for j in idx_map.ravel())
    order = sorted(counts, key=lambda c: -counts[c])
    lookup = {c: i for i, c in enumerate(codes)}
    # 图例尺寸
    row_h = 24
    rows_cap = max(6, (h * cell) // row_h)
    lcols = max(1, math.ceil(len(order) / rows_cap))
    legend_w = lcols * 210 + 16
    im = Image.new("RGB", (margin_l + w * cell + int(cell * 0.6) + legend_w,
                           margin_t + h * cell + int(cell * 0.6)), "white")
    d = ImageDraw.Draw(im)
    for yy in range(h):
        for xx in range(w):
            j = idx_map[yy, xx]
            x0, y0 = margin_l + xx * cell, margin_t + yy * cell
            d.rectangle([x0, y0, x0 + cell, y0 + cell],
                        fill=tuple(int(v) for v in pal_rgb[j]), outline="#bbbbbb")
            code = codes[j]
            label = code if len(code) <= 3 else code[:3]
            tw = d.textlength(label, font=font)
            d.text((x0 + (cell - tw) / 2, y0 + (cell - font.size) / 2 - 1),
                   label, fill="black", font=font)
    for xx in range(0, w + 1, 10):
        d.line([margin_l + xx * cell, margin_t, margin_l + xx * cell, im.height], fill="#666666")
    for yy in range(0, h + 1, 10):
        d.line([margin_l, margin_t + yy * cell, im.width, margin_t + yy * cell], fill="#666666")
    f10 = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 13)
    for xx in range(0, w, 10):
        d.text((margin_l + xx * cell + 2, 2), str(xx + 1), fill="black", font=f10)
    for yy in range(0, h, 10):
        d.text((2, margin_t + yy * cell + 2), str(yy + 1), fill="black", font=f10)
    # 图例面板
    fb = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 14)
    fc = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 12)
    lx = margin_l + w * cell + int(cell * 0.6) + 14
    d.text((lx, margin_t - 6), "图例 色号/数量/占比", fill="black", font=fb)
    total = int(idx_map.size)
    for i, c in enumerate(order):
        col, row = divmod(i, rows_cap)
        ex, ey = lx + col * 210, margin_t + 20 + row * row_h
        j = lookup[c]
        d.rectangle([ex, ey, ex + 20, ey + 20],
                    fill=tuple(int(v) for v in pal_rgb[j]), outline="#888888")
        d.text((ex + 26, ey + 2), c, fill="black", font=fc)
        d.text((ex + 78, ey + 3), f"{counts[c]} · {counts[c]/total*100:.1f}%",
               fill="#555555", font=fc)
    im.save(path)

def render_html(idx_map, codes, pal_rgb, counts, out, src, params):
    h, w = idx_map.shape
    rows_per_page = 52
    css = ("body{font-family:-apple-system,'Hiragino Sans GB',sans-serif;margin:24px}"
           "table{border-collapse:collapse;table-layout:fixed}"
           "td{width:14px;height:14px;font-size:7px;line-height:14px;text-align:center;"
           "color:#000;border:0.4px solid rgba(0,0,0,.18)}"
           ".rowhd{width:26px;font-size:8px;color:#888;border:none}"
           "h1{font-size:18px}.meta{color:#666;font-size:12px;margin:6px 0 14px}"
           "@media print{.pagebreak{page-break-before:always}}"
           "table.legend td{width:auto;height:auto;font-size:12px;border:1px solid #ccc;padding:2px 8px}"
           ".sw{display:inline-block;width:14px;height:14px;vertical-align:-2px;border:1px solid #999}")
    html = [f"<!doctype html><meta charset='utf-8'><style>{css}</style>",
            f"<h1>拼豆图纸 — {os.path.basename(src)}</h1>"
            f"<div class='meta'>{w}×{h} 豆 · 共 {sum(counts.values())} 颗 · {len(counts)} 色 · "
            f"模式 {params['mode']} · 匹配 {params['metric']} · MARD 色卡</div><div>"]
    for p0 in range(0, h, rows_per_page):
        html.append("<table>")
        for yy in range(p0, min(p0 + rows_per_page, h)):
            row = [f"<td class='rowhd'>{yy+1}</td>"]
            for xx in range(w):
                j = idx_map[yy, xx]
                r, g, b = (int(v) for v in pal_rgb[j])
                label = codes[j] if len(codes[j]) <= 3 else codes[j][:3]
                row.append(f"<td style='background:rgb({r},{g},{b})'>{label}</td>")
            html.append("<tr>" + "".join(row) + "</tr>")
        html.append("</table>")
        if p0 + rows_per_page < h:
            html.append("<div class='pagebreak'></div>")
    html.append("<div class='pagebreak'></div><h1>色卡清单</h1><table class='legend'>"
                "<tr><td>色号</td><td>色块</td><td>数量</td><td>占比</td></tr>")
    for code, n in counts.most_common():
        j = codes.index(code)
        r, g, b = (int(v) for v in pal_rgb[j])
        html.append(f"<tr><td>{code}</td><td><span class='sw' style='background:rgb({r},{g},{b})'></span></td>"
                    f"<td>{n}</td><td>{n/sum(counts.values())*100:.1f}%</td></tr>")
    html.append("</table>")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(html))

# -------------------------------------------------------------- 引擎 ----
def prepare_image(img, W):
    """PIL Image → (RGB small, W, H)"""
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img).convert("RGB")
    else:
        img = img.convert("RGB")
    W = max(1, W)
    H = max(1, round(img.height / img.width * W))
    return img.resize((W, H), Image.LANCZOS), W, H

def write_outputs(idx_map, codes, pal_rgb, counts, src, params, outdir):
    """生成全部产物 (SVG×3, PNG, HTML, CSV, JSON)。精修后也调这里重建。"""
    h, w = idx_map.shape
    total = int(idx_map.size)
    lookup = {c: i for i, c in enumerate(codes)}
    order = sorted(counts, key=lambda c: -counts[c])
    os.makedirs(outdir, exist_ok=True)

    pal_idx_lookup = lookup
    with open(os.path.join(outdir, "beads.csv"), "w", newline="", encoding="utf-8") as f:
        wcsv = csv.writer(f)
        wcsv.writerow(["色号", "R", "G", "B", "数量", "占比%"])
        for c in order:
            j = lookup[c]
            wcsv.writerow([c, *[int(v) for v in pal_rgb[j]], counts[c],
                           f"{counts[c]/total*100:.2f}"])

    render_svg(idx_map, codes, pal_rgb, os.path.join(outdir, "pattern.svg"),
               counts, src, params, layout="preview")
    render_svg(idx_map, codes, pal_rgb, os.path.join(outdir, "pattern_overview.svg"),
               counts, src, params, layout="overview")
    render_svg(idx_map, codes, pal_rgb, os.path.join(outdir, "pattern_grid.svg"),
               counts, src, params, layout="grid")
    render_grid(idx_map, codes, pal_rgb, os.path.join(outdir, "pattern_grid.png"))
    render_html(idx_map, codes, pal_rgb, counts, os.path.join(outdir, "pattern.html"),
                src, params)

    legend = [[c, counts[c], f"{counts[c]/total*100:.1f}%",
               *[int(v) for v in pal_rgb[lookup[c]]]] for c in order]
    grid_json = [[codes[j] for j in row] for row in idx_map]
    data = {"image": src, "size": [w, h], "mode": params.get("mode", "plain"),
            "metric": params.get("metric", "ciede2000"),
            "series": params.get("series") or "ALL(291)",
            "algo": params.get("algo", "plain"),
            "n_colors": params.get("colors", 0),
            "despeckle_n": params.get("despeckle_n", 0),
            "merge_th": params.get("merge_th", 0),
            "colors_used": len(counts), "beads_total": total,
            "palette_size": len(codes), "legend": legend, "grid": grid_json}
    with open(os.path.join(outdir, "pattern.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    stats = {k: v for k, v in data.items() if k != "grid"}
    return stats

def generate(img, width=80, mode="plain", metric="ciede2000", series=None,
             n_colors=32, src_name="upload", algo="plain",
             despeckle_n=0, merge_th=0):
    """核心引擎: PIL Image → 图纸文件集。返回 (outdir, stats_dict)。
    CLI 与 Web 共用; img 为 PIL.Image 对象。
    algo: plain=LANCZOS逐点 mode=区域主流色 edge=内容自适应加权
    despeckle_n: 孤立豆清理 (0=关, ≥2=小于该连通域的色块并入周围)
    merge_th: 相似色合并阈值 CIEDE2000 (0=关, 建议 3~8)"""
    t0 = time.time()
    palette = load_palette(parse_series(series))
    codes = [p[0] for p in palette]
    pal_rgb = np.stack([p[1] for p in palette])
    match, pal_lab, _ = build_matcher(palette, metric)

    # --- 降采样 ---
    if algo == "mode":
        small_rgb = mode_downsample(img.convert("RGB"), width,
                                    max(1, round(img.height / img.width * width)))
        W, H = width, max(1, round(img.height / img.width * width))
        small = Image.fromarray(small_rgb)
    elif algo == "edge":
        small_rgb = edge_downsample(img.convert("RGB"), width,
                                    max(1, round(img.height / img.width * width)))
        W, H = width, max(1, round(img.height / img.width * width))
        small = Image.fromarray(small_rgb)
    else:
        small, W, H = prepare_image(img, width)
    lab = srgb_to_lab(np.asarray(small, dtype=np.float64).reshape(-1, 3))

    # --- 取色/抖动/限色 ---
    if mode == "dither":
        pal_c = np.hypot(pal_lab[:, 1], pal_lab[:, 2])
        idx = floyd_steinberg(lab.reshape(H, W, 3), pal_lab, dark_guard=True,
                              pal_c=pal_c).ravel()
    elif mode == "limited":
        cent, asg = kmeans_downsample(lab, n_colors)
        idx = match(cent)[asg]
    else:
        idx = match(lab)

    idx_map = idx.reshape(H, W)
    merged_info = []
    if merge_th and merge_th > 0:
        idx_map, merged_info = merge_similar_codes(codes, pal_rgb, idx_map, merge_th)
    if despeckle_n and despeckle_n >= 2:
        idx_map = despeckle(idx_map, min_run=despeckle_n)
    counts = Counter(codes[j] for j in idx_map.ravel())
    stem = os.path.splitext(os.path.basename(src_name))[0]
    suffix = algo if algo != "plain" else ""
    outdir = os.path.join(HERE, "output", f"{stem}_{W}_{mode}{suffix}")
    params = {"image": src_name, "width": width, "mode": mode, "metric": metric,
              "series": series, "colors": n_colors, "algo": algo,
              "despeckle_n": despeckle_n, "merge_th": merge_th}
    stats = write_outputs(idx_map, codes, pal_rgb, counts, src_name, params, outdir)
    stats["merged"] = merged_info
    stats["seconds"] = round(time.time() - t0, 2)
    with open(os.path.join(outdir, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    return outdir, stats

# -------------------------------------------------------------- 主流程 ----
def main():
    ap = argparse.ArgumentParser(description="任意图 → MARD 拼豆图纸")
    ap.add_argument("image")
    ap.add_argument("-W", "--width", type=int, default=80, help="横向豆数 (默认 80)")
    ap.add_argument("--mode", choices=["plain", "dither", "limited"], default="plain",
                    help="plain=逐点取色 dither=误差扩散 limited=先聚类限色")
    ap.add_argument("--metric", choices=["ciede2000", "lab"], default="ciede2000")
    ap.add_argument("--series", help="限定色卡系列, 如 'A-HM' 或 'ABCM'; 默认全部 291 色")
    ap.add_argument("--colors", type=int, default=32, help="limited 模式聚类色数 (默认 32)")
    ap.add_argument("--algo", choices=["plain", "mode", "edge"], default="plain",
                    help="降采样: plain=LANCZOS mode=区域主流色 edge=内容自适应加权")
    ap.add_argument("--despeckle", type=int, default=0,
                    help="孤立豆清理: 连通域小于 N 的色块并入周围 (0=关)")
    ap.add_argument("--merge", type=float, default=0,
                    help="相似色合并阈值 CIEDE2000 (0=关, 建议 3~8)")
    ap.add_argument("-o", "--outdir", default=None)
    args = ap.parse_args()

    img = Image.open(args.image)
    outdir, stats = generate(img, width=args.width, mode=args.mode, metric=args.metric,
                             series=args.series, n_colors=args.colors,
                             src_name=os.path.basename(args.image),
                             algo=args.algo, despeckle_n=args.despeckle,
                             merge_th=args.merge)
    if args.outdir:   # 兼容旧参数: 把输出目录整体搬过去
        import shutil
        if os.path.abspath(args.outdir) != os.path.abspath(outdir):
            shutil.rmtree(args.outdir, ignore_errors=True)
            shutil.move(outdir, args.outdir)
            outdir = args.outdir

    order = [c for c, *_ in stats["legend"]]
    print(f"✔ {stats['image']} | {stats['colors_used']} 色 | "
          f"{stats['beads_total']} 颗 | {stats['seconds']}s")
    print("  Top 色:", ", ".join(f"{c}×{n}" for c, n, *_ in stats["legend"][:8]))
    print("  输出目录:", outdir)

if __name__ == "__main__":
    main()
