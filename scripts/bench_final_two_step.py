#!/usr/bin/env python3
"""
最终提示词优化测试 — 两步输出：
Step 1: 结构化提取（表格）
Step 2: 空间解读（坐标→尺寸/区域对应关系）

验证三个问题：
1. 提示词能否让模型理解图框坐标与尺寸之间的空间对应关系？
2. DashScope 的 26AWG→25AWG 错误是否可纠正？（如果是模型精度问题则不可纠正）
3. 最终确认首选/备选/兜底三层策略的合理性
"""
import json, time, base64
from pathlib import Path
from io import BytesIO
import requests, pypdfium2 as pdfium
from openai import OpenAI

CONFIG = json.load(open(Path.home() / ".read_everything_config.json"))
OUT_DIR = Path("/Users/eric-mingle-69/.claude/skills/read-everything-v3/scripts/bench_output")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# 最终优化提示词 —— 两步输出
# ============================================================
FINAL_PROMPT = """你是一个工业图纸分析系统。请对这张工程图纸完成两项任务：

## 任务 1：结构化提取
用 Markdown 表格逐项列出图纸上的所有信息，不遗漏不概括：

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

### 尺寸标注（逐个列出）
所有带公差的尺寸、不带公差的尺寸、参考尺寸。

### 材料与规格
所有线缆、材料、部件规格型号。

### 版权声明
逐字转录。

### 图章
批准人、检查人、绘图人及日期。

---

## 任务 2：空间解读
基于图纸的网格坐标系统（通常标注在图框边缘，如 1-8 列号、A-E 行号），
分析图纸的空间布局：

1. 列出所有网格坐标标记（如 A1, B3, C5 等）及其实际标注的文字
2. 说明关键尺寸所在的坐标区域（例如：「27.2±1 位于 D3 区域，对应水泵导线接口位置」）
3. 说明关键部件/材料规格所在的坐标区域
4. 总结图纸的空间结构：标题栏在哪个区域、主视图在哪个区域、尺寸标注分散在哪些区域

请确保：
- 任务 1 逐字转录，不修改任何数字和符号
- 任务 2 基于实际识别到的坐标标记进行推理，不要凭空编造坐标
- 两项任务之间用「---」分隔"""

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
    ct.append({"text": "请完成上述两步任务："})
    msgs.append({"role": "user", "content": ct})
    t0 = time.time()
    try:
        r = MultiModalConversation.call(model="qwen-vl-plus", messages=msgs, max_tokens=4096)
        txt = r.output.choices[0].message.content[0]["text"] if r.output else ""
        return {"ok": True, "text": txt, "elapsed": time.time() - t0}
    except Exception as e:
        return {"ok": False, "text": "", "elapsed": time.time() - t0, "error": str(e)[:300]}

# ============================================================
# 跑 3 平台
# ============================================================
print("Final optimized prompt benchmark — 两步输出\n")
results = {}
for name, fn in [("Gemini-Flash", call_gemini), ("NVIDIA-Qwen3.5", call_nvidia), ("DashScope-vl-plus", call_dashscope)]:
    print(f"[{name}] 调用中...", end=" ", flush=True)
    r = fn(TEST_FILE, FINAL_PROMPT)
    s = "✅" if r["ok"] else "❌"
    print(f"{s} {r['elapsed']:.1f}s, {len(r['text'])} chars")
    if r.get("error"):
        print(f"  ERROR: {r['error'][:300]}")
    results[name] = r
    out = OUT_DIR / f"final_two_step_{name}.md"
    out.write_text(f"# {name} — 两步输出\n延迟: {r['elapsed']:.1f}s\n\n{r['text']}")

# 质量快检：检查每个模型的错误标记
print(f"\n{'='*60}")
print("质量快检 — 关键字段对比")
print(f"{'='*60}")

checks = {
    "风扇导线 26AWG (正确)": "26AWG",
    "风扇导线 25AWG (错误)": "25AWG",
    "27.2±1": "27.2±1",
    "坐标对应关系": "A1",  # 看有没有做空间对应
    "空间解读段": "空间解读",
}

for cname, keyword in checks.items():
    row = [f"  {cname:35s}"]
    for pname in results:
        if keyword in results[pname].get("text",""):
            row.append(f"✅")
        else:
            row.append(f"❌")
    print(" | ".join(row))

print(f"\n输出目录: {OUT_DIR}")
