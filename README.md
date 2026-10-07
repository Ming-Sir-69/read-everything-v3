# <picture><source media="(prefers-color-scheme: dark)" srcset="assets/hero-dark.png"><img alt="Read Everything v3" src="assets/hero.png" width="100%"></picture>

**把文件转换为 Markdown，供人和 AI 按需阅读。**

Read Everything v3 根据文件类型选择 MarkItDown、视觉 OCR 或语音转写路径，将输出保存在原文件旁边，例如 `document.pdf.md`。适合整理 Office 文档、文字 PDF、扫描件与音视频转写材料；生成内容仍需要复核。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3-green)](https://www.python.org/)

仓库维护者：[Ming-Sir-69](https://github.com/Ming-Sir-69)。基础转换使用 Microsoft MarkItDown；其他组件的归属与链接见[致谢](#致谢)。

## 快速开始

从仓库根目录安装原有 Python 依赖，再转换一个可信的文件：

```bash
pip install "markitdown[all]" pypdfium2 pypdf dashscope openai requests Pillow
python3 scripts/read_everything_v3.py document.docx
# 输出：document.docx.md
```

Office 与结构化文档走 MarkItDown。文字 PDF 可走文本提取；PDF/图片的类型判定使用本机 Ollama，未能完成分类时会使用代码内的默认分类。环境与依赖版本需要在自己的机器上确认，仓库尚未提供锁定的 Python 依赖清单。

### 需要视觉 OCR 时

本地分类模型为 `qwen2.5vl:7b`，服务地址固定为 `http://localhost:11434`。已有 Ollama 后可按现有说明准备模型和启动服务：

```bash
ollama pull qwen2.5vl:7b
ollama serve
```

将示例配置复制到**脚本所在目录**，填写对应服务的 Key：

```bash
cp scripts/read_everything_config.example.json scripts/read_everything_config.json
python3 scripts/read_everything_v3.py document.pdf --verbose
```

当前代码读取 `scripts/read_everything_config.json`，不会自动读取 `~/.read_everything_config.json`。部分旧支持文档仍写有 home 目录路径，请以脚本的 `CONFIG_PATH` 为准。示例配置含占位值，真实配置不得提交到 Git。

| 配置键 | 当前用途 | 服务入口 |
| --- | --- | --- |
| `gemini` | Gemini 2.5 Flash，首选视觉 OCR/描述 | [Google AI Studio](https://aistudio.google.com/apikey) |
| `nvidia_nim` | NVIDIA NIM 的 Qwen3.5，视觉 OCR 备选 | [NVIDIA Build](https://build.nvidia.com) |
| `dashscope` | Qwen ASR 云端语音转写 | [阿里云百炼](https://bailian.console.aliyun.com) |

服务可用性、模型、价格和额度由各服务方决定，本文不承诺免费额度或免绑卡。云端分支会向相应服务提交输入内容，处理私密材料前请确认可上传范围。示例中的 `deepseek`、`moonshot` 键未被当前核心脚本使用。

### Docker

仓库提供的镜像以 Python 3.13 构建，安装 Python 依赖和 ffmpeg。先从本地文件转换开始：

```bash
docker build -t read-everything-v3 .
docker run --rm -v "$PWD:/data" read-everything-v3 document.docx
```

需要云端配置时，挂载到脚本实际读取的位置：

```bash
docker run --rm \
  -v "$PWD:/data" \
  -v "$PWD/scripts/read_everything_config.json:/app/read_everything_config.json:ro" \
  read-everything-v3 document.pdf
```

容器中的脚本位于 `/app/read_everything_v3.py`，所以配置路径是 `/app/read_everything_config.json`。镜像没有安装 Ollama、Whisper CLI 或本地模型；分类服务固定指向容器自身的 localhost，不能默认访问宿主机 Ollama。视觉分类与本地音视频分支需要另外准备匹配环境。

上述 PDF 示例在分类服务不可用时按 TEXT 路由进行文本提取，不执行云端 OCR；仅挂载云端配置不会改变这个回退。

### Windows

原说明提供 Python 入口，也可使用 Docker 或 WSL2：

```powershell
pip install "markitdown[all]" pypdfium2 pypdf dashscope openai requests Pillow
python scripts\read_everything_v3.py document.docx
```

本地 Whisper/ffmpeg 路径目前按 macOS 写死，不能据此保证 Windows 的音视频回退可用。优先从 Office/结构化文档开始确认环境。

## 格式与处理方式

以下是当前代码中的路由，表示实现入口，不是对所有文件的转换成功保证。

| 输入 | 处理方式 |
| --- | --- |
| `.docx .pptx .xlsx .xls` | MarkItDown |
| `.epub .html .csv .json .xml .ipynb .zip .msg` | MarkItDown |
| `.pdf` | 本地视觉分类后走文本提取、图文合并或 OCR |
| `.jpg .jpeg .png .webp .bmp .gif .tiff` | 本地视觉分类；文档类 OCR、照片描述、其他类跳过 |
| `.wav .mp3 .m4a .ogg .flac .opus .aac` | 云端 Qwen ASR，失败后尝试本地 Whisper |
| `.mp4 .mov .avi .mkv .webm` | 复用音频处理路径；不分析视频画面 |
| `.txt .md .py .js .ts .sh .yaml .yml .toml` | 直接读取并另存为 Markdown |

注意：JSON/CSV 走结构化文档分支，并非原文直接复制；音视频输出是转写结果，视频关键帧分析尚未提供。

## 架构与 OCR 复核

```text
输入文件
├─ Office / 结构化格式 → MarkItDown
├─ 纯文本 → 直接读取
├─ 音频 / 视频 → 云端 ASR / 本地 Whisper
└─ PDF / 图片 → Ollama 类型判定
   ├─ 文字 PDF → 文本提取
   ├─ 图文混合 PDF → 文字层 + OCR 合并
   ├─ 工程图 / 扫描 PDF / 文档图片 → 多轮 OCR
   ├─ 实拍照片 → 单轮描述
   └─ 其他图片 → 跳过
```

OCR 优先调用 Gemini，失败时尝试 NVIDIA NIM。前两轮结果使用文本相似度比较；存在差异时增加第三轮。当前实现是串行调用。第三轮仍有分歧时会输出带警告的结果；部分调用失败分支会保留已有单轮结果，并非始终等到共识才输出。

因此，多轮一致不等于事实正确，也不保证数字或工程尺寸准确。输出中的 `verified`、`rounds` 字段是程序记录，不能替代人工校对；重要数据应回看原件。

## 依赖与环境边界

| 依赖 | 用途 |
| --- | --- |
| `markitdown` | Office、结构化文档与文字 PDF 转换 |
| `pypdfium2`、`pypdf` | PDF 页面渲染与文字处理 |
| Ollama、`qwen2.5vl:7b` | 本地 PDF/图片类型判定 |
| `requests` | Gemini 调用 |
| `openai` | NVIDIA NIM 的兼容 API 客户端 |
| `dashscope` | 云端音频转写 |
| Whisper CLI、ffmpeg、本地语音模型 | 本地音视频回退 |

本地回退路径当前固定为 `/opt/homebrew/bin/whisper-cli`、`/opt/homebrew/bin/ffmpeg` 与 `/tmp/whisper-models/ggml-large-v3-turbo.bin`，模型和可执行文件不随仓库提供。Python 依赖安装不自动准备这些系统组件。

## 目录导航

| 位置 | 内容 |
| --- | --- |
| [scripts/read_everything_v3.py](scripts/read_everything_v3.py) | 转换与 CLI 入口 |
| [scripts/read_everything_config.example.json](scripts/read_everything_config.example.json) | Key 占位模板 |
| [Dockerfile](Dockerfile) | 镜像构建与入口 |
| [SKILL.md](SKILL.md) | AI 工作流定义 |
| [references/architecture.md](references/architecture.md) | 原架构说明 |
| [references/boundary-matrix.md](references/boundary-matrix.md) | 工具选择边界 |
| [references/v2-v3-migration.md](references/v2-v3-migration.md) | 迁移记录 |
| [SUPPORT.md](SUPPORT.md)、[SECURITY.md](SECURITY.md) | 帮助与漏洞报告方式 |
| [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) | 社区行为准则 |
| `assets/` | 封面图 |

## 状态与后续方向

代码包含 PDF/图片分类、多轮 OCR、工程图解读与模型降级路径。实际结果受输入质量、环境与外部服务影响，仓库文档未提供足以概括所有场景的性能结论。

原路线图保留以下待完成方向：

- 视频关键帧与画面分析。
- MCP Server 模式。
- 批量转换与进度显示。
- MarkItDown OCR 插件集成。

## 常见问题

**找不到 API Key？** 当前读取脚本同目录的 `read_everything_config.json`；本地仓库运行时放在 `scripts/`，容器挂载到 `/app/`。不要提交真实 Key。

**输出数字可信吗？** 多轮文本一致性只能帮助发现分歧，不能消除模型识别错误。重要数字、字段与工程尺寸需要回看原文件。

**Gemini 与 NVIDIA 都不可用？** 首轮两者均失败会返回错误；后续轮失败的处理方式不同，可能保留已有结果。请阅读输出与警告。

**输出写到哪里？** 写入原文件旁的 `<输入文件名>.md`，同名文件会被覆盖。使用可信文件，并确保输出目录可写。

## 参与贡献

欢迎通过 [Issues](https://github.com/Ming-Sir-69/read-everything-v3/issues) 或 Pull Request 提交可复现的格式问题、环境兼容性与文档修正。请注明输入类型、平台、依赖版本和脱敏错误；涉及私密文件时使用最小化示例。漏洞报告方式见 [SECURITY.md](SECURITY.md)，社区规范见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

## 致谢

| 项目/服务 | 用途 | 来源 |
| --- | --- | --- |
| Microsoft MarkItDown | 文档转换基础引擎 | [microsoft/markitdown](https://github.com/microsoft/markitdown) |
| Ollama | 本地视觉模型服务 | [ollama.com](https://ollama.com) |
| Google Gemini | 首选云端 OCR | [Google AI Studio](https://aistudio.google.com) |
| NVIDIA NIM | 备选云端 OCR | [NVIDIA Build](https://build.nvidia.com) |
| 阿里云 DashScope | 云端语音转写 | [百炼](https://bailian.console.aliyun.com) |

第三方组件和服务仍适用各自的许可与使用条件。

## 许可证

[MIT](LICENSE) © 2026 Eric Mingle ([Ming-Sir-69](https://github.com/Ming-Sir-69))
