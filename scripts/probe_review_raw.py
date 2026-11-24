"""看一眼 glm-4.6 到底返回了什么：finish_reason、正文长度、前 400 字。"""

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shenqi import llm, review, store, rules
from shenqi import text as T

env = llm.load_dotenv()
conn = store.connect("data/shenqi.db")
row = store.get_contract(conn, 1)
full = T.normalize(row["text"])
clauses = T.split_clauses(full)
issues = rules.run_rules(clauses, full)
missing = rules.check_required(full)

body = "\n\n".join(f"【{c['no']}】{c['body']}" for c in clauses)
already = "\n".join(f"- {i['clause_no']} {i['name']}" for i in issues) or "（无）"
user = (
    f"【合同条款】\n{body}\n\n【规则已经发现】\n{already}\n\n"
    f"【缺失的必备条款】{'、'.join(m['name'] for m in missing) or '（无）'}\n\n按要求输出 JSON。"
)

cfg = llm.default_config()
payload = {
    "model": cfg["model"],
    "messages": [
        {"role": "system", "content": review.SYSTEM.replace("{side_note}", "付款方").replace("{side}", "甲方")},
        {"role": "user", "content": user},
    ],
    "temperature": 0.2,
    "max_tokens": int(os.environ.get("PROBE_MAX", "3000")),
}
req = urllib.request.Request(
    cfg["base_url"].rstrip("/") + "/chat/completions",
    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + cfg["api_key"]},
    method="POST",
)
with urllib.request.urlopen(req, timeout=120) as r:
    data = json.loads(r.read().decode("utf-8"))
ch = data["choices"][0]
content = ch["message"].get("content") or ""
print("model:", data.get("model"), "finish:", ch.get("finish_reason"), "len:", len(content))
print("usage:", data.get("usage"))
print("---- 前 400 字 ----")
print(content[:400])
