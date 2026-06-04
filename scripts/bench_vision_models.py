#!/usr/bin/env python3
"""
视觉模型横向对比测试 — 能力 + 延迟 + 稳定性
从 ~/.read_everything_config.json 读取所有 API key
"""
import json, time, base64, sys
from pathlib import Path
from io import BytesIO

CONFIG = json.load(open(Path.home() / ".read_everything_config.json"))

TEST_BASE = "/Users/eric-mingle-69/Documents/trae/item_fille/read-everything-skill"
OUT_DIR = Path("/Users/eric-mingle-69/.claude/skills/read-everything-v3/scripts/bench_output")
OUT_DIR.mkdir(parents=True, exist_ok=True)

TEST_FILES = {
    "engineering_pdf": f"{TEST_BASE}/测试PDF.pdf",
    "poster_image": f"{TEST_BASE}/测试图片.jpeg",
}

OCR_PROMPT = """你是一个高精度工业OCR引擎。请将图片中的每一个字、数字、符号、尺寸标注原封不动地转录出来。
保留所有标点、数字、邮箱、URL、电话号码、坐标、公差标注（如 ±1、±0.1）。
不要概括、翻译或添加解释。
对于工程图纸，特别关注：图号、版本号、设计人、审批人、日期、材料规格、尺寸标注、公差范围。"""

# --- PDF rendering helper ---
def render_pdf_pages(pdf_path, dpi=200):
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(pdf_path)
    images = []
    for i in range(min(len(pdf), 2)):
        page = pdf[i]
        bitmap = page.render(scale=dpi / 72)
        img = bitmap.to_pil().convert("RGB")
        buf = BytesIO()
        img.save(buf, format="PNG")
        images.append(base64.b64encode(buf.getvalue()).decode())
    return images

def load_image_b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

# --- Backend: Google Gemini 2.5 Pro ---
def call_gemini(file_path, file_type):
    import requests
    key = CONFIG["gemini"]
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent"
    images = render_pdf_pages(file_path) if file_type == "pdf" else [load_image_b64(file_path)]
    parts = [{"text": OCR_PROMPT}]
    for img in images:
        parts.append({"inline_data": {"mime_type": "image/png", "data": img}})
    t0 = time.time()
    resp = requests.post(f"{url}?key={key}", json={"contents": [{"parts": parts}]}, timeout=120)
    elapsed = time.time() - t0
    if resp.status_code == 200:
        d = resp.json()
        return {"text": d["candidates"][0]["content"]["parts"][0]["text"], "elapsed": elapsed, "status": "ok"}
    return {"text": "", "elapsed": elapsed, "status": "error", "error": resp.text[:300]}

# --- Backend: OpenRouter Qwen3-VL-235B ---
def call_openrouter(file_path, file_type):
    from openai import OpenAI
    client = OpenAI(api_key=CONFIG["openrouter"], base_url="https://openrouter.ai/api/v1")
    images = render_pdf_pages(file_path) if file_type == "pdf" else [load_image_b64(file_path)]
    content = [{"type": "text", "text": OCR_PROMPT}]
    for img in images:
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}})
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model="qwen/qwen3-vl-235b-a22b-thinking:free",
            messages=[{"role": "user", "content": content}],
            max_tokens=4096, temperature=0, timeout=120)
        elapsed = time.time() - t0
        return {"text": resp.choices[0].message.content, "elapsed": elapsed, "status": "ok",
                "tokens": {"in": resp.usage.prompt_tokens, "out": resp.usage.completion_tokens} if resp.usage else {}}
    except Exception as e:
        return {"text": "", "elapsed": time.time() - t0, "status": "error", "error": str(e)[:300]}

# --- Backend: NVIDIA NIM Qwen3.5-397B ---
def call_nvidia(file_path, file_type):
    from openai import OpenAI
    client = OpenAI(api_key=CONFIG["nvidia_nim"], base_url="https://integrate.api.nvidia.com/v1")
    images = render_pdf_pages(file_path) if file_type == "pdf" else [load_image_b64(file_path)]
    content = [{"type": "text", "text": OCR_PROMPT}]
    for img in images:
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}})
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model="qwen/qwen3.5-397b-a17b",
            messages=[{"role": "user", "content": content}],
            max_tokens=4096, temperature=0, timeout=120)
        elapsed = time.time() - t0
        return {"text": resp.choices[0].message.content, "elapsed": elapsed, "status": "ok",
                "tokens": {"in": resp.usage.prompt_tokens, "out": resp.usage.completion_tokens} if resp.usage else {}}
    except Exception as e:
        return {"text": "", "elapsed": time.time() - t0, "status": "error", "error": str(e)[:300]}

# --- Backend: DashScope qwen-vl-plus ---
def call_dashscope(file_path, file_type):
    from dashscope import MultiModalConversation
    import dashscope
    dashscope.api_key = CONFIG["dashscope"]
    images_b64 = render_pdf_pages(file_path) if file_type == "pdf" else [load_image_b64(file_path)]
    messages = [{"role": "system", "content": [{"text": OCR_PROMPT}]}]
    content = []
    for img in images_b64:
        content.append({"image": f"data:image/png;base64,{img}"})
    content.append({"text": f"精确转录全部 {len(images_b64)} 张图片的所有文字："})
    messages.append({"role": "user", "content": content})
    t0 = time.time()
    try:
        resp = MultiModalConversation.call(model="qwen-vl-plus", messages=messages, max_tokens=4096)
        elapsed = time.time() - t0
        text = resp.output.choices[0].message.content[0]["text"] if resp.output else ""
        return {"text": text, "elapsed": elapsed, "status": "ok",
                "tokens": {"in": resp.usage.input_tokens, "out": resp.usage.output_tokens} if resp.usage else {}}
    except Exception as e:
        return {"text": "", "elapsed": time.time() - t0, "status": "error", "error": str(e)[:300]}

# ============================================================
PLATFORMS = [
    ("Gemini-2.5-Pro",       call_gemini),
    ("OpenRouter-Qwen3VL235B", call_openrouter),
    ("NVIDIA-Qwen3.5-397B",  call_nvidia),
    ("DashScope-qwen-vl-plus", call_dashscope),
]

results = {}
for file_key, file_path in TEST_FILES.items():
    file_type = "pdf" if file_key == "engineering_pdf" else "image"
    print(f"\n{'='*60}\n测试文件: {file_key}\n{'='*60}")
    results[file_key] = {}
    for name, fn in PLATFORMS:
        print(f"[{name}] 调用中...", end=" ", flush=True)
        r = fn(file_path, file_type)
        s = "✅" if r["status"] == "ok" else "❌"
        print(f"{s} {r['elapsed']:.1f}s, {len(r['text'])} chars")
        if r["status"] == "error":
            print(f"  ERROR: {r['error'][:200]}")
        results[file_key][name] = r
        out_path = OUT_DIR / f"{file_key}_{name}.md"
        out_path.write_text(f"# {name} → {file_key}\n延迟: {r['elapsed']:.2f}s\n状态: {r['status']}\n\n## Output\n{r['text']}")

# Summary
print(f"\n{'='*60}\n汇总\n{'='*60}")
for fk in TEST_FILES:
    print(f"\n--- {fk} ---")
    for name, _ in PLATFORMS:
        r = results[fk][name]
        s = "✅" if r["status"] == "ok" else "❌"
        print(f"  {s} {name}: {r['elapsed']:.1f}s, {len(r['text'])} chars")

with open(OUT_DIR / "bench_results.json", "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=2, default=str)
print(f"\nDone → {OUT_DIR}")
