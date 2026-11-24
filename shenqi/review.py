"""模型审阅：规则管「有没有」，模型管「对不对味」。

规则能抓的是硬信号（自动续约、无限责任、30% 违约金），抓不到的是语义层的东西——
验收标准写成了「双方另行商定」、独家条款藏在附件里、数据归属一句话都没提。这些
只能靠读。所以模型这部分的任务很窄：读条款，找出规则漏掉的语义风险，并给出改法。

一个硬约束：它引的每一句都必须是原文里真实存在的连续片段。引不出来就丢掉这条,
不跟它讲道理——编造原文是这类工具最不能忍的错。
"""

from __future__ import annotations

import re

from . import llm, rules
from . import text as T

SYSTEM = """你是给{side}（{side_note}）看合同的审阅律师。只看合同原文，不要补合同里没有的事实。

任务：找出下面这些条款里真正会影响甲方利益的语义风险。
不要重复我在【规则已经发现】里列过的问题。

每条风险给四个字段：
- clause_no：条款编号，必须和原文一致
- quote：从原文里原样摘的连续片段，20–60 字，一个字都不要改
- level：high（签之前必须改）/ medium（要谈）/ low（建议）
- why：为什么这是个坑，说人话，别用法律术语堆砌
- fix：怎么改，给一句可以直接替换进去的条款文字

另外给一个 summary：三句话以内说清这份合同最该盯的两三个点。

只输出 JSON：
{"risks": [{"clause_no": "", "quote": "", "level": "", "why": "", "fix": ""}], "summary": ""}

如果确实没有规则之外的风险，risks 给空数组。不要为了凑数编风险。"""


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n] + "…"


def _squash(s: str) -> str:
    """比对引文时去掉所有空白和标点差异，只比字。"""
    return re.sub(r"[\s，。、；：！？（）()“”\"'·,.;:!?\-—]", "", s or "")


def verify_quotes(risks: list[dict], full: str) -> tuple[list[dict], list[dict]]:
    """核验每条风险的 quote 是否真在原文里。返回 (留下的, 丢掉的)。"""
    squashed = _squash(full)
    kept, dropped = [], []
    for r in risks:
        q = (r.get("quote") or "").strip()
        if not q:
            dropped.append({**r, "why_dropped": "没有引原文"})
            continue
        if _squash(q) in squashed:
            kept.append(r)
            continue
        # 模型常把长句截一半再改写几个字，放宽到「前 10 个字能对上」也算它确实读了原文。
        # 取太长不行：10 个字之后往往就是它自己加的话，反而对不上。
        head = _squash(q)[:10]
        if head and head in squashed:
            kept.append({**r, "partial": True})
            continue
        dropped.append({**r, "why_dropped": "引文在原文里找不到"})
    return kept, dropped


def _dedup(risks: list[dict], rule_issues: list[dict]) -> list[dict]:
    """模型和规则报了同一处，留规则那条（它的证据更硬）。"""
    seen = {(i["clause_no"], _squash(i["quote"])[:12]) for i in rule_issues}
    out = []
    for r in risks:
        key = (r.get("clause_no", ""), _squash(r.get("quote", ""))[:12])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def ask(clauses: list[dict], rule_issues: list[dict], missing: list[dict], config=None,
        max_tokens: int = 3000, side: str = "甲方") -> dict:
    """调模型。失败不抛，返回空结果，让规则的结果照样能用。"""
    body = "\n\n".join(f"【{c['no']}】{c['body']}" for c in clauses)
    already = "\n".join(f"- {i['clause_no']} {i['name']}" for i in rule_issues) or "（无）"
    miss = "、".join(m["name"] for m in missing) or "（无）"
    side_note = "付款方" if side.startswith("甲") else "服务提供方"
    user = (
        f"【合同条款】\n{_clip(body, 6000)}\n\n"
        f"【规则已经发现】\n{already}\n\n"
        f"【缺失的必备条款】{miss}\n\n"
        "按要求输出 JSON。"
    )
    try:
        raw = llm.chat(
            [
                # 用 replace 而不是 format：prompt 里有 {"risks": ...} 这种花括号，
                # format 会把它当成占位符直接 KeyError
                {"role": "system", "content": SYSTEM.replace("{side_note}", side_note).replace("{side}", side)},
                {"role": "user", "content": user},
            ],
            config=config,
            temperature=0.2,
            max_tokens=max_tokens,
        )
        data = llm.extract_json(raw)
        if not isinstance(data, dict):
            raise llm.LLMError("返回的不是对象")
        return {"risks": data.get("risks") or [], "summary": (data.get("summary") or "").strip(), "error": ""}
    except llm.LLMError as e:
        return {"risks": [], "summary": "", "error": str(e)}


def review(contract_text: str, config=None, use_model: bool = True, side: str = "甲方") -> dict:
    """一份合同的完整体检：切条款 → 跑规则 → 问模型 → 核验引文 → 合并打分。"""
    full = T.normalize(contract_text)
    clauses = T.split_clauses(full)
    rule_issues = rules.run_rules(clauses, full, side=side)
    missing = rules.check_required(full)

    summary, error, model_risks, dropped = "", "", [], []
    if use_model:
        result = ask(clauses, rule_issues, missing, config=config, side=side)
        summary, error = result["summary"], result["error"]
        kept, dropped = verify_quotes(result["risks"], full)
        model_risks = _dedup(kept, rule_issues)

    model_issues = [
        {
            "code": "MODEL",
            "name": f"语义风险 · {r.get('clause_no') or '全文'}",
            "level": r.get("level") if r.get("level") in ("high", "medium", "low") else "medium",
            "clause_no": r.get("clause_no") or "—",
            "quote": r.get("quote", ""),
            "why": r.get("why", ""),
            "suggestion": r.get("fix", ""),
            "partial": bool(r.get("partial")),
        }
        for r in model_risks
    ]

    all_issues = rule_issues + model_issues
    order = {"high": 0, "medium": 1, "low": 2}
    all_issues.sort(key=lambda i: order.get(i["level"], 3))

    return {
        "clauses": clauses,
        "issues": all_issues,
        "missing": missing,
        "score": rules.score(all_issues, missing),
        "summary": summary,
        "error": error,
        "dropped": dropped,
        "rule_count": len(rule_issues),
        "model_count": len(model_issues),
    }
