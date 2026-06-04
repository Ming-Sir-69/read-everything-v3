# Read Everything v3 — 文件处理边界矩阵

> 核心原则：MarkItDown 底座 + RE 补充。v3 对调用者不暴露"用了哪个工具"。

---

## 1. 边界决策矩阵（最终版）

| 文件类型 | 子类型判断 | 选哪个 | 为什么 |
|---------|-----------|:---:|------|
| **.docx** | — | **MarkItDown** | mammoth→HTML→MD，保留标题/表格/列表，远超 RE 纯文本 |
| **.pptx** | — | **MarkItDown** | python-pptx 结构解析：标题层级 + 表格 + 图表 + 备注 + 图片 alt |
| **.xlsx / .xls** | — | **MarkItDown** | pandas+openpyxl，每 sheet 独立表格，HTML→MD 保留结构 |
| **.pdf** | 文字型（有文本层） | **MarkItDown** | pdfplumber 表格提取 + 结构保留，实测与 RE 中文精度相同 |
| **.pdf** | 工程图/扫描件（无文本层 或 文本层混乱） | **Qwen-VL** (RE 后端) | pdfplumber 对工程图输出乱码表格，Qwen-VL 按视觉理解输出干净文字 |
| **图像 .jpg/.png** | 需要忠实 OCR | **Qwen-VL 云端** / PaddleOCR 本地降级 | MarkItDown 的图像处理是 AI 描述，非文字提取 |
| **图像 .jpg/.png** | 需要 AI 描述 | **MarkItDown (LLM)** | 多模型兼容，可设为 qwen-vl-max 等同于单个调用 |
| **音频 .ogg/.mp3/.wav/.m4a** | — | **qwen-asr 云端** / whisper-cpp 本地降级 | MarkItDown 的音频依赖重且不支持 .ogg |
| **音频 .wav/.mp3** (无网络) | — | **whisper-cpp** (RE 后端) | MarkItDown 也可用，但 whisper-cpp 离线免费 |
| **视频 .mp4/.mov/.avi/.mkv** | — | **ffmpeg→whisper** (RE 后端) | MarkItDown 不支持视频 |
| **.epub** | — | **MarkItDown** | RE 不支持 |
| **.html / .csv / .json / .xml / .ipynb** | — | **MarkItDown** | RE 简陋 |
| **.zip** | — | **MarkItDown** | 递归遍历转换，RE 不支持 |
| **.msg (Outlook)** | — | **MarkItDown** | RE 不支持 |
| **YouTube URL** | — | **MarkItDown** | 字幕提取，RE 不支持 |
| **Wikipedia URL** | — | **MarkItDown** | RE 不支持 |
| **纯文本 .txt/.md** | — | 直接 read | 不需要任何工具 |

---

## 2. PDF 文字型 vs 工程图 判别逻辑（关键）

这是唯一需要智能判断的边界。判别依据：

```
PDF 文件
  │
  ├─ 有文本层（pypdf 提取 text > 500 chars 且 中文连续率 > 0.7）
  │   → MarkItDown (pdfplumber)   // 文字型：表格 + 结构保留
  │
  └─ 无文本层（扫描件）或 文本层混乱（工程图，提取的是乱序坐标数字）
      → Qwen-VL 云端  // 视觉理解
        降级: PaddleOCR 本地
```

**中文连续率**：提取的文本中，连续的 Unicode 中文标点 + 汉字占比。文字型 PDF > 0.7，工程图 < 0.3（因为 pdfplumber 把图纸坐标当数字分散输出）。

---

## 3. 两工具在 v3 中的取舍原则

### 全用 MarkItDown 的场景
- 所有 Office 文档 (.docx/.pptx/.xlsx/.xls)
- 文字型 PDF
- 结构化格式 (.epub/.html/.csv/.json/.xml/.ipynb/.zip/.msg)
- URL 类 (YouTube/Wikipedia/RSS)

> 原因：MarkItDown 的核心价值是 **保留语义结构 → Markdown**，不是纯文本提取。

### 全用 Read Everything 后端的场景
- 工程图/扫描件 PDF（视觉理解）
- 图片 OCR（忠实文字提取，非 AI 描述）
- 音频转录（格式覆盖广，qwen-asr 快 36x RT）
- 视频转录（MarkItDown 不支持）

> 原因：RE 的价值是 **多后端的兜底能力** + **中文 OCR/ASR 优化**。

### 不用的
- RE 的 OfficeBackend（纯文本，比 MarkItDown 差太多）
- RE 的 LocalTextBackend 用于文字 PDF（MarkItDown 结构更好，中文精度实测相同）
- RE 的 CloudVisionBackend 用于图像 AI 描述（MarkItDown 的 LLM 图像描述更标准化，且支持多模型）

---

## 4. v3 对调用者暴露的统一接口

```python
# 一个函数搞定，内部黑盒
result = read_everything("file.pdf")   # 自动判别 PDF 类型
result = read_everything("file.docx")  # → MarkItDown
result = read_everything("audio.ogg")  # → qwen-asr

# result 统一格式
# {
#   "text": "...",          # 文本内容（Markdown 或纯文本）
#   "engine": "markitdown/pdfplumber",  # 实际使用的引擎
#   "format": "markdown",   # "markdown" | "plaintext"
#   "elapsed": 0.5,         # 秒
# }
```
