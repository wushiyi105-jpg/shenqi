"""命令行入口。"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import llm, review, store
from . import text as T

LEVEL_LABEL = {"high": "高", "medium": "中", "low": "低"}


def _read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _open_db(args):
    return store.connect(args.db)


def cmd_add(args) -> int:
    conn = _open_db(args)
    for path in args.files:
        if not os.path.isfile(path):
            print(f"✗ 找不到文件：{path}")
            continue
        text = _read(path)
        title = args.title or os.path.splitext(os.path.basename(path))[0]
        cid = store.add_contract(conn, title, text, source=os.path.abspath(path))
        clauses = T.split_clauses(text)
        print(f"· 合同 [{cid}] {title} —— {len(text)} 字，切出 {len(clauses)} 条")
    print("  跑体检：python -m shenqi review <id>")
    return 0


def cmd_list(args) -> int:
    conn = _open_db(args)
    rows = store.list_contracts(conn)
    if not rows:
        print("还没有合同。先 python -m shenqi add samples/xxx.txt")
        return 0
    print(f"{'ID':<4}{'分数':<6}{'结论':<12}{'体检':<6}标题")
    for r in rows:
        score = r["score"] if r["score"] is not None else "—"
        verdict = r["verdict"] or "未体检"
        print(f"{r['id']:<4}{score!s:<6}{verdict:<12}{r['reviews']:<6}{r['title']}")
    return 0


def cmd_review(args) -> int:
    conn = _open_db(args)
    row = store.get_contract(conn, args.id)
    if not row:
        print(f"✗ 没有 id={args.id} 的合同")
        return 1

    cfg = llm.config_from_args(args)
    result = review.review(row["text"], config=cfg, use_model=not args.rules_only, side=args.side)
    store.save_review(conn, args.id, result)

    if result["error"] and not args.rules_only:
        print(f"! 模型这部分没跑成：{result['error']}", file=sys.stderr)
        print("  规则的结果照样给你，下面这些不依赖模型。\n", file=sys.stderr)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    s = result["score"]
    print(f"\n=== 合同 [{args.id}] {row['title']} · {s['score']} 分 · {s['verdict']} ===")
    print(f"高 {s['high']} · 中 {s['medium']} · 低 {s['low']} · 缺 {s['missing']} 项必备条款 "
          f"（规则 {result['rule_count']} 条 / 模型 {result['model_count']} 条）")

    if result["summary"]:
        print(f"\n一句话：{result['summary']}")

    if result["missing"]:
        print("\n缺的必备条款：" + "、".join(m["name"] for m in result["missing"]))

    for i, issue in enumerate(result["issues"], 1):
        print(f"\n[{LEVEL_LABEL.get(issue['level'], '?')}] {i}. {issue['name']}（{issue['clause_no']}）")
        if issue["quote"]:
            print(f"   原文：{issue['quote']}")
        print(f"   为什么：{issue['why']}")
        print(f"   怎么改：{issue['suggestion']}")

    if result["dropped"]:
        print(f"\n（模型给了 {len(result['dropped'])} 条引不出原文的风险，已丢弃，不列进报告）")

    if args.out:
        _write_markdown(args.out, row["title"], result)
        print(f"\n报告已写到 {args.out}")
    return 0


def _write_markdown(path: str, title: str, result: dict) -> None:
    s = result["score"]
    lines = [f"# {title} 体检报告", "", f"**{s['score']} 分 · {s['verdict']}**", "",
             f"高 {s['high']} · 中 {s['medium']} · 低 {s['low']} · 缺 {s['missing']} 项必备条款", ""]
    if result["summary"]:
        lines += [f"> {result['summary']}", ""]
    if result["missing"]:
        lines += ["## 缺失条款", "", "、".join(m["name"] for m in result["missing"]), ""]
    lines += ["## 风险清单", ""]
    for issue in result["issues"]:
        lines += [f"### [{LEVEL_LABEL.get(issue['level'], '?')}] {issue['name']}（{issue['clause_no']}）", ""]
        if issue["quote"]:
            lines += [f"- 原文：{issue['quote']}"]
        lines += [f"- 为什么：{issue['why']}", f"- 怎么改：{issue['suggestion']}", ""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def cmd_show(args) -> int:
    conn = _open_db(args)
    row = store.get_contract(conn, args.id)
    if not row:
        print(f"✗ 没有 id={args.id} 的合同")
        return 1
    print(f"\n=== [{row['id']}] {row['title']} ===\n来源：{row['source']}\n导入：{row['created_at']}\n")
    clauses = T.split_clauses(row["text"])
    for c in clauses:
        head = f"{c['no']}" + (f" {c['title']}" if c["title"] else "")
        print(f"--- {head} ---")
        print(T.normalize(c["body"])[:400])
        print()

    rv = store.latest_review(conn, args.id)
    if rv:
        print(f"最近一次体检：{rv['created_at']} · {rv['score']} 分 · {rv['verdict']}")
        print("历史：" + " → ".join(f"{h['score']}分({h['created_at'][5:16]})" for h in store.history(conn, args.id)))
    else:
        print("还没体检过：python -m shenqi review %d" % args.id)
    return 0


def cmd_rm(args) -> int:
    conn = _open_db(args)
    store.delete_contract(conn, args.id)
    print(f"· 合同 [{args.id}] 已删除（含体检记录）")
    return 0


def cmd_stats(args) -> int:
    conn = _open_db(args)
    print("统计：", store.stats(conn))
    return 0


def cmd_serve(args) -> int:
    from . import web

    conn = _open_db(args)
    web.serve(conn, host=args.host, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="shenqi", description="合同条款体检：规则扫一遍，模型再读一遍。")
    p.add_argument("--db", default="data/shenqi.db", help="库文件路径")
    p.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="导入合同")
    a.add_argument("files", nargs="+")
    a.add_argument("--title")
    a.set_defaults(func=cmd_add)

    sub.add_parser("list", help="合同列表").set_defaults(func=cmd_list)

    r = sub.add_parser("review", help="体检一份合同")
    r.add_argument("id", type=int)
    r.add_argument("--rules-only", action="store_true", help="只跑规则，不调模型（省钱、离线）")
    r.add_argument("--json", action="store_true")
    r.add_argument("--out", help="把报告写成 markdown")
    r.add_argument("--side", choices=["甲方", "乙方"], default="甲方", help="替哪一方看（默认甲方=付款方）")
    r.add_argument("--api-key")
    r.add_argument("--base-url")
    r.add_argument("--model")
    r.set_defaults(func=cmd_review)

    s = sub.add_parser("show", help="看原文、条款切分和体检历史")
    s.add_argument("id", type=int)
    s.set_defaults(func=cmd_show)

    d = sub.add_parser("rm", help="删一份合同")
    d.add_argument("id", type=int)
    d.set_defaults(func=cmd_rm)

    sub.add_parser("stats", help="统计").set_defaults(func=cmd_stats)

    w = sub.add_parser("serve", help="起 Web")
    w.add_argument("--host", default="127.0.0.1")
    w.add_argument("--port", type=int, default=8768)
    w.set_defaults(func=cmd_serve)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
