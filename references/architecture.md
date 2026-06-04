# Read Everything v3 — 架构设计

> 最后更新：2026-06-04
> 状态：架构确认，开始编码

---

## 0. 核心定位转变

| 版本 | 理念 | 输出 |
|------|------|------|
| v2 (old) | 读取 → 输出到**对话上下文** | 打印到 stdout → 污染上下文 → 幻觉风险 |
| **v3 (new)** | 读取 → 转换 → **写入 .md 文件** | 保存到原文件旁边 → AI 按需 Read → 上下文干净 |

**v3 不输出到对话。它生成 `.md` 文件，让 AI 自己去读。**

这跟 MarkItDown 的设计哲学一致：把一切文件变成 Markdown，格式保留，token 高效，按需加载。

---

## 1. 接口

```python
from read_everything_v3 import read_everything

result = read_everything("/path/to/file.pdf")
# → 输出文件: /path/to/file.md
# → 返回: {"ok": True, "output": "/path/to/file.md", "type": "TEXT|ENGINEERING|...", "engine": "markitdown|gemini-flash|...", "rounds": 2, "verified": True}
```

---

## 2. 全格式路由

```
输入文件
  ├─ .docx/.pptx/.xlsx/.xls  → MarkItDown → <filename>.md
  ├─ .epub/.html/.csv/.json/.xml/.ipynb/.zip/.msg → MarkItDown → .md
  ├─ .pdf → [本地 VL 判定类型] → 分流处理 → .md
  ├─ .jpg/.jpeg/.png/.webp/.bmp → [本地 VL 判定类型] → .md
  ├─ .wav/.mp3/.m4a/.ogg → qwen-asr / whisper → .md
  └─ .mp4/.mov → ffmpeg→whisper → .md
```

---

## 3. PDF 类型判定 + 分流

用 `qwen2.5vl:7b` 本地 VL 渲染首页（scale=0.8），输出分类词。

| 类型 | 定义 | 处理 |
|------|------|------|
| `TEXT` | 纯文字页面，无嵌入图片/Logo | **MarkItDown 直接提取** — 不调大模型，不交叉验证 |
| `MIXED` | 文字 + 嵌入图片/海报/图表 | MarkItDown 提取文字层 + 渲染各页 → Gemini Flash OCR 图片层 → **合并** → .md |
| `ENGINEERING` | 工程图纸（有尺寸/公差/坐标系） | Gemini Flash 两轮交叉验证 + 空间解读 → .md |
| `OTHER` | 纯扫描件/图像页 | 同 ENGINEERING 流程 |

**为什么 TEXT 类不交叉验证**：文本层可靠，提取即原文，交叉验证是画蛇添足。

---

## 4. 图片类型判定 + 分流

| 类型 | 定义 | 处理 |
|------|------|------|
| `TEXT_IMAGE` | 文档截图/表格截图/扫描件 | Gemini Flash 两轮交叉验证 → .md |
| `POSTER` | 海报/邀请函/信息图 | Gemini Flash 两轮交叉验证 → .md |
| `PHOTO` | 实景照片 | AI 描述（单轮） → .md |
| `OTHER` | 艺术图/抽象图 | 跳过，不生成 .md |

---

## 5. 交叉验证引擎

仅用于非 TEXT 类（ENGINEERING / MIXED / OTHER / TEXT_IMAGE / POSTER）。

```
首选  Gemini 2.5 Flash   (Google AI Studio, 1500次/天免费)
备选  NVIDIA Qwen3.5     (NVIDIA NIM, 免费credits)
兜底  停止 + 告知用户
```

```
同一个 prompt，跑两轮：
  ├─ 两轮一致 → 直接输出 ✅
  └─ 两轮不一致 → 分析差异 → 优化 prompt → 第三轮
      ├─ 第三轮与某一轮一致 → 输出该内容
      └─ 三轮各不同 → 标注 [⚠️ 未通过交叉验证，需人工确认]
```

两轮并行发出，不串行等待。

MIXED 类型特殊处理：MarkItDown 文本层 + Gemini Flash 图片层结果做**并集合并**（MarkItDown 文字在前，OCR 补漏的图片文字在后）。

---

## 6. 空间解读

仅 ENGINEERING 类型输出后半段。基于坐标网格建立尺寸→区域→部件对应关系。

---

## 7. 提示词体系（4 套）

| 模板 | 用在哪 |
|------|------|
| **通用 OCR** | TEXT_IMAGE, POSTER — 逐字转录 |
| **工程图 OCR + 空间解读** | ENGINEERING — 结构化提取 + 坐标对应 |
| **混合文档合并** | MIXED — 文本层结果 + 图片层 OCR 合并且去重 |
| **图片描述** | PHOTO — 非 OCR 的描述性输出 |

不为每种类型写一篇提示词。4 套公共模板 + 类型参数注入。

---

## 8. 五大维度保障

| 维度 | 手段 |
|------|------|
| **准确性** | 两轮交叉验证 + 三轮兜底 + 不一致标注 |
| **完整性** | 类型适配提示词 + MIXED 类文本+图片合并 |
| **免费额度** | 本地 VL 判定零消耗 + Gemini 1500次/天 + NVIDIA 免费 |
| **稳定性** | 三层降级 + 模型间轮换 |
| **输出结构** | Markdown 表格 + 分节 + 空间解读段 |

---

## 9. 依赖

| 依赖 | 用途 |
|------|------|
| `markitdown` | Office/结构化文档 |
| `pypdfium2` + `pypdf` | PDF 渲染 + 文本提取 |
| `ollama` + `qwen2.5vl:7b` | 本地类型判定 |
| `requests` + 配置文件 | API 调用（Gemini / NVIDIA） |
| `dashscope` | 音频转录（qwen-asr） |
| `whisper-cpp` | 音频本地降级 |
