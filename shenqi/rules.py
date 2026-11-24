"""硬规则体检：不花 token 的那一半。

模型会漏、会飘、会顺着你的话说。所以合同里那些「一票否决」型的问题——自动续约没
写怎么退、单方变更、无限责任、没有解除条款——先用正则和计数扫一遍，模型只负责
它擅长的部分：读懂语义、给出改法。

每条规则输出同一个结构，前端和报告都好排：
    {"code", "name", "level", "clause_no", "quote", "why", "suggestion"}
level 只有 high / medium / low 三档，high 是签之前必须改掉的。
"""

from __future__ import annotations

import re

from . import text as T

# 必备条款体检清单：(键, 名字, 判定正则, 缺了算什么)
REQUIRED = [
    ("price", "价款或报酬", r"元|金额|价款|费用|报酬|服务费"),
    ("term", "履行期限", r"有效期|期限|自.{0,12}起|至.{0,12}止"),
    ("delivery", "交付或验收", r"交付|提供|上线|验收|验收标准"),
    ("breach", "违约责任", r"违约"),
    ("dispute", "争议解决", r"仲裁|诉讼|管辖|争议"),
    ("exit", "解除或终止", r"解除|终止|退订|解约"),
    ("secret", "保密义务", r"保密|商业秘密"),
    ("ip", "知识产权归属", r"知识产权|著作权|成果归属|所有权"),
]


def _scan(clauses: list[dict], pattern: str):
    """在每条条款里跑一遍正则，返回 (条款, 匹配对象)。"""
    hits = []
    for c in clauses:
        for m in re.finditer(pattern, c["body"]):
            hits.append((c, m))
    return hits


def _issue(code, name, level, clause, quote, why, suggestion):
    return {
        "code": code,
        "name": name,
        "level": level,
        "clause_no": clause["no"] if clause else "—",
        "quote": quote,
        "why": why,
        "suggestion": suggestion,
    }


# ---------- 逐条规则 ----------
def rule_auto_renew(clauses, full):
    """自动续约：写了「自动续费」，却没写怎么退出。"""
    out = []
    for c, m in _scan(clauses, r"自动续(?:约|期|费|订|展期)"):
        body = c["body"]
        has_exit = re.search(r"提前\s*[0-9一二三四五六七八九十百]+\s*(?:个工作日|日|天)", body)
        has_notice = re.search(r"书面(?:通知|确认)|主动(?:取消|关闭)|可随时(?:取消|关闭)", body)
        if has_exit or has_notice:
            continue
        out.append(_issue(
            "AUTO_RENEW", "自动续约没写退出方式", "high", c,
            T.window(body, m.start(), m.end()),
            "只写了会自动续，没写提前几天、用什么方式取消，等于把续费的决定权单方面留给了对方。",
            "补一句：到期前 N 日可书面通知不续约，未通知视为续约一期；并写明取消入口。",
        ))
    return out


def rule_unilateral_change(clauses, full):
    """单方变更：一方可以自己改条款。"""
    out = []
    for c, m in _scan(clauses, r"单方(?:面)?(?:变更|修改|调整|终止|解除)"):
        body = c["body"]
        silent = re.search(r"无需(?:另行)?通知|无须通知|不必通知|不再(?:另行)?通知", body)
        out.append(_issue(
            "UNILATERAL_CHANGE", "允许单方变更条款", "high", c,
            T.window(body, m.start(), m.end()),
            "对方可以自己改规则，你的义务跟着变，这条基本等于合同没定。" + ("而且写明了不用通知你。" if silent else ""),
            "改成：变更需双方书面确认；或至少提前 30 日通知，你有权在通知期内无责终止。",
        ))
    return out


def rule_unlimited_liability(clauses, full):
    """无限责任：一切损失都要赔、还不设上限。"""
    out = []
    patterns = [
        (r"(?:一切|全部|所有)\s*(?:直接|间接)?\s*损失", "要把「一切损失」都赔上"),
        (r"不设(?:赔偿)?上限|不受(?:赔偿)?限额限制|无限(?:连带)?责任", "明确写了不设赔偿上限"),
        (r"(?:全额|全部)\s*赔偿", "要全额赔偿，没有封顶"),
    ]
    for pat, why in patterns:
        for c, m in _scan(clauses, pat):
            if re.search(r"(?:全额|全部)\s*(?:退还|退回|返还|退款)", c["body"][m.start(): m.end() + 4]):
                continue
            out.append(_issue(
                "UNLIMITED_LIABILITY", "赔偿责任无上限", "high", c,
                T.window(c["body"], m.start(), m.end()),
                why + "，一次事故可能赔掉整个项目利润。",
                "加责任限额：累计赔偿不超过合同总金额（或已付费用）的 100%，并排除间接损失、可得利益损失。",
            ))
    return out


def rule_full_prepay(clauses, full):
    """全额预付：钱先给完，活没交付。"""
    out = []
    for c, m in _scan(clauses, r"一次性(?:支付|付清)(?:全部|全额)|(?:预付|先行支付)(?:全部|全额)款?项?|款到(?:后)?(?:开始|启动)"):
        out.append(_issue(
            "FULL_PREPAY", "全额预付、交付在后", "medium", c,
            T.window(c["body"], m.start(), m.end()),
            "款项一次付清，交付却排在后面。对方不履约时你手里没有筹码，只能去打官司。",
            "拆成 3:4:3 或至少留 20%–30% 尾款，验收合格后支付。",
        ))
    return out


def rule_penalty(clauses, full):
    """违约金：比例过高，或者按日算得离谱。"""
    out = []
    for c in clauses:
        if "违约" not in c["body"]:
            continue
        for raw, pct in T.find_percents(c["body"]):
            if pct >= 30:
                out.append(_issue(
                    "PENALTY_HIGH", f"违约金比例 {pct:g}% 偏高", "high", c,
                    T.window(c["body"], c["body"].find(raw), c["body"].find(raw) + len(raw)),
                    f"一次违约就要付 {pct:g}%，法院通常按实际损失调整，写太高反而整条容易被认定无效。",
                    "违约金控制在合同总额的 20% 以内，或改为按实际损失赔偿 + 上限。",
                ))
        m = re.search(r"每日?\s*([0-9.]+)\s*%", c["body"])
        if m and float(m.group(1)) >= 0.5:
            out.append(_issue(
                "PENALTY_DAILY", f"按日违约金 {m.group(1)}% 过高", "medium", c,
                T.window(c["body"], m.start(), m.end()),
                f"每天 {m.group(1)}%，一个月就超过本金的三成，属于典型的高利式条款。",
                "按日万分之三到万分之五比较常见，并约定总额上限。",
            ))
    return out


def rule_missing_termination(clauses, full):
    """没有解除条款：想跑跑不掉。"""
    if re.search(r"解除|终止|退订|解约", full):
        return []
    return [_issue(
        "NO_TERMINATION", "全文没有解除或终止条款", "high", None, "（全文检索无命中）",
        "签了就没有退出机制，对方摆烂你也得陪着，或者只能等违约再打官司。",
        "补一条：任一方提前 30 日书面通知可解除；对方重大违约经催告 15 日未改正的，可立即解除并要求退款。",
    )]


def rule_missing_dispute(clauses, full):
    """没有争议解决条款：出事连去哪个法院都不确定。"""
    if re.search(r"仲裁|诉讼|管辖|争议", full):
        return []
    return [_issue(
        "NO_DISPUTE", "没有争议解决条款", "medium", None, "（全文检索无命中）",
        "没有约定管辖，真出问题要按法定管辖找法院，异地诉讼成本高、周期长。",
        "约定「由我方所在地人民法院管辖」，或约定明确的仲裁机构。",
    )]


def rule_no_tax(clauses, full):
    """谈钱不谈税，报销时才知道少了几个点。"""
    if not T.find_amounts(full):
        return []
    if re.search(r"含税|不含税|税费|税额|税率|发票", full):
        return []
    return [_issue(
        "NO_TAX", "金额没写是否含税", "low", None, "（全文检索无命中）",
        "合同写了钱，却没说含不含税、开什么票，结算时容易各说各话。",
        "写明「上述金额为含税价，乙方开具 6% 增值税专用发票」。",
    )]


def rule_no_effective_date(clauses, full):
    """没有日期，也没有生效条件。"""
    if T.find_dates(full) or re.search(r"生效|签署之日|签订之日", full):
        return []
    return [_issue(
        "NO_EFFECTIVE_DATE", "没有生效日期或生效条件", "low", None, "（全文检索无命中）",
        "看不出从哪天开始算，履约期、违约起算点都会扯皮。",
        "写明「本合同自双方签字盖章之日起生效，有效期 12 个月」。",
    )]


def rule_odd_jurisdiction(clauses, full):
    """管辖地在对方那里，等于把主场让出去。"""
    out = []
    for c, m in _scan(clauses, r"(?:甲方|乙方|对方|供方|需方)\s*(?:所在)?地(?:的)?(?:人民法院|仲裁委)"):
        body = c["body"]
        if re.search(r"我方所在地|本公司所在地", body):
            continue
        out.append(_issue(
            "ODD_JURISDICTION", "管辖约定在对方所在地", "low", c,
            T.window(body, m.start(), m.end()),
            "真打起来你要去对方城市立案、开庭，差旅和时间成本都由你先垫。",
            "争取改成我方所在地；谈不动就退一步，约定合同签订地。",
        ))
    return out


RULE_LIST = [
    rule_auto_renew,
    rule_unilateral_change,
    rule_unlimited_liability,
    rule_full_prepay,
    rule_penalty,
    rule_missing_termination,
    rule_missing_dispute,
    rule_no_tax,
    rule_no_effective_date,
    rule_odd_jurisdiction,
]


def _dedup(issues: list[dict]) -> list[dict]:
    """同一条款、同一个毛病只报一次。

    第五条那句「一切损失…全额赔偿，不设上限」三条正则全命中了，第一版报告里
    同一句话被列了三次，看着像有三倍风险。留证据最长的那条。
    """
    best: dict[tuple, dict] = {}
    for i in issues:
        key = (i["code"], i["clause_no"])
        cur = best.get(key)
        if cur is None or len(i["quote"]) > len(cur["quote"]):
            best[key] = i
    return list(best.values())


def run_rules(clauses: list[dict], full: str | None = None, side: str = "甲方") -> list[dict]:
    """跑完整套规则，按危险程度排序。

    side 是「替谁看合同」，默认甲方（付款方）。管辖那条规则必须知道这个：
    合同写「由甲方所在地法院管辖」，站在甲方这边是好事，站在乙方那边才是坑。
    第一版没区分，把改好的合同也报了一条「管辖在对方所在地」。
    """
    full = full if full is not None else "\n".join(c["body"] for c in clauses)
    issues = []
    for fn in RULE_LIST:
        try:
            issues.extend(fn(clauses, full))
        except Exception:  # 单条规则写错不该拖垮整次体检
            continue
    issues = _dedup(issues)
    if side:
        issues = [
            i for i in issues
            if not (i.get("code") == "ODD_JURISDICTION" and side in i.get("quote", ""))
        ]
    order = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda i: order.get(i["level"], 3))
    return issues


def check_required(full: str) -> list[dict]:
    """必备条款体检：缺了哪几样。"""
    missing = []
    for key, name, pattern in REQUIRED:
        if not re.search(pattern, full):
            missing.append({"key": key, "name": name})
    return missing


def score(issues: list[dict], missing: list[dict]) -> dict:
    """给个能排序的总分，100 分制。扣分规则写死，不交给模型。"""
    high = sum(1 for i in issues if i["level"] == "high")
    medium = sum(1 for i in issues if i["level"] == "medium")
    low = sum(1 for i in issues if i["level"] == "low")
    value = 100 - high * 12 - medium * 5 - low * 2 - len(missing) * 6
    value = max(0, min(100, value))
    verdict = "别签，先改" if high else ("可以谈，改完再签" if medium else "风险不大")
    return {"score": value, "high": high, "medium": medium, "low": low, "missing": len(missing), "verdict": verdict}
