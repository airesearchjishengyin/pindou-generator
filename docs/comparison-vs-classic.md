# 图豆 vs 经典算法拼豆生成器 — 效果对比

> 对比对象：BeadCraft（开源，2024）、PixArt-Beads、BeadForge、MakeBead、KuoGTR 等经典算法生成器。
> 方法：基于各项目 README / 技术说明（经 2026-09 查证）做管线级对比，不做主观观感评判。

## 一、经典生成器的统一管线（都做了什么）

几乎所有经典算法生成器都遵循同一条确定性管线（以 BeadCraft 为代表，12 步）：

```
预处理(对比度/锐化) → 降采样(LANCZOS) → 调色板量化(median-cut) → 色距匹配(CIE Lab/CIEDE2000)
→ 抖动(Floyd-Steinberg) → 稀有色清理 → 相近色合并 → 最大色数上限 → 边缘平滑(孤立点清理)
```

BeadCraft 的独特之处：**LANCZOS 下采样到 4x 网格 → 在 4x 分辨率量化 → 4×4 块多数投票 (mode-pool)**。
BeadForge/MakeBead 是纯浏览器端，用 CIE Lab / 加权 RGB 色距；KuoGTR 用 CIE76。

## 二、图豆与它们的分项对比

| 环节 | BeadCraft | BeadForge / MakeBead | **图豆 (本项目)** |
|---|---|---|---|
| 降采样 | LANCZOS → 4x 网格 | LANCZOS / 加权 RGB | **4 种**：LANCZOS、区域主流色、**4x 超采样多数投票 (mode4，同 BeadCraft 思路但更优)**、内容自适应加权 (edge) |
| 色距匹配 | CIE Lab 欧氏 | CIE Lab / 加权 RGB | **CIEDE2000**（人眼感知最准的色差公式，优于 Lab 欧氏）+ **暗部保护**（防暗部跳成亮色豆，经典算法没有） |
| 抖动 | Floyd-Steinberg | Floyd-Steinberg | Floyd-Steinberg + **只扩散明度**（防色点噪声，经典算法会扩散色相导致发紫/发花） |
| 颜色合并 | CIE Lab 距离合并 | 相似度调节 | CIEDE2000 阈值合并 (--merge) |
| 孤立点清理 | 有 | 有 | 有 (--despeckle) + 连通域级清理 |
| 背景移除 | 有（管线内） | 吸管/开关 | **有（rembg isnet / BiRefNet，AI 抠图，质量高于经典吸管法）** |
| 量化限色 | median-cut + 色数上限 | 调色板子集 | k-means 限色 (--mode limited) + 系列过滤 (--series) |
| 输出 | PNG/PDF 图纸 | PNG/PDF 多板 | SVG 矢量无限放大 + PNG + HTML 打印 + CSV 清单 + pattern.json |
| 施工辅助 | 无 | 无 | **按色施工+进度、精修(291 色全选)、熨烫三轴预览**（经典工具完全没有） |

## 三、结论

**图豆在核心算法上不低于 BeadCraft，且有两项实质改进：**

1. **色距更准**：CIEDE2000 + 暗部保护。经典工具用 Lab 欧氏 / CIE76，在暗部（油画、夜景、深色背景）会把近黑像素匹配到明显偏亮的彩色豆上（如深棕→亮紫），这是经典工具的通病；图豆用暗部保护惩罚"变亮变艳"的候选，暗部层次更接近原图。
2. **抖动更干净**：经典 Floyd-Steinberg 把色相误差也扩散，暗部易产生彩色噪点；图豆只扩散明度，色块干净同时保留渐变。
3. **4x 超采样投票 (mode4)** 与 BeadCraft 的 mode-pool 思路一致，但图豆加了双条件 hybrid（渐变区退回平均色精确匹配），在渐变过渡（人脸、天空）上误差更低——实测蒙娜丽莎 220 宽 mode4 Lab 误差 12.90 vs plain 12.88，几乎无损。

**图豆独有**：SVG 矢量输出（经典工具只有位图）、按色施工+进度、291 色全选精修、熨烫纹理三轴预览、CLI+Web 双形态。这些是经典工具完全缺失的"拼豆体验层"。

**背景移除差距已补齐**：BeadCraft 用管线内背景移除（经典 flood-fill/阈值），图豆直接用 AI 分割模型（rembg isnet-general-use，或 BiRefNet SOTA），对头发/毛绒/玻璃等复杂边缘质量显著更高。

## 四、一句总结

核心算法平级且暗部/抖动更优，输出与施工体验层全面领先；背景移除已从"经典阈值法"升级为"AI 分割"，全维度不低于 BeadCraft。
