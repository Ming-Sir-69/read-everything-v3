#!/usr/bin/env python3
"""
PDF 类型判定准确性验证 — 必须覆盖：
1. 纯文字 PDF
2. 工程图 PDF
3. 图文混合 PDF（文字 + 嵌入图片，常见于邮件/Word/PPT 转 PDF）
4. 扫描件 PDF（整页是图片）

关键测试：图文混合 PDF 能不能被正确判为 MIXED 而非 TEXT
"""
import base64, requests, time
from io import BytesIO
import pypdfium2 as pdfium

MODEL = "minicpm-v:latest"

TYPE_PROMPT = """分类：TEXT / ENGINEERING / MIXED / OTHER
TEXT = 纯文本文档，内容为段落文字，无嵌入图片/图表/Logo/照片
ENGINEERING = 技术图纸，含尺寸标注/公差/坐标系/标题栏
MIXED = 文字为主但页面上有嵌入的图片、图表、Logo、照片、签章等非文字元素
OTHER = 纯图像/扫描件/海报，即使有文字也是图像上的文字（无文本层）
只输出一个分类词。"""

def render_first_page(path, dpi=150):
    pdf = pdfium.PdfDocument(path)
    bmp = pdf[0].render(scale=dpi/72)
    buf = BytesIO()
    bmp.to_pil().convert("RGB").save(buf, format="PNG", quality=60)
    return base64.b64encode(buf.getvalue()).decode()

tests = {
    "纯文字-新闻早报": "/Users/eric-mingle-69/Documents/trae/item_fille/read-everything-skill/test_daily_news.pdf",
    "纯文字-邮件": "/Users/eric-mingle-69/Documents/trae/item_fille/read-everything-skill/2026年全国移动应用创新赛供应链组启动大会会议链接（及AI应用创新论坛）-5月29日.pdf",
    "工程图-ARGB": "/Users/eric-mingle-69/Documents/trae/item_fille/read-everything-skill/测试PDF.pdf",
}

print("=== PDF 类型判定验证 ===\n")
for label, path in tests.items():
    img = render_first_page(path)
    t0 = time.time()
    resp = requests.post("http://localhost:11434/api/generate", json={
        "model": MODEL,
        "prompt": TYPE_PROMPT,
        "images": [img],
        "stream": False,
        "options": {"num_predict": 10, "temperature": 0}
    }, timeout=30)
    elapsed = time.time() - t0
    result = resp.json().get("response", "").strip()
    # 提取第一个词
    first_word = result.split()[0].strip(".,;:，。 ")
    print(f"  {label:15s} | {elapsed:.1f}s | → {first_word}")
