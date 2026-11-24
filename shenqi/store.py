"""SQLite 存取：合同原文 + 每次体检的结果。

一个库文件放全部。合同按内容哈希去重（同一份合同重复导入不会堆两份）,
审阅结果每次都留一条，方便对比「改完以后分有没有涨」。
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from datetime import datetime

_LOCK = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    sha TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_contract_sha ON contracts(sha);
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    score INTEGER NOT NULL,
    verdict TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    issues TEXT NOT NULL DEFAULT '[]',
    missing TEXT NOT NULL DEFAULT '[]',
    rule_count INTEGER NOT NULL DEFAULT 0,
    model_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def connect(path: str = "data/shenqi.db") -> sqlite3.Connection:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def add_contract(conn, title: str, text: str, source: str = "") -> int:
    """加一份合同。同一份内容再导入就覆盖标题和来源，不新建。"""
    h = sha(text)
    with _LOCK:
        row = conn.execute("SELECT id FROM contracts WHERE sha=?", (h,)).fetchone()
        if row:
            conn.execute("UPDATE contracts SET title=?, source=? WHERE id=?", (title, source, row["id"]))
            conn.commit()
            return row["id"]
        cur = conn.execute(
            "INSERT INTO contracts(title, source, sha, text, created_at) VALUES (?,?,?,?,?)",
            (title, source, h, text, now()),
        )
        conn.commit()
        return cur.lastrowid


def list_contracts(conn) -> list[dict]:
    rows = conn.execute(
        """SELECT c.id, c.title, c.source, c.created_at,
                  (SELECT score FROM reviews r WHERE r.contract_id=c.id ORDER BY r.id DESC LIMIT 1) score,
                  (SELECT verdict FROM reviews r WHERE r.contract_id=c.id ORDER BY r.id DESC LIMIT 1) verdict,
                  (SELECT COUNT(*) FROM reviews r WHERE r.contract_id=c.id) reviews
           FROM contracts c ORDER BY c.id DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


def get_contract(conn, contract_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM contracts WHERE id=?", (contract_id,)).fetchone()
    return dict(row) if row else None


def delete_contract(conn, contract_id: int) -> None:
    with _LOCK:
        conn.execute("DELETE FROM reviews WHERE contract_id=?", (contract_id,))
        conn.execute("DELETE FROM contracts WHERE id=?", (contract_id,))
        conn.commit()


def save_review(conn, contract_id: int, result: dict) -> int:
    with _LOCK:
        cur = conn.execute(
            """INSERT INTO reviews(contract_id, score, verdict, summary, issues, missing,
                                   rule_count, model_count, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                contract_id,
                result["score"]["score"],
                result["score"]["verdict"],
                result.get("summary", ""),
                json.dumps(result["issues"], ensure_ascii=False),
                json.dumps(result["missing"], ensure_ascii=False),
                result.get("rule_count", 0),
                result.get("model_count", 0),
                now(),
            ),
        )
        conn.commit()
        return cur.lastrowid


def latest_review(conn, contract_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM reviews WHERE contract_id=? ORDER BY id DESC LIMIT 1", (contract_id,)
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["issues"] = json.loads(d["issues"])
    d["missing"] = json.loads(d["missing"])
    return d


def history(conn, contract_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, score, verdict, created_at FROM reviews WHERE contract_id=? ORDER BY id", (contract_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def stats(conn) -> dict:
    contracts = conn.execute("SELECT COUNT(*) n FROM contracts").fetchone()["n"]
    reviews = conn.execute("SELECT COUNT(*) n FROM reviews").fetchone()["n"]
    avg = conn.execute("SELECT AVG(score) a FROM reviews").fetchone()["a"]
    issues = conn.execute(
        "SELECT SUM(rule_count) r, SUM(model_count) m FROM reviews"
    ).fetchone()
    return {
        "contracts": contracts,
        "reviews": reviews,
        "avg_score": round(avg, 1) if avg else 0,
        "rule_issues": issues["r"] or 0,
        "model_issues": issues["m"] or 0,
    }
