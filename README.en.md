<picture>
  <source media="(prefers-color-scheme: dark)" srcset="readme-assets/header-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="readme-assets/header-light.svg">
  <img alt="Read Everything v3 · ✦ EricMingle69" src="readme-assets/header-light.svg" width="100%">
</picture>

<p align="center">
  <a href="README.md">简体中文</a> · <a href="README.en.md">English</a> · <a href="PERSONAL-NOTICE.md">✦ EricMingle69</a>
</p>

# Read Everything v3

## Purpose

Selects document conversion, visual OCR or speech transcription by file type and writes Markdown beside the input file for people and AI to read.

## Repository guide

| Entry | Contents |
| --- | --- |
| [Conversion CLI](scripts/read_everything_v3.py) | Actual file processing and routing entry |
| [Configuration template](scripts/read_everything_config.example.json) | Cloud-service key placeholders |
| [Container definition](Dockerfile) | Python 3.13 and ffmpeg environment |
| [Architecture notes](references/architecture.md) | Processing-path background |
| [Boundary matrix](references/boundary-matrix.md) | Tool-selection notes |
| [AI workflow](SKILL.md) | Input/output and collaboration definition |
| [Support notes](SUPPORT.md) | Help entry; configuration-path correction below |
| [Security reporting](SECURITY.md) | Vulnerability reporting entry |

## Getting started

1. Begin with a trusted Office/structured file and prepare dependencies in your own Python environment:

```sh
pip install "markitdown[all]" pypdfium2 pypdf dashscope openai requests Pillow
python3 scripts/read_everything_v3.py document.docx
```

2. Output is `document.docx.md`; an existing output is overwritten, and the directory must be writable.
3. PDF/image classification uses Ollama `qwen2.5vl:7b` at `http://localhost:11434`. Cloud OCR prefers Gemini with NVIDIA NIM as fallback; audio uses DashScope ASR with local Whisper fallback.
4. Cloud configuration belongs in `scripts/read_everything_config.json`; copy the example and supply your own settings without committing real keys. The core script does not read home-directory configuration.

## Scope and limitations

- Office and structured formats such as JSON/CSV use MarkItDown; video reuses audio transcription without visual analysis, and some image types are skipped.
- Python dependencies are not pinned; Whisper, ffmpeg and local-model paths are hard-coded for macOS, so audio/video fallback on other systems is not guaranteed.
- Container configuration belongs at `/app/read_everything_config.json`. The image contains no Ollama, Whisper CLI or models; localhost refers to the container itself.
- If classification is unavailable, PDFs follow TEXT extraction without cloud OCR; mounting cloud configuration alone does not change that fallback.
- Multi-round OCR runs serially and can retain a single-round or warned result; agreement does not establish correctness. Check important numbers and engineering dimensions against the original.
- Cloud branches upload input content, with pricing and availability determined by providers; no accuracy or free-quota guarantee is made.

## Sources and existing licenses

[MIT](LICENSE) retains `Copyright (c) 2026 Eric Mingle (Ming-Sir-69)`. Document conversion uses [Microsoft MarkItDown](https://github.com/microsoft/markitdown); [Ollama](https://ollama.com), [Google Gemini](https://aistudio.google.com), [NVIDIA NIM](https://build.nvidia.com) and [Alibaba Cloud DashScope](https://bailian.console.aliyun.com) retain their own provenance, licenses and service terms.

---

Documentation maintained by **✦ EricMingle69** · [Ming-Sir-69](https://github.com/Ming-Sir-69)  
[Personal identity, licensing and permissions](PERSONAL-NOTICE.md) · The header follows your GitHub theme.
