## 2026-06-04: v2→v3 迁移记录

### 二合一决策

`read-everything-skill/`（v2，621 行）与 `read-everything-v3/` 合并。v2 所有能力已被 v3 覆盖且超越：

| v2 能力 | v3 去向 |
|---------|---------|
| pypdf 文本提取 | MarkItDown pdfplumber（结构更好） |
| Qwen-VL OCR | Gemini Flash 交叉验证（精确度完胜） |
| PaddleOCR 本地 | qwen2.5vl:7b 本地分类 + Gemini 云端 OCR |
| qwen-asr 音频 | 保留，同后端 |
| whisper-cpp 音频 | 保留，同后端 |
| Office 纯文本提取 | MarkItDown 结构化保留 |
| 智能路由 | v3 四分类路由 + 交叉验证 |

### 结果

- `read-everything-skill/` → 已删除（残留测试用 .md 文件保留原样）
- `read-everything-v3/` → 保留，已推送 GitHub https://github.com/Ming-Sir-69/read-everything-v3
