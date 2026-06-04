#!/usr/bin/env python3
"""Final vision benchmark: 3 working platforms × 2 test files. Reads all keys from config."""
import json, time, base64
from pathlib import Path
from io import BytesIO
import requests
import pypdfium2 as pdfium
from openai import OpenAI

CONFIG = json.load(open(Path.home() / ".read_everything_config.json"))
OUT_DIR = Path("/Users/eric-mingle-69/.claude/skills/read-everything-v3/scripts/bench_output")
OUT_DIR.mkdir(parents=True, exist_ok=True)

OCR_PROMPT = """你是一个高精度工业OCR引擎。请将图片中的每一个字、数字、符号、尺寸标注原封不动地转录出来。保留所有标点、数字、邮箱、URL、电话号码、坐标、公差标注。不要概括、翻译或添加解释。"""

TEST_FILES = {
    "engineering_pdf": "/Users/eric-mingle-69/Documents/trae/item_fille/read-everything-skill/测试PDF.pdf",
    "poster_image": "/Users/eric-mingle-69/Documents/trae/item_fille/read-everything-skill/测试图片.jpeg",
}

def render_pdf(path, dpi=200):
    pdf = pdfium.PdfDocument(path)
    imgs = []
    for i in range(min(len(pdf), 2)):
        bmp = pdf[i].render(scale=dpi/72)
        buf = BytesIO()
        bmp.to_pil().convert("RGB").save(buf, format="PNG")
        imgs.append(base64.b64encode(buf.getvalue()).decode())
    return imgs

def load_b64(path):
    with open(path, "rb") as f:
        return [base64.b64encode(f.read()).decode()]

# --- Gemini 2.5 Flash ---
def call_gemini(fp, is_pdf):
    imgs = render_pdf(fp) if is_pdf else load_b64(fp)
    parts = [{"text": OCR_PROMPT}]
    for img in imgs:
        parts.append({"inline_data": {"mime_type": "image/png", "data": img}})
    t0 = time.time()
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={CONFIG['gemini']}",
        json={"contents": [{"parts": parts}]}, timeout=180)
    el = time.time() - t0
    if r.status_code == 200:
        d = r.json()
        return {"ok": True, "text": d["candidates"][0]["content"]["parts"][0]["text"], "elapsed": el}
    return {"ok": False, "text": "", "elapsed": el, "error": r.text[:300]}

# --- NVIDIA NIM Qwen3.5-397B ---
def call_nvidia(fp, is_pdf):
    cl = OpenAI(api_key=CONFIG["nvidia_nim"], base_url="https://integrate.api.nvidia.com/v1")
    imgs = render_pdf(fp) if is_pdf else load_b64(fp)
    ct = [{"type": "text", "text": OCR_PROMPT}]
    for img in imgs:
        ct.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}})
    t0 = time.time()
    try:
        r = cl.chat.completions.create(
            model="qwen/qwen3.5-397b-a17b",
            messages=[{"role": "user", "content": ct}],
            max_tokens=4096, temperature=0, timeout=180)
        return {"ok": True, "text": r.choices[0].message.content, "elapsed": time.time() - t0}
    except Exception as e:
        return {"ok": False, "text": "", "elapsed": time.time() - t0, "error": str(e)[:300]}

# --- DashScope qwen-vl-plus ---
def call_dashscope(fp, is_pdf):
    from dashscope import MultiModalConversation
    import dashscope
    dashscope.api_key = CONFIG["dashscope"]
    imgs = render_pdf(fp) if is_pdf else load_b64(fp)
    msgs = [{"role": "system", "content": [{"text": OCR_PROMPT}]}]
    ct = [{"image": f"data:image/png;base64,{i}"} for i in imgs]
    ct.append({"text": f"精确转录全部 {len(imgs)} 张图片的文字："})
    msgs.append({"role": "user", "content": ct})
    t0 = time.time()
    try:
        r = MultiModalConversation.call(model="qwen-vl-plus", messages=msgs, max_tokens=4096)
        txt = r.output.choices[0].message.content[0]["text"] if r.output else ""
        return {"ok": True, "text": txt, "elapsed": time.time() - t0}
    except Exception as e:
        return {"ok": False, "text": "", "elapsed": time.time() - t0, "error": str(e)[:300]}

# ============================================================
PLATFORMS = [
    ("Gemini-2.5-Flash", call_gemini),
    ("NVIDIA-Qwen3.5", call_nvidia),
    ("DashScope-qwen-vl-plus", call_dashscope),
]

results = {}
for fk, fp in TEST_FILES.items():
    is_pdf = fk == "engineering_pdf"
    print(f"\n{'='*60}\n{fk} (pdf={is_pdf})\n{'='*60}")
    results[fk] = {}
    for name, fn in PLATFORMS:
        print(f"[{name}] calling...", end=" ", flush=True)
        r = fn(fp, is_pdf)
        s = "✅" if r["ok"] else "❌"
        print(f"{s} {r['elapsed']:.1f}s, {len(r['text'])} chars")
        if r.get("error"):
            print(f"  ERROR: {r['error'][:200]}")
        results[fk][name] = r
        out_path = OUT_DIR / f"final_{fk}_{name}.md"
        out_path.write_text(f"# {name} → {fk}\n延迟: {r['elapsed']:.1f}s\n状态: {'ok' if r['ok'] else 'error'}\n\n{r['text']}")

print(f"\n{'='*60}\nFINAL SUMMARY\n{'='*60}")
for fk in TEST_FILES:
    print(f"\n{fk}:")
    for name, _ in PLATFORMS:
        r = results[fk][name]
        ok = "✅" if r["ok"] else "❌"
        print(f"  {ok} {name:25s} | {r['elapsed']:5.1f}s | {len(r['text']):4d} chars")

with open(OUT_DIR / "bench_final.json", "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=2, default=str)
print(f"\nSaved → {OUT_DIR}")
