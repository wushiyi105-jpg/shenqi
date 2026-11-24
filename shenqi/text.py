"""条款切分与要素抽取。

合同不是散文，它有编号、有金额、有期限。后面所有判断都建立在这三件事上：
先把一条一条切开，再把钱、日期、比例、天数抽出来，规则和模型才有东西可看。
"""

from __future__ import annotations

import re

_NUM = "一二三四五六七八九十百零两"

# 合同里常见的四种编号：第X条 / 一、 / 1. / （一）
_CLAUSE_RE = re.compile(
    rf"(?m)^[ \t]*(?:第[{_NUM}]+条|[{_NUM}]+、|\d+(?:\.\d+)*[.、][ \t]|（[{_NUM}]+）)"
)

_AMOUNT_RE = re.compile(r"(?:人民币|RMB|¥|￥)?\s*([0-9][0-9,，]*(?:\.\d+)?)\s*(万元|万|元|块)")
_DATE_RE = re.compile(r"(20\d{2})\s*[年\-/.]\s*(\d{1,2})\s*[月\-/.]\s*(\d{1,2})\s*日?")
_PERCENT_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*%")
_DAY_RE = re.compile(rf"([0-9]+|[{_NUM}]+)\s*个?\s*(工作日|自然日|日历日|日|天)")

_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9}


def cn_to_int(text: str) -> int | None:
    """把「三十」「十五」「一百二十」这类小数字转成 int。够用就行，不做完整解析。"""
    if not text:
        return None
    if text.isdigit():
        return int(text)
    total, section = 0, 0
    for ch in text:
        if ch in _CN_DIGITS:
            section = _CN_DIGITS[ch]
        elif ch == "十":
            section = (section or 1) * 10
            total += section
            section = 0
        elif ch == "百":
            section = (section or 1) * 100
            total += section
            section = 0
        else:
            return None
    return total + section if total or section else None


def normalize(text: str) -> str:
    """统一换行、去零宽字符、把全角空格压成半角。不动正文用字。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u3000", " ").replace("\ufeff", "").replace("\u200b", "")
    return text


def split_clauses(text: str) -> list[dict]:
    """按编号切条款。切不出来就整篇当一条，绝不丢内容。"""
    text = normalize(text)
    marks = list(_CLAUSE_RE.finditer(text))
    if not marks:
        body = text.strip()
        return [{"no": "全文", "title": "", "body": body, "start": 0, "end": len(body)}]

    clauses: list[dict] = []
    for i, m in enumerate(marks):
        start = m.start()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        raw = text[start:end].strip()
        # 目录页里「一、」「二、」后面没字，切出来是空壳，跳过
        if len(re.sub(r"\s", "", raw)) < 8:
            continue
        head, _, rest = raw.partition("\n")
        no = m.group(0).strip().rstrip("、.")
        # 编号后面的那段：可能是一行标题，也可能就是正文本身（合同常常一条一行）
        after_mark = head[m.end() - start:].strip() if m.end() - start <= len(head) else ""
        if rest:
            title = after_mark if len(after_mark) <= 24 else ""
            body = (after_mark + "\n" + rest).strip()
        else:
            title = ""
            body = after_mark
        clauses.append({"no": no, "title": title, "body": body, "start": start, "end": end})
    return clauses


def split_sentences(text: str) -> list[str]:
    """按中文句号/分号/换行切句，短句丢掉。"""
    parts = re.split(r"[。；;\n]+", normalize(text))
    return [p.strip() for p in parts if len(p.strip()) >= 6]


def find_amounts(text: str) -> list[tuple[str, float]]:
    """抽出金额，统一换算成元。返回 (原文片段, 元)。"""
    out = []
    for m in _AMOUNT_RE.finditer(text):
        raw = m.group(0).strip()
        digits = m.group(1).replace(",", "").replace("，", "")
        try:
            value = float(digits)
        except ValueError:
            continue
        if m.group(2) in ("万元", "万"):
            value *= 10000
        out.append((raw, value))
    return out


def find_dates(text: str) -> list[tuple[str, str]]:
    """抽出日期，统一成 YYYY-MM-DD。"""
    out = []
    for m in _DATE_RE.finditer(text):
        y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            continue
        out.append((m.group(0).strip(), f"{y}-{mo:02d}-{d:02d}"))
    return out


def find_percents(text: str) -> list[tuple[str, float]]:
    """抽出百分比，返回 (原文, 数值如 30 表示 30%)。"""
    out = []
    for m in _PERCENT_RE.finditer(text):
        try:
            out.append((m.group(0).strip(), float(m.group(1))))
        except ValueError:
            continue
    return out


def find_days(text: str) -> list[tuple[str, int]]:
    """抽出「30 日」「七个工作日」这类天数。"""
    out = []
    for m in _DAY_RE.finditer(text):
        n = cn_to_int(m.group(1))
        if n:
            out.append((m.group(0).strip(), n))
    return out


def window(text: str, start: int, end: int, pad: int = 28) -> str:
    """取命中位置前后一小段原文，用来在报告里交代「凭什么」。"""
    return text[max(0, start - pad): min(len(text), end + pad)].replace("\n", " ").strip()
