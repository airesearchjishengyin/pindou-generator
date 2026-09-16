# 拼豆图纸生成器行业 AI 技术应用现状调研

> **摘要**：拼豆（Perler/Hama/Artkal/MARD）图纸生成器的主流技术仍是「下采样 + 量化 + 色距匹配」的确定性图像算法，AI 的真正用武之地集中在背景移除（rembg）、AI 风格化/Q版化、LLM 视觉质检与自然语言辅助四个环节；「AI 像素生成」「AI 上采样」等宣传多为营销包装，行业几乎无人用 AI 做放大或主体检测，这两处恰是自研产品的差异化机会。

*本文所有产品信息均经 web_search / 页面抓取 / GitHub README 实际查证（2026-09 调研）。*

## 一、产品全景（均已查证）

| 产品 | 类型 | 核心能力（查证摘要） |
|---|---|---|
| PixelBeads (pixel-beads.com) | 在线站 | 浏览器内处理；自动配色到 Perler/Hama/Artkal/MARD；网格 10–200；编辑、PNG/PDF 导出 |
| PixelBeads (pixelbeads.io) | 中文在线站 | 拼豆/像素画/Minecraft 三合一；MARD/COCO/PERLER/HAMA 色盘；网格 20–128、色数 10–120；图纸广场社区 |
| BeadForge (beadforge.com) | 在线站 | 纯浏览器端（"processes images on your device"）；4 品牌色卡（Perler 103/Hama 92/Artkal 199/Nabbi 30，源自 BeadColors 社区数据）；「逐像素测量与珠色的真实色距」；亮度/对比度/饱和度/抖动调节；背景移除开关；多板 PDF |
| MakeBead (makebead.com) | 在线站 | 纯浏览器端；715 色 5 品牌（含 MARD 185/221/291）；「加权 RGB 算法」匹配；Floyd–Steinberg 抖动；吸管+容差背景透明化；flood fill 编辑；多板 PDF |
| Fuse Bead Maker (fusebeadmaker.com) | 在线站 | 相似度/色板调节（96/144/168 色系统）；刷子/擦除/替换编辑；PDF/PNG/CSV 导出 |
| BeadsHub (beadshub.net) | 在线站 | 浏览器生成器；Perler/Hama/Artkal/MARD 色板；PDF 导出；MARD 图纸社区 |
| FuseBeads Hub (fusebeads.cc) | 在线站 | 自称「免费 AI 驱动的拼豆图纸生成器」；可上传图片或「描述你想做的图案」；AI 灵感生成栏目；9 品牌色卡（Artkal/MARD/Kaka/Coco/Manman/Panpan/Perler/Hama/Nabbi）；魔棒/对称工具 |
| BeadCraft (github.com/lixin0304/BeadCraft) | 开源 | FastAPI + Pillow/NumPy；CIE Lab 欧氏色距；Artkal 221 色（96–221 预设）；Floyd–Steinberg；量化管线 = LANCZOS 抗锯齿 + 调色板量化 + mode-pool 下采样（自称借鉴 PixArt-Beads）；管线内含背景移除、稀有色清理(<0.5%)、颜色合并、最大色数上限 |
| PixArt-Beads (github.com/Chipdelmal/PixArt-Beads) | 开源 | Python 脚本：颜色量化（自定义调色板/色数）、图像下采样、手动颜色映射去背景、每色珠数统计 |
| KuoGTR/perler-beads-generator | 开源 | 纯前端单文件；Delta E CIE76 (LAB) 色距匹配；72 色 Hama/Artkal 色板；饱和度/对比度调节；色量统计；HD PNG |
| Jett-Wu/Perler_Beads_Generator | 开源 | MARD 色卡配色；按每格对应原图区域采样（非单像素）；分层、3D 预览、高清导出 |
| Pindou-Studio (Aswellle/Pindou-Studio) | 开源 | **K-means++ 取色 + CIEDE2000 色距匹配**；六大品牌色卡（Perler/Hama/Artkal/COCO/MARD 等）跨品牌重映射 |
| pypindou (HansBug/pypindou) | 开源库 | 纯 Python；默认 MARD 221 色卡；RGB/Lab 距离；Floyd–Steinberg；孤立色块清理 |
| pindou-agent (NoraXu-0111/pindou-agent) | 开源 | 宠物照→MARD 图纸：确定性管线（**rembg 背景移除** → 下采样 → median-cut 量化 → CIELAB 匹配 → 去噪点 → 描边）+ **Claude 视觉质检循环**（评分、重调参数重跑至多 3 次）+ **Claude 解析特征声明**（"黄毛白胸粉舌头"→结构化颜色规格，量化向声明色吸附） |
| PindouAI / 拼豆AI (xuange6610、aat.ee、pindouai-mcp-server) | 开源 App + 在线 + MCP | **AI 卡通化（照片→Chibi/Q版）**、**自动背景移除**、精确色卡匹配、PDF 蓝图；官方 MCP server 供 Claude/Cursor 调用 |
| PerlerBead Pattern Maker (App Store) | iOS App | 自称 AI 驱动：照片→图案的「AI 像素艺术生成」；多风格（像素风/8-bit/线稿/Big Face/chibi 平涂/卡通插画）；支持背景移除、色码、用量统计；兼出十字绣图 |
| AI Fuse Bead Pattern Maker (App Store) | iOS App | **AI 卡通化**（简化主体为大胆色块）、**AI 背景移除**（纯白背景）、直接转换三选一；空白画布（29–116 pegboard）；文本模式（≤60 字符→像素文字图）；AI 处理按"豆点"计费 |

> 注：任务清单中的 Mdtcy/perler-bead-pattern-maker 调研时仓库已 404（搜索索引可见但不可访问），未计入。

## 二、按「AI 在管线中的位置」分类汇总

### 1. AI 背景移除 / 抠图
- **pindou-agent**：管线第一步用 **rembg**（U²-Net 深度学习分割模型）去背景，是全行业唯一把深度学习抠图写进确定性管线的开源项目。
- **PindouAI**：标注 "Auto Background Removal"；**AI Fuse Bead Pattern Maker**：AI 抠图并补纯白背景；**PerlerBead Pattern Maker**：支持背景移除。
- **对照（非 AI 经典算法）**：BeadForge 背景移除开关、MakeBead 吸管+容差透明化（可处理抗锯齿边缘）、BeadCraft 管线内背景移除、PixArt-Beads 手动颜色映射去背景。
- 结论：AI 抠图（分割模型）是照片转拼豆效果提升最大的单点，且 rembg 离线可跑、结果确定可复现。

### 2. AI 上采样 / 细节增强
- **真实结论：行业内基本空白**。所有被调研产品做的都是**下采样**到目标网格（BeadCraft LANCZOS 下采样、PixArt-Beads 按像素数下采样、pixelbeads.io 按网格长边缩图），没有任何拼豆产品宣传 AI 上采样。通用 AI 放大服务（Picsart Upscale、Replicate/PrunaAI 等）存在，但未被拼豆工具集成。
- 原因合理：拼豆输出是 10–200 格的极低分辨率网格，AI 放大（Real-ESRGAN 类）补充的细节在有限色卡+有限格数下根本无法表达，反而制造噪声。App 宣称的「AI 像素艺术生成」实质是重绘/风格化，不是放大。

### 3. AI 颜色匹配与调色板优化
- 主流全部是经典色彩科学，非 AI：CIE Lab 欧氏距离（BeadCraft）、CIE76 Delta E（KuoGTR）、CIEDE2000（Pindou-Studio）、加权 RGB（MakeBead）、RGB/Lab 最近色（pypindou）、MARD 区域采样（Jett-Wu）。
- 唯一的「机器学习」元素：**Pindou-Studio 的 K-means++ 自适应取色**（无监督聚类提取主色后做色距匹配）。
- 工程化调色板优化（各产品通用）：最大颜色数上限与品牌预设子集（BeadCraft 96–221、Fuse Bead Maker 96/144/168、PixelBeads 色数 10–120、MakeBead max colors）、稀有色清理与相近色合并（BeadCraft/pypindou）。
- 前沿用法：pindou-agent 用 Claude 把用户自然语言特征声明解析成结构化颜色规格，量化时向"声明的颜色"吸附——LLM 参与调色的真实案例。

### 4. AI 图案生成（文本→图案）
- **FuseBeads Hub**：首页即「上传图片或**描述你想做的图案**」，设有 AI 灵感生成栏目——文本/提示词入口生成。
- **AI Fuse Bead Pattern Maker**：文本模式（≤60 字符→像素文字图，属排版而非生成式）。
- **拼豆AI (aat.ee)**：prompt 或照片生成 ACNH 风格角色（text-to-image 再转拼豆）。
- **PerlerBead Pattern Maker**：AI 像素艺术生成入口。
- 结论：文本→图案是 App/在线站最常打的 AI 卖点，但生成结果不可控（色数爆炸、无法构建），必须后接确定性量化管线约束。

### 5. AI 主体检测 / 自动裁剪
- **行业空白**。没有任何产品把「主体检测/自动裁剪」作为 AI 功能售卖：pixel-beads.com 只指导用户手动裁切、选简单背景；fusebeads.cc 只建议主体占满画面。pindou-agent 的 Claude QC 会对轮廓（silhouette）评分——间接评估主体质量，但无自动裁剪。
- 这是明确的机会点：分割模型（rembg 同源技术）天然可以做「检测主体→自动裁剪→去背景→量化」。

### 6. AI 风格化（Q版化 / 卡通化）
- **PerlerBead Pattern Maker**：多风格生成（像素风、8-bit、线稿、Big Face 大头贴、chibi Q版、平涂、卡通插画）——面向小红书人群的主打卖点。
- **AI Fuse Bead Pattern Maker**：AI 卡通化把照片简化为大胆色块。
- **PindouAI**：AI 卡通化→Chibi/Q版设计。
- 技术手段：均为图像到图像的风格化模型（具体架构未公开，属卡通化生成模型一类），App 内通常按次计费（"豆点"）。
- 结论：Q版化是 C 端付费意愿最强的 AI 功能，但方向与「忠实还原照片」冲突，宜作为可选风格通道。

### 7. LLM / 对话式辅助
- **pindou-agent（最深集成）**：Claude 双角色——(a) 视觉 QC 评委：对预览图按轮廓/五官/噪声/描边打分，参数重调并重跑至多 3 次；(b) 特征声明解析器：自然语言→结构化颜色规格，并保留舌头/腮红等小点缀。附确定性回归评测（4 张照片、15 项断言）。
- **PindouAI MCP Server**：把拼豆生成能力封装成 MCP 工具，供 Claude Desktop/Cursor 等 Agent 直接调用——对话式 Agent 编排的行业首例。
- **FuseBeads Hub**：文本描述入口（LLM 生成）。
- 结论：LLM 最适合做「质检闭环」和「自然语言参数化」，而不是直接生成像素。

## 三、真伪 AI 判别与自研建议

**真正值得用 AI 的环节**：
1. **背景移除**（rembg/U²-Net）：离线、确定、性价比最高，照片类输入必备。
2. **LLM/VLM 质检闭环**（pindou-agent 模式）：把"好不好看"变成可自动迭代的评分循环，是开源界最新、最难抄的差异化。
3. **自然语言辅助**：特征声明解析、文本→图案提示词，成本低、感知价值高。
4. **AI 风格化/Q版化**：仅当目标用户是萌宠/人像 C 端市场时值得做，需独立计费。

**属于营销噱头的环节**：
1. 「AI 像素艺术生成」：多数 App 的包装，内核仍是量化+抖动+色距匹配的经典算法。
2. **AI 上采样/细节增强**：与拼豆「低格数+有限色卡」的物理约束矛盾，方向错误，别做。
3. 把经典色距匹配（CIE Lab/CIEDE2000）包装成「AI 智能配色」——诚实标注（如 BeadForge/MakeBead）反而更可信。

**对自研（图片→MARD 色卡图纸，Python+FastAPI）的具体建议**：
- 核心管线保持确定性：下采样（LANCZOS）→ K-means++ 或 median-cut 提取主色（可选）→ CIEDE2000/CIE76 匹配 MARD 221 色 → Floyd–Steinberg 抖动（可调强度）→ 稀有色清理/相近色合并/最大色数上限（参考 BeadCraft、pypindou 已验证方案）。
- 增加 rembg 背景移除作为可选前置，配合分割模型做「主体检测+自动裁剪」——行业空白，是最大差异化机会。
- 借鉴 pindou-agent 引入 VLM 质检循环 + 特征声明解析；封装 MCP server 让 Agent 可调用（参考 PindouAI）。
- 架构范式：「AI 出图/抠图 + 确定性量化 + LLM 质检兜底」，绝不让生成模型直接输出网格。
