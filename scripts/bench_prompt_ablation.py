#!/usr/bin/env python3
"""
提示词优化对比测试 — 验证 4 个问题:
1. NVIDIA 图框坐标噪音：是提示词导致的遗漏还是模型问题？
2. DashScope 26AWG→25AWG、27.2±1 遗漏：能否通过提示词纠正？
3. 输出结构：能否通过提示词让三者都输出结构化 Markdown？
4. 完整性：优化提示词后谁恢复的字段最多？

5 维度中提示词可能影响: 完整性、准确性、输出结构（3 维）
免费额度、稳定性（2 维）不受提示词影响
"""
import json, time, base64
from pathlib import Path
from io import BytesIO
import requests
import pypdfium2 as pdfium
from openai import OpenAI

CONFIG = json.load(open(Path.home() / ".read_everything_config.json"))
OUT_DIR = Path("/Users/eric-mingle-69/.claude/skills/read-everything-v3/scripts/bench_output")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# 三版提示词：A=原版(对照) B=精确OCR版 C=结构输出版
# ============================================================
PROMPT_A = """你是一个高精度工业OCR引擎。请将图片中的每一个字、数字、符号、尺寸标注原封不动地转录出来。保留所有标点、数字、邮箱、URL、电话号码、坐标、公差标注。不要概括、翻译或添加解释。"""

PROMPT_B = """你是一个工业图纸OCR系统。请按以下规则处理：

1. **列全所有文本**：图片上出现的每一个文字、数字、符号、标记都必须转录。包括但不限于：
   - 标题栏（REV、DESCRIPTION、DESIGN、APPROVAL、DATE）
   - 零件号（PART NO）、图号（DWG NO）
   - 所有尺寸标注（含公差如 ±1、±0.1）
   - 材料规格和线缆型号
   - 图框坐标（ABCDE/123456 列号行号）
   - 版权声明
   - 比例尺（SCALE）、图纸张数（SHEET）

2. **坐标栏单独列出**：如果图框边缘有 ABCDE 或 12345678 等坐标标记，以「图框坐标：」为标题单独列出，说明每个坐标对应的行/列位置。

3. **逐字转录，不概括**：不要总结、不要省略、不要改写。看到什么写什么。

4. **保留原文格式**：数字和单位之间保留空格或连接。公差标注保留 ± 符号，不要替换为 +/-。

输出格式：纯文本，每行一个字段。"""

PROMPT_C = """你是一个工业图纸OCR系统。请输出以下结构：

## 标题栏
用 Markdown 表格列出 REV | DESCRIPTION | DESIGN | APPROVAL | DATE

## 零件信息
用 Markdown 表格列出 PART NO | TITLE | CUSTOMER P/N

## 尺寸标注
逐行列出的所有尺寸数据（含公差）

## 材料规格
列出的所有材料/线缆/部件规格

## 图框坐标
如果图框边缘存在坐标标记（ABCDE 列号 / 123456 行号），列出其实际位置和含义。

## 版权与声明
逐字转录的版权和法律声明文本

## 图章与签名
批准/检查/绘图人员的姓名、签名日期

输出要求：Markdown 格式，每部分用 ## 标题分隔。所有字段逐字转录，不省略不概括。"""

TEST_FILE = "/Users/eric-mingle-69/Documents/trae/item_fille/read-everything-skill/测试PDF.pdf"

def render_pdf(path, dpi=200):
    pdf = pdfium.PdfDocument(path)
    imgs = []
    for i in range(len(pdf)):
        bmp = pdf[i].render(scale=dpi/72)
        buf = BytesIO()
        bmp.to_pil().convert("RGB").save(buf, format="PNG")
        imgs.append(base64.b64encode(buf.getvalue()).decode())
    return imgs

def call_gemini(fp, prompt):
    imgs = render_pdf(fp)
    parts = [{"text": prompt}]
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

def call_nvidia(fp, prompt):
    cl = OpenAI(api_key=CONFIG["nvidia_nim"], base_url="https://integrate.api.nvidia.com/v1")
    imgs = render_pdf(fp)
    ct = [{"type": "text", "text": prompt}]
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

def call_dashscope(fp, prompt):
    from dashscope import MultiModalConversation
    import dashscope
    dashscope.api_key = CONFIG["dashscope"]
    imgs = render_pdf(fp)
    msgs = [{"role": "system", "content": [{"text": prompt}]}]
    ct = [{"image": f"data:image/png;base64,{i}"} for i in imgs]
    ct.append({"text": "请按上述格式输出："})
    msgs.append({"role": "user", "content": ct})
    t0 = time.time()
    try:
        r = MultiModalConversation.call(model="qwen-vl-plus", messages=msgs, max_tokens=4096)
        txt = r.output.choices[0].message.content[0]["text"] if r.output else ""
        return {"ok": True, "text": txt, "elapsed": time.time() - t0}
    except Exception as e:
        return {"ok": False, "text": "", "elapsed": time.time() - t0, "error": str(e)[:300]}

# ============================================================
# 跑：3 平台 × 3 提示词 = 9 次调用
# ============================================================
PLATFORMS = [
    ("Gemini-Flash", call_gemini),
    ("NVIDIA-Qwen3.5", call_nvidia),
    ("DashScope-vl-plus", call_dashscope),
]
PROMPTS = [
    ("A-baseline", PROMPT_A),
    ("B-full", PROMPT_B),
    ("C-structured", PROMPT_C),
]

results = {}
for pkey, prompt in PROMPTS:
    print(f"\n{'#'*60}\n提示词: {pkey}\n{'#'*60}")
    results[pkey] = {}
    for pname, pfn in PLATFORMS:
        print(f"  [{pname}] ...", end=" ", flush=True)
        r = pfn(TEST_FILE, prompt)
        s = "✅" if r["ok"] else "❌"
        print(f"{s} {r['elapsed']:.1f}s, {len(r['text'])} chars")
        if r.get("error"):
            print(f"       {r['error'][:200]}")
        results[pkey][pname] = r
        out = OUT_DIR / f"prompt_{pkey}_{pname}.md"
        out.write_text(f"# {pname} × {pkey}\n延迟: {r['elapsed']:.1f}s\n\n{r['text']}")

# 汇总表
print(f"\n{'='*60}\nPROMPT ABLATION SUMMARY\n{'='*60}")
print(f"{'Platform':25s} | {'A-baseline':>10s} | {'B-full':>10s} | {'C-structured':>10s}")
print("-" * 65)
for pname, _ in PLATFORMS:
    chars = []
    for pkey, _ in PROMPTS:
        c = len(results[pkey][pname].get("text", ""))
        chars.append(c)
    print(f"{pname:25s} | {chars[0]:5d} chars | {chars[1]:5d} chars | {chars[2]:5d} chars")

# 输出所有 B 版和 C 版文件路径
with open(OUT_DIR / "prompt_ablation.json", "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=2, default=str)
print(f"\n全部输出: {OUT_DIR}")
