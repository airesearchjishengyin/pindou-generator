#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拼豆图纸生成器 — Web 服务
启动: python3 server.py   →  http://localhost:8600
"""
import io, os, sys, uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pindou import generate, load_palette, write_outputs  # noqa: E402

import numpy as np                                        # noqa: E402
from collections import Counter                           # noqa: E402
from fastapi import FastAPI, UploadFile, File, Form, HTTPException  # noqa: E402
from fastapi.responses import FileResponse, Response      # noqa: E402
from fastapi.staticfiles import StaticFiles               # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
os.makedirs(OUT, exist_ok=True)
os.makedirs(os.path.join(HERE, "static"), exist_ok=True)

app = FastAPI(title="图豆 · 拼豆图纸生成器")

_palette = load_palette(None)
PALETTE = [{"code": c, "rgb": [int(v) for v in rgb]} for c, rgb in _palette]
PAL_LOOKUP = {p["code"]: p["rgb"] for p in PALETTE}

# ==================================================================
# 熨烫分类学 (基于社区调研: Bitbead 三轴模型 + PixelBeads 6 法 + 22 finish)
# 三轴: A 熔合程度 (孔的保留) × B 熨烫面 (单/双面) × C 表面纹理 (介质压纹)
# 前端按树选择 → 组合成 method key → /api/iron-svg 渲染对应质感
# ==================================================================
IRON_TREE = {
    "axisA": [
        {"id": "raw", "name": "不熨 (原拼装)", "desc": "豆孔完整清晰, 可拆重拼, 像素感最强",
         "tip": "不需要熨斗, 先用板子展示再决定。", "time": "-", "iron": "-"},
        {"id": "semi", "name": "半熔 (孔保留)", "desc": "豆间粘连但豆孔仍在, 立体像素感, 最流行",
         "tip": "中温 ~140-150°C 轻压 10-15s, 缓慢移动, 垫助烫纸。", "time": "10-15s", "iron": "~140-150°C"},
        {"id": "full", "name": "全熔 (孔闭合)", "desc": "熔成平整一片, 最牢固, 适合钥匙扣/杯垫",
         "tip": "中高温 ~155-170°C 持续 20-40s 均匀施压。", "time": "20-40s", "iron": "~155-170°C"},
    ],
    "axisB": [
        {"id": "one", "name": "单面熨", "desc": "只熨正面, 背面保留原豆貌; 正面决定观感", "tip": "正面熨好后从板上取下即完成。"},
        {"id": "two", "name": "双面熨", "desc": "翻面再熨, 两面平整, 强度最高, 大件推荐",
         "tip": "第一面完成后冷却, 翻面垫纸再熨 10-20s; 趁温热重物压平防翘曲。"},
    ],
    "axisC": [
        {"id": "plain", "name": "助烫纸 (光面)", "desc": "标准光面效果, 略带光泽, 最通用",
         "tip": "烘焙纸/助烫纸, 压力均匀。"},
        {"id": "towel", "name": "澡巾纹 (毛巾/澡巾)", "desc": "深绒毛质感, 软萌治愈, 深色图案效果最好",
         "tip": "棉澡巾垫底, 压熨不滑熨; 趁余温撕离, 太凉会粘死。难度★★。"},
        {"id": "washcloth", "name": "方巾纹 (浅绒)", "desc": "比澡巾更细腻的短绒毛, 浅色/萌系动物友好",
         "tip": "浅色豆+方巾; 难度★☆, 比澡巾容错高。"},
        {"id": "waffle", "name": "华夫格纹 (网格压纹)", "desc": "规则格状压纹, 食物类作品超有食欲",
         "tip": "华夫格布垫底; 布料易撕坏, 起离要轻。难度★。"},
        {"id": "diamond", "name": "菱格纹 (斜纹压纹)", "desc": "斜向菱形网格, 像菱格羽绒服面",
         "tip": "菱格纹布/购物袋织带垫底。"},
        {"id": "lace", "name": "蕾丝纹 (镂空花)", "desc": "蕾丝编织镂空花纹压到豆面, 精致复古",
         "tip": "棉蕾丝垫布; 纹理细处压力要够。难度★★。"},
        {"id": "bubble", "name": "气泡膜纹", "desc": "规则圆凸点阵, 像露珠/泡泡, 趣味强",
         "tip": "气泡膜 (小气泡) 垫底轻压。"},
        {"id": "linen", "name": "棉麻布纹", "desc": "细织布纹, 哑光降反光, 接近织物观感",
         "tip": "纯棉平纹布; 代替亮面助烫纸的哑光方案。"},
        {"id": "glitter", "name": "闪粉/亮片膜", "desc": "闪粉转印到豆面, 舞台/节日感",
         "tip": "闪粉熨烫布; 温度窗口窄: 不够热不转印, 过热撕坏布。难度★★★。"},
        {"id": "shimmer", "name": "蓝闪/灰姑娘膜", "desc": "社区俗称'灰姑娘烫', 蓝调珠光, 海洋/星空绝配",
         "tip": "专用灰姑娘膜 (蓝闪膜), 温度窗口最窄, 大件先打样。难度★★★。"},
        {"id": "wrinkle", "name": "褶皱纹", "desc": "揉皱的助烫纸随机褶皱印, 大理石/岩石质感",
         "tip": "烘焙纸揉皱再展开垫底; 每次效果独一无二。"},
        {"id": "clear", "name": "透明感 (透明豆优化)", "desc": "保透明豆的通透感, 少压轻熨",
         "tip": "短时间低温, 避免孔全闭合失去透光。"},
    ],
}

# 组合渲染标识: A_raw 只有一种; 其余 A×B×C 有限组合渲染质感
def _iron_look(axis_a, axis_c):
    """返回渲染风格 key + 纹理参数"""
    if axis_a == "raw":
        return "raw"
    base = "semi" if axis_a == "semi" else "full"
    return base, axis_c

FILE_SET = {"pattern.svg", "pattern_overview.svg", "pattern_grid.svg",
            "pattern_grid.png", "pattern.html", "beads.csv", "stats.json",
            "pattern.json"}


def _job_dir(job: str) -> str:
    if not job or "/" in job or ".." in job or "\\" in job:
        raise HTTPException(404, "任务不存在")
    d = os.path.join(OUT, job)
    if not os.path.isdir(d):
        raise HTTPException(404, "任务不存在")
    return d


def _load_json(job: str) -> dict:
    path = os.path.join(_job_dir(job), "pattern.json")
    if not os.path.isfile(path):
        raise HTTPException(404, "该图纸没有 pattern.json, 请重新生成")
    import json
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_json(job: str, data: dict):
    import json
    path = os.path.join(_job_dir(job), "pattern.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


@app.get("/api/health")
def health():
    return {"ok": True, "palette_size": len(PALETTE)}


@app.get("/api/palette")
def palette():
    return PALETTE


@app.get("/api/iron-methods")
def iron_methods():
    """熨烫分类树: 熔合程度 × 熨烫面 × 表面纹理"""
    return IRON_TREE


@app.post("/api/generate")
async def api_generate(
    image: UploadFile = File(...),
    width: int = Form(80),
    mode: str = Form("plain"),
    metric: str = Form("ciede2000"),
    series: str = Form(""),
    n_colors: int = Form(32),
    algo: str = Form("plain"),
    despeckle_n: int = Form(0),
    merge_th: float = Form(0),
):
    if width < 8 or width > 220:
        raise HTTPException(400, "宽度需在 8–220 之间")
    if mode not in ("plain", "dither", "limited"):
        raise HTTPException(400, f"未知模式: {mode}")
    if metric not in ("ciede2000", "lab"):
        raise HTTPException(400, f"未知色差算法: {metric}")
    if not (2 <= n_colors <= 64):
        raise HTTPException(400, "限色数需在 2–64 之间")
    if algo not in ("plain", "mode", "edge", "mode4"):
        raise HTTPException(400, f"未知降采样算法: {algo}")
    if not (0 <= despeckle_n <= 8):
        raise HTTPException(400, "孤立豆清理需在 0–8 之间")
    if not (0 <= merge_th <= 20):
        raise HTTPException(400, "相似色合并阈值需在 0–20 之间")

    raw = await image.read()
    if len(raw) > 30 * 1024 * 1024:
        raise HTTPException(400, "图片超过 30MB")
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception:
        raise HTTPException(400, "无法解析图片, 请上传 PNG/JPG/WebP 等常见格式")

    safe_stem = "".join(ch for ch in os.path.splitext(image.filename or "upload")[0]
                        if ch.isalnum() or ch in "-_")[:40] or "upload"
    src_name = f"{safe_stem}_{uuid.uuid4().hex[:6]}{os.path.splitext(image.filename or '')[1]}"
    try:
        outdir, stats = generate(img, width=width, mode=mode, metric=metric,
                                 series=series or None, n_colors=n_colors,
                                 src_name=src_name, algo=algo,
                                 despeckle_n=despeckle_n, merge_th=merge_th)
    except Exception as e:
        raise HTTPException(500, f"生成失败: {e}")

    job = os.path.basename(outdir)
    return {"job": job, **{k: v for k, v in stats.items() if k != "legend"},
            "legend": stats["legend"]}


@app.get("/api/pattern/{job}")
def api_pattern(job: str):
    """完整图案数据: legend + grid (色号矩阵), 供按色施工/精修/熨烫预览"""
    return _load_json(job)


@app.get("/api/color-svg/{job}/{code}")
def api_color_svg(job: str, code: str, done: str = ""):
    """按色施工图: 只高亮 code 色; done='1' 时灰色显示已完成色"""
    data = _load_json(job)
    grid = data["grid"]
    h, w = len(grid), len(grid[0])
    if code not in PAL_LOOKUP:
        raise HTTPException(404, f"色号 {code} 不在 MARD 色卡中")
    rgb = PAL_LOOKUP[code]
    cell, pad = 40, 26
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w*cell+2*pad}" '
         f'height="{h*cell+2*pad}" viewBox="0 0 {w*cell+2*pad} {h*cell+2*pad}" '
         f'font-family="Arial, sans-serif">',
         f'<rect width="{w*cell+2*pad}" height="{h*cell+2*pad}" fill="#fff"/>',
         '<g shape-rendering="crispEdges">']
    # 背景: 该色的位置高亮, 其他位置浅灰底
    for yy in range(h):
        row = grid[yy]
        parts = []
        for xx in range(w):
            x, y = pad + xx * cell, pad + yy * cell
            if row[xx] == code:
                parts.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" '
                             f'fill="#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}" '
                             f'stroke="#666" stroke-width="0.6"/>')
            else:
                parts.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" '
                             f'fill="#f2f0ec" stroke="#ddd" stroke-width="0.5"/>')
        s.append("".join(parts))
    # 5×5 定位线 (标准拼豆板定位)
    for k in range(0, w + 1, 5):
        s.append(f'<line x1="{pad+k*cell}" y1="{pad}" x2="{pad+k*cell}" '
                 f'y2="{pad+h*cell}" stroke="#b41e1e" stroke-width="1" opacity="0.75"/>')
    for k in range(0, h + 1, 5):
        s.append(f'<line x1="{pad}" y1="{pad+k*cell}" x2="{pad+w*cell}" '
                 f'y2="{pad+k*cell}" stroke="#b41e1e" stroke-width="1" opacity="0.75"/>')
    s.append('</g>')
    # 坐标
    for k in range(0, w, 5):
        s.append(f'<text x="{pad+k*cell+2}" y="{pad-6}" font-size="11" fill="#888">{k+1}</text>')
    for k in range(0, h, 5):
        s.append(f'<text x="{pad-6}" y="{pad+k*cell+12}" font-size="11" fill="#888" '
                 f'text-anchor="end">{k+1}</text>')
    s.append('</svg>')
    return Response("".join(s), media_type="image/svg+xml")


@app.post("/api/edit-bead")
async def api_edit_bead(job: str = Form(...), x: int = Form(...), y: int = Form(...),
                        code: str = Form(...)):
    """精修: 把 (x,y) 格改成 code 色, 重建全部产物"""
    if code not in PAL_LOOKUP:
        raise HTTPException(400, f"色号 {code} 不在 MARD 色卡中")
    data = _load_json(job)
    grid = data["grid"]
    gh, gw = len(grid), len(grid[0])
    if not (0 <= x < gw and 0 <= y < gh):
        raise HTTPException(400, f"坐标越界: 图纸是 {gw}×{gh}")
    old = data["grid"][y][x]
    data["grid"][y][x] = code
    # 重算 legend
    cnt = Counter(c for row in data["grid"] for c in row)
    total = sum(cnt.values())
    data["colors_used"] = len(cnt)
    data["beads_total"] = total
    data["legend"] = [[c, cnt[c], (f"{cnt[c]/total*100:.1f}%" if cnt[c]/total*100 >= 0.05
                                   else "<0.1%"), *PAL_LOOKUP[c]]
                      for c in sorted(cnt, key=lambda c: -cnt[c])]
    _save_json(job, data)

    # 重建全部产物
    codes_all = [p["code"] for p in PALETTE]
    pal_rgb = np.array([p["rgb"] for p in PALETTE], dtype=np.float64)
    code_to_j = {c: i for i, c in enumerate(codes_all)}
    idx_map = np.array([[code_to_j[c] for c in row] for row in data["grid"]],
                       dtype=np.int32)
    counts = Counter(codes_all[j] for j in idx_map.ravel())
    params = {"image": data["image"], "mode": data.get("mode", "plain"),
              "metric": data.get("metric", "ciede2000"), "series": None, "colors": 0}
    write_outputs(idx_map, codes_all, pal_rgb, counts, data["image"], params,
                  _job_dir(job))
    return {"ok": True, "x": x, "y": y, "old": old, "new": code,
            "colors_used": len(cnt), "legend": data["legend"]}


@app.get("/api/iron-svg/{job}")
def api_iron_svg(job: str, a: str = "semi", b: str = "one", c: str = "plain"):
    """熨烫效果预览 SVG。a=熔合程度(raw/semi/full) b=面(one/two) c=表面纹理(12种)
    纹理介质在豆面上压出对应纹样; b=two 额外整体平整感"""
    if a not in ("raw", "semi", "full"):
        raise HTTPException(400, "a 须为 raw/semi/full")
    if b not in ("one", "two"):
        raise HTTPException(400, "b 须为 one/two")
    if c not in {x["id"] for x in IRON_TREE["axisC"]}:
        raise HTTPException(400, "未知表面纹理 c")
    if a == "raw":
        c = "plain"
    data = _load_json(job)
    grid = data["grid"]
    h, w = len(grid), len(grid[0])
    import random
    rng = random.Random(42)          # 固定种子: 同参数同预览
    cs, pad = 16, 20
    Wt, Ht = w * cs + 2 * pad, h * cs + 2 * pad
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{Wt}" height="{Ht}" '
         f'viewBox="0 0 {Wt} {Ht}">',
         f'<rect width="{Wt}" height="{Ht}" fill="#f8f6f2"/>',
         '<g shape-rendering="crispEdges">']
    for yy in range(h):
        row = grid[yy]
        parts = []
        for xx in range(w):
            r, g, b_ = PAL_LOOKUP[row[xx]]
            x, y = pad + xx * cs, pad + yy * cs
            hexc = f"#{r:02x}{g:02x}{b_:02x}"
            p = [f'<rect x="{x}" y="{y}" width="{cs}" height="{cs}" fill="{hexc}"/>']
            if a == "raw":       # 原始豆: 清晰豆孔
                p.append(f'<circle cx="{x+cs/2}" cy="{y+cs/2}" r="{cs*0.22}" fill="rgba(0,0,0,0.38)"/>'
                         f'<rect x="{x+0.5}" y="{y+0.5}" width="{cs-1}" height="{cs-1}" '
                         f'fill="none" stroke="rgba(0,0,0,0.25)" stroke-width="0.6"/>')
            elif a == "semi":    # 半熔: 浅孔影
                p.append(f'<circle cx="{x+cs/2}" cy="{y+cs/2}" r="{cs*0.18}" fill="rgba(0,0,0,0.16)"/>')
            # ---- 表面纹理 C (全熔/半熔 + 介质) ----
            if a != "raw" and c != "plain":
                if c == "towel":      # 澡巾: 深色短绒点
                    for _ in range(3):
                        dx, dy = rng.uniform(1, cs-3), rng.uniform(1, cs-3)
                        p.append(f'<circle cx="{x+dx:.1f}" cy="{y+dy:.1f}" r="0.9" '
                                 f'fill="rgba(0,0,0,0.20)"/>')
                elif c == "washcloth":  # 方巾: 细绒点 (浅)
                    for _ in range(2):
                        dx, dy = rng.uniform(1, cs-3), rng.uniform(1, cs-3)
                        p.append(f'<circle cx="{x+dx:.1f}" cy="{y+dy:.1f}" r="0.7" '
                                 f'fill="rgba(0,0,0,0.12)"/>')
                elif c == "waffle":   # 华夫格: 方格凹槽
                    p.append(f'<path d="M{x} {y+cs*0.5} H{x+cs} M{x+cs*0.5} {y} V{y+cs}" '
                             f'stroke="rgba(0,0,0,0.18)" stroke-width="1.1"/>')
                elif c == "diamond":  # 菱格: 斜线交叉
                    p.append(f'<path d="M{x} {y} L{x+cs} {y+cs} M{x+cs} {y} L{x} {y+cs}" '
                             f'stroke="rgba(0,0,0,0.15)" stroke-width="0.9"/>')
                elif c == "lace":     # 蕾丝: 花形镂空影
                    p.append(f'<circle cx="{x+cs/2}" cy="{y+cs/2}" r="{cs*0.30}" fill="none" '
                             f'stroke="rgba(0,0,0,0.16)" stroke-width="0.9"/>'
                             f'<circle cx="{x+cs/2}" cy="{y+cs/2}" r="{cs*0.12}" fill="rgba(0,0,0,0.12)"/>')
                elif c == "bubble":   # 气泡膜: 圆凸点
                    p.append(f'<circle cx="{x+cs*0.4}" cy="{y+cs*0.4}" r="{cs*0.24}" '
                             f'fill="rgba(255,255,255,0.16)" stroke="rgba(0,0,0,0.10)" stroke-width="0.6"/>')
                elif c == "linen":    # 棉麻: 细横织纹
                    p.append(f'<path d="M{x} {y+4} H{x+cs} M{x} {y+9} H{x+cs} M{x} {y+14} H{x+cs}" '
                             f'stroke="rgba(0,0,0,0.09)" stroke-width="0.7"/>')
                elif c == "glitter":  # 闪粉: 高光碎点
                    for _ in range(3):
                        dx, dy = rng.uniform(2, cs-2), rng.uniform(2, cs-2)
                        p.append(f'<circle cx="{x+dx:.1f}" cy="{y+dy:.1f}" r="0.8" '
                                 f'fill="rgba(255,255,255,0.85)"/>')
                elif c == "shimmer":  # 灰姑娘: 蓝调珠光
                    p.append(f'<circle cx="{x+cs*0.35}" cy="{y+cs*0.35}" r="{cs*0.26}" '
                             f'fill="rgba(120,180,255,0.28)"/>'
                             f'<circle cx="{x+cs*0.65}" cy="{y+cs*0.65}" r="{cs*0.14}" '
                             f'fill="rgba(255,255,255,0.30)"/>')
                elif c == "wrinkle":  # 褶皱: 随机折痕
                    x1, y1 = rng.uniform(0, cs*0.4), rng.uniform(0, cs*0.4)
                    x2, y2 = rng.uniform(cs*0.6, cs), rng.uniform(cs*0.6, cs)
                    p.append(f'<path d="M{x+x1:.1f} {y+y1:.1f} L{x+x2:.1f} {y+y2:.1f}" '
                             f'stroke="rgba(0,0,0,0.14)" stroke-width="1.2"/>')
                elif c == "clear":    # 透明感: 高透过高光
                    p.append(f'<circle cx="{x+cs*0.4}" cy="{y+cs*0.4}" r="{cs*0.30}" '
                             f'fill="rgba(255,255,255,0.22)"/>')
            elif a != "raw" and c == "plain":
                if a == "full" or b == "two":   # 全熔/双面: 光滑高光
                    p.append(f'<circle cx="{x+cs*0.38}" cy="{y+cs*0.38}" r="{cs*0.30}" '
                             f'fill="rgba(255,255,255,0.10)"/>')
            parts.append("".join(p))
        s.append("".join(parts))
    s.append('</g>')
    if a != "raw":
        gloss = "0.06" if a == "semi" else "0.12"
        s.append(f'<rect width="{Wt}" height="{Ht}" fill="rgba(255,255,255,{gloss})"/>')
        if b == "two":
            s.append(f'<rect x="6" y="6" width="{Wt-12}" height="{Ht-12}" fill="none" '
                     f'stroke="rgba(255,255,255,0.35)" stroke-width="3" rx="6"/>')
    s.append('</svg>')
    return Response("".join(s), media_type="image/svg+xml")


@app.get("/api/file/{job}/{fname}")
def api_file(job: str, fname: str):
    if fname not in FILE_SET:
        raise HTTPException(404, "文件不存在")
    path = os.path.join(_job_dir(job), fname)
    if not os.path.isfile(path):
        raise HTTPException(404, "文件不存在")
    media = {"pattern.html": "text/html", "beads.csv": "text/csv",
             "pattern.svg": "image/svg+xml", "pattern_overview.svg": "image/svg+xml",
             "pattern_grid.svg": "image/svg+xml", "pattern.json": "application/json",
             }.get(fname, "application/octet-stream")
    return FileResponse(path, media_type=media, filename=fname)


app.mount("/", StaticFiles(directory=os.path.join(HERE, "static"), html=True),
          name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8600, log_level="warning")
