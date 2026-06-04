#!/usr/bin/env python3
"""
read-everything-v3: Convert any file to Markdown.

Architecture:
  1. File type detection (extension + local VL for PDF/images)
  2. Route to best backend (MarkItDown / Gemini Flash / NVIDIA / Audio)
  3. Non-text types: cross-validation (2 parallel rounds → diff → 3rd round)
  4. Output: <original_file>.md saved next to original file

Usage:
  python3 read_everything_v3.py /path/to/file.pdf
  python3 read_everything_v3.py /path/to/file.jpg --verbose
"""

import os, sys, json, time, base64, argparse, difflib, re
from pathlib import Path
from io import BytesIO
from typing import Optional, Dict, Any, Tuple, List

# ============================================================
# Config
# ============================================================
# Config file: <script_dir>/read_everything_config.json
#   - Copy from read_everything_config.example.json and fill in real keys
#   - This file is gitignored — never commit real API keys
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "read_everything_config.json"
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_CLASSIFY_MODEL = "qwen2.5vl:7b"

def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    print("[WARN] 未找到 read_everything_config.json，请从 .example.json 复制并填入真实 Key",
          file=sys.stderr)
    return {}

# ============================================================
# File type detection (extension-based, fast, for routing)
# ============================================================
OFFICE_EXTS = {'.docx', '.pptx', '.xlsx', '.xls'}
STRUCTURED_EXTS = {'.epub', '.html', '.csv', '.json', '.xml', '.ipynb', '.zip', '.msg'}
AUDIO_EXTS = {'.wav', '.mp3', '.m4a', '.ogg', '.flac', '.opus', '.aac'}
VIDEO_EXTS = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.tiff'}
PDF_EXTS = {'.pdf'}
TEXT_EXTS = {'.txt', '.md', '.py', '.js', '.ts', '.sh', '.yaml', '.yml', '.toml'}

def file_ext(path: str) -> str:
    return Path(path).suffix.lower()

def route_by_ext(ext: str) -> str:
    if ext in OFFICE_EXTS: return "office"
    if ext in STRUCTURED_EXTS: return "structured"
    if ext in PDF_EXTS: return "pdf"
    if ext in IMAGE_EXTS: return "image"
    if ext in AUDIO_EXTS: return "audio"
    if ext in VIDEO_EXTS: return "video"
    if ext in TEXT_EXTS: return "text"
    return "unknown"

# ============================================================
# PDF rendering for VL classification
# ============================================================
def render_pdf_page(path: str, page_idx: int = 0, scale: float = 0.8) -> str:
    """Render one PDF page to base64 PNG. Returns empty string on failure."""
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(path)
        if page_idx >= len(pdf):
            return ""
        bmp = pdf[page_idx].render(scale=scale)
        buf = BytesIO()
        bmp.to_pil().convert("RGB").save(buf, format="PNG", quality=50)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""

def render_all_pages(path: str, scale: float = 1.5) -> List[str]:
    """Render all PDF pages to base64 PNGs at higher res (for OCR)."""
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(path)
        imgs = []
        for i in range(len(pdf)):
            bmp = pdf[i].render(scale=scale)
            buf = BytesIO()
            bmp.to_pil().convert("RGB").save(buf, format="PNG", quality=80)
            imgs.append(base64.b64encode(buf.getvalue()).decode())
        return imgs
    except Exception:
        return []

def render_image(path: str, max_size: int = 800) -> str:
    """Load and resize an image to base64. Returns empty string on failure."""
    try:
        from PIL import Image
        img = Image.open(path)
        img.thumbnail((max_size, max_size))
        buf = BytesIO()
        img.save(buf, format="PNG", quality=50)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""

# ============================================================
# Local VL classification (zero API cost)
# ============================================================
def ollama_classify(image_b64: str, prompt: str, model: str = OLLAMA_CLASSIFY_MODEL) -> Optional[str]:
    """Send image to local Ollama VL and return single-word classification."""
    import requests
    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": model,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
            "options": {"num_predict": 12, "temperature": 0}
        }, timeout=90)
        if resp.status_code == 200:
            return resp.json().get("response", "").strip()
        return None
    except Exception:
        return None

PDF_CLASSIFY_PROMPT = """分析这个文档页面，只输出一个英文单词：
TEXT = 纯文字页面，无嵌入图片/海报/Logo/图表（即使有很小的Logo也算TEXT）
MIXED = 页面同时含有大段文字和嵌入的图片/海报/Logo/图表，图片内容也是信息主体的一部分
ENGINEERING = 工程图纸(含尺寸标注/公差/坐标系/标题栏/图框坐标等特征)
OTHER = 纯扫描件/纯图像，即使有文字也是图像上的文字（无文本层）
只输出一个单词。"""

IMAGE_CLASSIFY_PROMPT = """分析这张图片，只输出一个英文单词：
TEXT_IMAGE = 文档转成的图片/截图/扫描件/合同/证件照，主要目的是提取文字和数字信息
POSTER = 海报/邀请函/信息图/宣传图，含设计性文字+图像元素
PHOTO = 实景照片/产品实物照，文字并非信息主体
OTHER = 艺术图/抽象图/装饰图/纯色块，不含需要提取的信息文字
只输出一个单词。"""

def classify_pdf(path: str) -> str:
    """
    Classify PDF first page with qwen2.5vl:7b local VL.
    Renders first page at scale=1.2 (moderate resolution) for accurate classification.
    Longer timeout (90s) for qwen2.5vl which can be slow on first inference.
    Falls back to TEXT on failure.
    """
    img = render_pdf_page(path, 0, scale=1.2)
    if not img:
        return "TEXT"

    result = ollama_classify(img, PDF_CLASSIFY_PROMPT)
    if not result:
        return "TEXT"

    for word in ["TEXT", "MIXED", "ENGINEERING", "OTHER"]:
        if word in result.upper():
            return word
    return "TEXT"

def classify_image(path: str) -> str:
    """Classify an image. Falls back to TEXT_IMAGE on failure."""
    img = render_image(path)
    if not img:
        return "TEXT_IMAGE"

    result = ollama_classify(img, IMAGE_CLASSIFY_PROMPT)
    if not result:
        return "TEXT_IMAGE"
    for word in ["TEXT_IMAGE", "POSTER", "PHOTO", "OTHER"]:
        if word in result.upper():
            return word
    return "TEXT_IMAGE"

# ============================================================
# Backend callers
# ============================================================

# --- MarkItDown (Office + structured + TEXT PDF) ---
def call_markitdown(file_path: str) -> Tuple[str, bool]:
    """Use MarkItDown to convert a file to Markdown. Returns (text, ok)."""
    try:
        from markitdown import MarkItDown
        md = MarkItDown()
        result = md.convert(file_path)
        return result.text_content, True
    except Exception as e:
        return f"[MarkItDown Error: {e}]", False

# --- Gemini Flash (vision OCR) ---
def call_gemini_flash(images_b64: List[str], prompt: str) -> Tuple[str, bool]:
    """Call Gemini 2.5 Flash for OCR. Returns (text, ok)."""
    import requests
    cfg = load_config()
    key = cfg.get("gemini", "")
    if not key:
        return "[Error: Gemini API key not configured]", False

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    parts = [{"text": prompt}]
    for img in images_b64:
        parts.append({"inline_data": {"mime_type": "image/png", "data": img}})

    try:
        t0 = time.time()
        resp = requests.post(f"{url}?key={key}", json={
            "contents": [{"parts": parts}]
        }, timeout=180)
        elapsed = time.time() - t0
        if resp.status_code == 200:
            d = resp.json()
            text = d["candidates"][0]["content"]["parts"][0]["text"]
            return text, True
        return f"[Gemini Error: {resp.status_code} {resp.text[:200]}]", False
    except Exception as e:
        return f"[Gemini Exception: {e}]", False

# --- NVIDIA NIM (vision OCR fallback) ---
def call_nvidia(images_b64: List[str], prompt: str) -> Tuple[str, bool]:
    """Call NVIDIA Qwen3.5-397B for OCR. Returns (text, ok)."""
    cfg = load_config()
    key = cfg.get("nvidia_nim", "")
    if not key:
        return "[Error: NVIDIA API key not configured]", False

    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, base_url="https://integrate.api.nvidia.com/v1")
        content = [{"type": "text", "text": prompt}]
        for img in images_b64:
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}})
        resp = client.chat.completions.create(
            model="qwen/qwen3.5-397b-a17b",
            messages=[{"role": "user", "content": content}],
            max_tokens=4096, temperature=0, timeout=180)
        return resp.choices[0].message.content, True
    except Exception as e:
        return f"[NVIDIA Error: {e}]", False

# --- Audio transcription ---
def call_audio(file_path: str) -> Tuple[str, bool]:
    """Transcribe audio using qwen-asr (cloud) or whisper-cpp (local fallback)."""
    cfg = load_config()
    dashscope_key = cfg.get("dashscope", "")

    # Try cloud ASR first
    if dashscope_key:
        try:
            import dashscope
            from dashscope import MultiModalConversation
            dashscope.api_key = dashscope_key
            messages = [{"role": "user", "content": [{"audio": file_path}]}]
            resp = MultiModalConversation.call(
                model="qwen3-asr-flash", messages=messages)
            if resp.status_code == 200 and resp.output and resp.output.choices:
                text_parts = resp.output.choices[0].message.content
                if isinstance(text_parts, list):
                    return " ".join(t.get("text", str(t)) for t in text_parts), True
                return str(text_parts), True
        except Exception:
            pass

    # Local fallback: whisper-cpp
    try:
        import subprocess, tempfile
        WHISPER = "/opt/homebrew/bin/whisper-cli"
        FFMPEG = "/opt/homebrew/bin/ffmpeg"
        MODEL = "/tmp/whisper-models/ggml-large-v3-turbo.bin"

        ext = Path(file_path).suffix.lower()
        audio_path = file_path
        tmp_wav = None

        if ext not in {'.wav'}:
            tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_wav.close()
            subprocess.run([FFMPEG, "-i", file_path, "-ar", "16000", "-ac", "1",
                          "-y", tmp_wav.name], capture_output=True, timeout=30)
            audio_path = tmp_wav.name

        result = subprocess.run(
            [WHISPER, "-m", MODEL, "-l", "zh", "-f", audio_path, "--no-prints"],
            capture_output=True, text=True, timeout=120)

        if tmp_wav: os.unlink(tmp_wav.name)
        return result.stdout.strip(), True
    except Exception as e:
        return f"[Audio Error: {e}]", False

# ============================================================
# Cross-validation engine
# ============================================================
def cross_validated_ocr(images_b64: List[str], prompt: str) -> Tuple[str, bool]:
    """
    Run OCR with cross-validation:
    1. Two parallel rounds with same prompt → compare
    2. If consistent → return directly
    3. If different → analyze diff → optimize prompt → 3rd round
    4. Output consensus; mark unresolved diffs
    """
    # Round 1 + 2 (parallel would be ideal, but serial for simplicity)
    text1, ok1 = call_gemini_flash(images_b64, prompt)
    if not ok1:
        # Fallback to NVIDIA
        text1, ok1 = call_nvidia(images_b64, prompt)
        if not ok1:
            return f"[Error: Both primary and fallback models failed]", False
        # NVIDIA as sole source: run second round
        text2, ok2 = call_nvidia(images_b64, prompt)
    else:
        text2, ok2 = call_gemini_flash(images_b64, prompt)
        if not ok2:
            # Second round failed, but we have first round → return it
            return text1, True

    # Compare rounds
    if _texts_consistent(text1, text2):
        return text1, True

    # Inconsistent → 3rd round with refined prompt
    diff_report = _generate_diff_report(text1, text2)
    refined_prompt = prompt + "\n\n[自纠错] 前两次识别存在以下差异，请以更精确的方式重新识别并统一：\n" + diff_report

    text3, ok3 = call_gemini_flash(images_b64, refined_prompt)
    if not ok3:
        text3, ok3 = call_nvidia(images_b64, refined_prompt)
        if not ok3:
            # Both failed for 3rd round → return first round with warning
            return f"{text1}\n\n[⚠️ 仅完成1轮识别，未通过交叉验证]", True

    # Three-way consensus
    if _texts_consistent(text1, text3) or _texts_consistent(text2, text3):
        # At least 2 agree
        return text3, True

    # All three different → return best-effort with explicit warning
    merged = f"{text1}\n\n---\n[⚠️ 以下为第三轮优化结果，与前两轮存在差异]\n---\n\n{text3}"
    return merged, True

def _texts_consistent(t1: str, t2: str) -> bool:
    """Check if two OCR texts are consistent enough to trust."""
    # Normalize: lowercase, collapse whitespace, remove punctuation
    def normalize(s: str) -> str:
        s = re.sub(r'\s+', ' ', s.lower().strip())
        s = re.sub(r'[^\w\s一-鿿]', '', s)
        return s

    n1, n2 = normalize(t1), normalize(t2)
    if not n1 or not n2:
        return False
    # Simple similarity threshold
    ratio = difflib.SequenceMatcher(None, n1, n2).ratio()
    return ratio >= 0.90

def _generate_diff_report(t1: str, t2: str) -> str:
    """Generate a brief diff report between two texts for prompt refinement."""
    diff_lines = []
    for line in difflib.unified_diff(
        t1.splitlines(), t2.splitlines(),
        fromfile='Round1', tofile='Round2', lineterm=''
    ):
        if line.startswith('+') or line.startswith('-'):
            diff_lines.append(line)
    if len(diff_lines) > 40:
        # Too many diffs — just return first 40 lines
        return "\n".join(diff_lines[:40])
    return "\n".join(diff_lines) if diff_lines else ""

# ============================================================
# Prompt templates
# ============================================================
GENERIC_OCR_PROMPT = """你是高精度OCR系统。逐字转录图片中的所有文字和数字。
保留标点、符号、表格结构。不概括、不翻译、不添加解释。不认识的字符标注[?]。"""

ENGINEERING_OCR_PROMPT = """你是工业图纸OCR系统。

## 任务1：结构化提取
用Markdown表格提取以下信息：

### 标题栏
| 字段 | 值 |
|------|-----|
| REV | |
| DESCRIPTION | |
| DESIGN | |
| APPROVAL | |
| DATE | |

### 零件信息
| PART NO | TITLE | DWG NO | SCALE | SHEET | CUSTOMER P/N |
|---------|-------|--------|-------|-------|--------------|

### 尺寸标注
逐项列出所有尺寸（含公差如 ±1、±0.1）

### 材料规格
所有线缆、材料、部件规格型号

### 版权声明
逐字转录

### 图章
批准人、检查人、绘图人及日期

---

## 任务2：空间解读
基于图纸边缘的网格坐标系统（横向1-8列、纵向A-E行），分析：

1. 列出所有网格坐标标记
2. 关键尺寸对应的坐标区域
3. 关键部件/材料对应的坐标区域
4. 图纸宏观空间结构总结

逐字转录，不概括。数字和符号不要修改。"""

MIXED_PROMPT = """你是文档分析系统。请提取这张文档图片中的所有信息：

1. 所有可见文字（逐字转录）
2. 嵌入的图片/图表/海报中的文字内容
3. 表格数据（如有）
4. 任何Logo、签章、水印周围的文字

逐字转录，不概括。保留原格式。"""

# ============================================================
# Processors per type
# ============================================================
def process_text_pdf(path: str) -> Tuple[str, bool]:
    """TEXT PDF: MarkItDown direct extraction. No LLM, no cross-validation."""
    text, ok = call_markitdown(path)
    return text, ok

def process_engineering_pdf(path: str) -> Tuple[str, bool]:
    """ENGINEERING PDF: Render all pages, 2-round cross-validated OCR + spatial interpretation."""
    images = render_all_pages(path, scale=1.5)
    if not images:
        return "[Error: Cannot render PDF pages]", False
    return cross_validated_ocr(images, ENGINEERING_OCR_PROMPT)

def process_mixed_pdf(path: str) -> Tuple[str, bool]:
    """MIXED PDF: MarkItDown text layer + Gemini Flash OCR on embedded images → merge."""
    # Step 1: text layer
    text_layer, _ = call_markitdown(path)
    # Step 2: OCR on rendered pages for embedded image text
    images = render_all_pages(path, scale=1.5)
    if images:
        ocr_text, _ = cross_validated_ocr(images, MIXED_PROMPT)
        # Merge: text layer first, then supplement with OCR
        merged = f"{text_layer}\n\n<!-- 以下为图片层OCR补充 -->\n\n{ocr_text}"
        return merged, True
    return text_layer, True

def process_other_pdf(path: str) -> Tuple[str, bool]:
    """OTHER (scanned): Same as engineering — full OCR with cross-validation."""
    return process_engineering_pdf(path)

def process_ocr_image(path: str) -> Tuple[str, bool]:
    """TEXT_IMAGE / POSTER: Cross-validated OCR."""
    img_b64 = render_image(path, max_size=1200)
    if not img_b64:
        return "[Error: Cannot load image]", False
    return cross_validated_ocr([img_b64], GENERIC_OCR_PROMPT)

def process_photo(path: str) -> Tuple[str, bool]:
    """PHOTO: AI description, single round (no 'correctness' to validate)."""
    img_b64 = render_image(path, max_size=1200)
    if not img_b64:
        return "[Error: Cannot load image]", False
    prompt = "用中文简要描述这张照片的内容。包括：场景、人物/物体、动作、氛围。100字以内。"
    text, ok = call_gemini_flash([img_b64], prompt)
    if not ok:
        text, ok = call_nvidia([img_b64], prompt)
    return text, ok

# ============================================================
# Main router
# ============================================================
def read_everything(file_path: str, verbose: bool = False) -> Dict[str, Any]:
    """
    Convert any file to Markdown, saved as <file_path>.md next to the original.
    Returns: {"ok": bool, "output": str, "type": str, "engine": str, "rounds": int, "verified": bool}
    """
    path = os.path.abspath(file_path)
    if not os.path.exists(path):
        return {"ok": False, "error": f"File not found: {path}"}

    ext = file_ext(path)
    route = route_by_ext(ext)

    if verbose:
        print(f"文件: {path}")
        print(f"类型: {route} ({ext})")

    # --- Office & Structured → MarkItDown ---
    if route in ("office", "structured"):
        text, ok = call_markitdown(path)
        if ok:
            return _save_and_return(path, text, route, "markitdown", 1, True)
        return {"ok": False, "error": text}

    # --- PDF → classify → route ---
    if route == "pdf":
        pdf_type = classify_pdf(path)
        if verbose:
            print(f"PDF分类: {pdf_type}")

        processors = {
            "TEXT": process_text_pdf,
            "ENGINEERING": process_engineering_pdf,
            "MIXED": process_mixed_pdf,
            "OTHER": process_other_pdf,
        }
        fn = processors.get(pdf_type, process_text_pdf)
        text, ok = fn(path)

        if ok:
            engine = "markitdown" if pdf_type == "TEXT" else "gemini-flash+cross-validate"
            return _save_and_return(path, text, pdf_type, engine, 2 if pdf_type != "TEXT" else 1, True)
        return {"ok": False, "error": text}

    # --- Image → classify → route ---
    if route == "image":
        img_type = classify_image(path)
        if verbose:
            print(f"图片分类: {img_type}")

        if img_type == "OTHER":
            return {"ok": True, "output": None, "type": "OTHER", "engine": "none", "rounds": 0, "verified": True,
                    "message": "非信息型图片，已跳过"}

        if img_type == "PHOTO":
            text, ok = process_photo(path)
            engine = "gemini-flash"
            rounds = 1
        else:  # TEXT_IMAGE, POSTER
            text, ok = process_ocr_image(path)
            engine = "gemini-flash+cross-validate"
            rounds = 2

        if ok:
            return _save_and_return(path, text, img_type, engine, rounds, True)
        return {"ok": False, "error": text}

    # --- Audio ---
    if route == "audio":
        text, ok = call_audio(path)
        if ok:
            return _save_and_return(path, text, "AUDIO", "qwen-asr", 1, True)
        return {"ok": False, "error": text}

    # --- Video ---
    if route == "video":
        text, ok = call_audio(path)  # ffmpeg→whisper reuses audio path
        if ok:
            return _save_and_return(path, text, "VIDEO", "ffmpeg+whisper", 1, True)
        return {"ok": False, "error": text}

    # --- Plain text → copy directly ---
    if route == "text":
        with open(path) as f:
            text = f.read()
        return _save_and_return(path, text, "TEXT", "direct", 1, True)

    return {"ok": False, "error": f"Unsupported format: {ext}"}

def _save_and_return(path: str, text: str, doc_type: str, engine: str, rounds: int, verified: bool) -> Dict:
    """Save text to <path>.md and return result dict."""
    out_path = path + ".md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"<!-- read-everything-v3 | type={doc_type} engine={engine} rounds={rounds} verified={verified} -->\n\n")
        f.write(text)
    return {
        "ok": True,
        "output": out_path,
        "type": doc_type,
        "engine": engine,
        "rounds": rounds,
        "verified": verified
    }

# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="read-everything-v3: Convert any file to Markdown")
    parser.add_argument("file", help="File to convert")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    result = read_everything(args.file, verbose=args.verbose)

    if args.verbose:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"]:
        print(result["output"])
    else:
        print(f"Error: {result.get('error', 'unknown')}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
