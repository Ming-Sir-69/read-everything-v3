---
name: read-everything-v3
description: >
  将任何文件转换为 Markdown。输入 PDF/图片/Office/音频/视频，输出 <原文件名>.md 保存在原文件旁边。
  不污染上下文，让 AI 按需读取。触发：用户说「读这个文件」「转成MD」「读取XX」「这个PDF/图片/音频里有什么」「帮我提取XX的文字」。
  PDF 四分类自动路由（TEXT→直接提取 / MIXED→文本+图片合并 / ENGINEERING→交叉验证+空间解读 / OTHER→全页OCR）。
  图片四分类路由（TEXT_IMAGE→OCR / POSTER→OCR / PHOTO→描述 / OTHER→跳过）。
  非文本类两轮交叉验证（首选 Gemini Flash 免费，备选 NVIDIA NIM 免费），三轮不一致不输出。
---

# Read Everything v3 — 文件→Markdown 转换器

## 定位

v3 不是"读取文件输出到对话"，而是**将任何文件转换为 Markdown 文件**，保存在原文件旁边（`原文件名.md`）。

AI 需要内容时用 Read 工具按需读取，上下文保持干净。

## 一句话命令

```bash
python3 ~/.claude/skills/read-everything-v3/scripts/read_everything_v3.py <文件路径>
```

输出：`<文件路径>.md`

---

## 支持格式

| 输入 | 引擎 | 输出 |
|------|------|------|
| `.docx .pptx .xlsx .xls` | MarkItDown | 结构化 Markdown |
| `.epub .html .csv .json .xml .ipynb .zip .msg` | MarkItDown | Markdown |
| `.pdf` | [本地 VL 判定类型] → MarkItDown 或 Gemini Flash/NVIDIA | Markdown |
| `.jpg .jpeg .png .webp .bmp` | [本地 VL 判定类型] → Gemini Flash/NVIDIA | Markdown |
| `.wav .mp3 .m4a .ogg .flac` | qwen-asr 云端 / whisper-cpp 本地 | 转录文本 |
| `.mp4 .mov .avi .mkv` | ffmpeg 提取音频 → whisper-cpp 转录 | **音频转录文本** |
| `.txt .md .json .csv .py` | 直接读取 | 原文 |

> **视频处理说明**：v3 当前版本对视频的处理是**提取音频轨道转录为文字**（同音频流程），**不做逐帧截图和视觉分析**。此能力预留为后续扩展——如需分析视频画面（PPT 录屏中的文字、操作演示中的 UI），可通过关键帧提取 + Gemini Flash 视觉 OCR 实现，架构上路由已预留。

---

## PDF 处理流程（重点）

### 类型判定

用 `qwen2.5vl:7b`（Ollama 本地）渲染首页判定类型，约 10 秒/文件，零 API 消耗。

| 类型 | 判定标准 | 处理 |
|------|------|------|
| `TEXT` | 纯文字页面，无嵌入图片/图表 | MarkItDown 直接提取 |
| `MIXED` | 文字 + 嵌入图片/海报/Logo | MarkItDown 文字层 + Gemini OCR 图片层合并 |
| `ENGINEERING` | 工程图纸（尺寸/公差/坐标系/标题栏） | Gemini Flash 两轮交叉验证 + 空间解读 |
| `OTHER` | 纯扫描件/图像页 | 同 ENGINEERING |

### TEXT 类型 — 不调大模型，不交叉验证

文本层可靠，提取即原文。MarkItDown (pdfplumber) 保留 Markdown 结构。

### 非 TEXT 类型 — 交叉验证

```
首选  Gemini 2.5 Flash   (Google AI Studio, 1500次/天免费)
备选  NVIDIA Qwen3.5     (NVIDIA NIM, 免费 credits)
兜底  停止 + 告知用户
```

同 prompt 跑两轮：
- 两轮一致 → 直接输出
- 两轮不一致 → 分析差异 → 优化 prompt → 第三轮
- 三轮各不同 → 标注 `[⚠️ 未通过交叉验证]`

---

## 图片处理流程

| 类型 | 判定标准 | 处理 |
|------|------|------|
| `TEXT_IMAGE` | 文档截图/表格截图/扫描件，目的是提取文字数字 | Gemini Flash 两轮交叉验证 OCR |
| `POSTER` | 海报/邀请函/信息图，设计性文字+图像 | Gemini Flash 两轮交叉验证 OCR |
| `PHOTO` | 实景照片/产品实物 | AI 描述（单轮） |
| `OTHER` | 艺术图/抽象装饰图 | 跳过 |

---

## 配置要求

编辑 `~/.read_everything_config.json`：

```json
{
  "gemini": "你的Google-AI-Studio-key",
  "nvidia_nim": "你的NVIDIA-NIM-key",
  "dashscope": "你的阿里云百炼-key(音频用)",
  "deepseek": "...",
  "moonshot": "..."
}
```

**Ollama 依赖**（类型判定用）：
```bash
brew install ollama          # 如未安装
ollama pull qwen2.5vl:7b     # 约 6GB，本地推理
ollama serve                 # 确保服务运行
```

`qwen2.5vl:7b` 已存在于铭哥 M4 Mac 上，无需重新下载。

---

## API 用法

```python
from read_everything_v3 import read_everything

result = read_everything("/path/to/file.pdf")
# → 生成 /path/to/file.pdf.md
# → 返回: {"ok": True, "output": "/path/to/file.pdf.md", "type": "TEXT|ENGINEERING|...", "engine": "markitdown|gemini-flash", "rounds": 2, "verified": True}

result = read_everything("/path/to/image.jpg", verbose=True)
```

---

## 与旧版 read-everything / MarkItDown 关系

```
MarkItDown           → v3 内部用作 Office + TEXT PDF 文档提取引擎
Read Everything v2   → 保留音频/视频后端（qwen-asr + whisper-cpp）
read-everything-v3   → 编排层 + 类型判定 + 交叉验证 + 空间解读 + 文件输出
```

---

## 项目路径

- 脚本: `~/.claude/skills/read-everything-v3/scripts/read_everything_v3.py`
- 架构文档: `~/.claude/skills/read-everything-v3/references/architecture.md`
- 测试基准: `~/.claude/skills/read-everything-v3/scripts/bench_output/`
- 配置文件: `~/.read_everything_config.json`
