"""探测智谱各个文本模型名到底能不能用（付费通道已充值）。

用法：python scripts/probe_zhipu.py
只打印 HTTP 状态和前 60 字，不做别的事。
"""

import json
import os
import urllib.error
import urllib.request

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
CANDIDATES = ["glm-4.6", "glm-4.6-air", "glm-4.6-flashx", "glm-4.6v-flashx", "glm-4.5-flash", "glm-4-flashx"]


def load_env():
    env = {}
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def probe(key, base, model):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "只回复两个字：可用"}],
        "temperature": 0.1,
        "max_tokens": 64,
    }
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            data = json.loads(r.read().decode("utf-8"))
        content = (data["choices"][0]["message"].get("content") or "").strip()
        print(f"{model:<18} 200  {content[:40] or '(空正文)'}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:120]
        print(f"{model:<18} {e.code}  {body}")
    except Exception as e:  # noqa: BLE001
        print(f"{model:<18} ERR  {repr(e)[:90]}")


env = load_env()
key = env.get("VISION_API_KEY") or ""
base = env.get("VISION_BASE_URL") or "https://open.bigmodel.cn/api/paas/v4"
for m in CANDIDATES:
    probe(key, base, m)
