"""生成 assets/demo.gif：960×600 的终端风演示动图。

只用 Pillow（开发期依赖，不进 requirements）。跑法：
    python scripts/make_demo_gif.py

画面里的分数是真实跑出来的：坑版 8 分、改后版 100 分。
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

W, H = 960, 600
BG = "#0b0f14"
BAR = "#161b22"
LINE = "#21262d"
GREEN = "#7ee787"
TEXT = "#c9d1d9"
DIM = "#8b949e"
BLUE = "#79c0ff"
YELLOW = "#e3b341"
RED = "#ff7b72"

FONT_PATH = r"C:\Windows\Fonts\msyh.ttc"

LINE_H = 25
MAX_W = W - 56

COLORS = {"cmd": GREEN, "out": TEXT, "dim": DIM, "cite": BLUE, "warn": YELLOW, "bad": RED}


def font(size: int):
    return ImageFont.truetype(FONT_PATH, size)


_MEASURE = ImageDraw.Draw(Image.new("RGB", (1, 1)))


def clip(text: str, size: int = 16) -> str:
    f = font(size)
    if _MEASURE.textlength(text, font=f) <= MAX_W:
        return text
    while text and _MEASURE.textlength(text + "…", font=f) > MAX_W:
        text = text[:-1]
    return text + "…"


def render(rows, cursor_row=None):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 36], fill=BAR)
    for i, color in enumerate(["#ff5f56", "#ffbd2e", "#27c93f"]):
        d.ellipse([16 + i * 22, 12, 28 + i * 22, 24], fill=color)
    d.text((92, 9), "shenqi — 合同条款体检", font=font(15), fill=DIM)
    d.line([0, 36, W, 36], fill=LINE)

    y = 54
    for idx, (style, text) in enumerate(rows):
        shown = clip(text)
        d.text((26, y), shown, font=font(16), fill=COLORS[style])
        if cursor_row == idx:
            w = _MEASURE.textlength(shown, font=font(16))
            d.rectangle([26 + w + 4, y + 2, 26 + w + 12, y + 19], fill=GREEN)
        y += LINE_H
        if y > H - 16:
            break
    return img


SCRIPT = [
    ("cmd", "> python -m shenqi add samples/云盘服务合同-坑版.txt"),
    ("out", "· 合同 [1] 云盘服务合同-坑版 —— 449 字，切出 8 条"),
    ("dim", ""),
    ("cmd", "> python -m shenqi review 1 --rules-only"),
    ("bad", "=== 合同 [1] 云盘服务合同-坑版 · 8 分 · 别签，先改 ==="),
    ("out", "高 5 · 中 2 · 低 2 · 缺 3 项必备条款（规则 9 条 / 模型 0 条）"),
    ("dim", "缺的必备条款：争议解决、解除或终止、知识产权归属"),
    ("bad", "[高] 1. 自动续约没写退出方式（第三条）"),
    ("dim", "     原文：合同期满后自动续期一年，除非一方提出异议。"),
    ("bad", "[高] 2. 允许单方变更条款（第四条）"),
    ("dim", "     原文：乙方有权…单方面调整服务内容、存储规格及价格，无需另行通知甲方。"),
    ("bad", "[高] 3. 赔偿责任无上限（第五条）"),
    ("bad", "[高] 4. 违约金比例 30% 偏高（第六条）"),
    ("bad", "[高] 5. 全文没有解除或终止条款（—）"),
    ("dim", ""),
    ("cmd", "> python -m shenqi review 2 --rules-only"),
    ("out", "=== 合同 [2] 云盘服务合同-改后版 · 100 分 · 风险不大 ==="),
    ("out", "高 0 · 中 0 · 低 0 · 缺 0 项必备条款（规则 0 条 / 模型 0 条）"),
]
TAIL = [
    ("warn", "只跑规则：8 分 → 100 分，每条风险都挂着原文。"),
    ("dim", "加模型再看：改后版 56 分——模型又挑出 6 条语义风险，那是规则看不见的。"),
]


def build():
    frames, shown = [], []
    for style, text in SCRIPT:
        if style == "cmd":
            for i in range(6, len(text) + 1, 6):
                frames.append(render(shown + [("cmd", text[:i])], cursor_row=len(shown)))
        shown = shown + [(style, text)]
        frames.append(render(shown))
    for _ in range(12):
        frames.append(render(shown + TAIL))

    frames = [f.quantize(colors=20, method=Image.MEDIANCUT) for f in frames]
    os.makedirs("assets", exist_ok=True)
    out = os.path.join("assets", "demo.gif")
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=140, loop=0, optimize=True)
    print(f"ok -> {out}  {len(frames)} 帧  {os.path.getsize(out) / 1024:.1f} KB")


if __name__ == "__main__":
    build()
