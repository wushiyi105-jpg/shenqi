import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from shenqi import store, web

CONTRACT = """第一条 费用
合同总金额 60,000 元，甲方一次性支付全部款项。

第二条 续约
本合同到期自动续期一年。
"""


class TestWeb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        cls.conn = store.connect(os.path.join(cls.dir, "web.db"))
        cls.httpd = web.make_server(cls.conn, port=0)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.conn.close()

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def get(self, path):
        with urllib.request.urlopen(self.url(path), timeout=10) as r:
            return r.status, r.read().decode("utf-8")

    def post(self, path, payload):
        req = urllib.request.Request(
            self.url(path),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode("utf-8"))

    def test_index_page(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("审契", body)
        self.assertIn("/api/contracts", body)

    def test_contracts_empty_ok(self):
        status, body = self.get("/api/contracts")
        self.assertEqual(status, 200)
        self.assertIn("items", json.loads(body))

    def test_add_then_get(self):
        _, data = self.post("/api/add", {"title": "测试合同", "text": CONTRACT})
        cid = data["id"]
        self.assertIsInstance(cid, int)
        status, body = self.get(f"/api/contract?id={cid}")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["title"], "测试合同")
        self.assertEqual(payload["clauses"], 2)
        self.assertIsNone(payload["review"])

    def test_add_empty_text_400(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/api/add", {"text": "   "})
        self.assertEqual(ctx.exception.code, 400)

    def test_review_rules_only(self):
        _, data = self.post("/api/add", {"title": "规则版", "text": CONTRACT})
        cid = data["id"]
        status, payload = self.post("/api/review", {"id": cid, "rules_only": True})
        self.assertEqual(status, 200)
        self.assertIn("score", payload)
        self.assertEqual(payload["error"], "")
        _, body = self.get(f"/api/contract?id={cid}")
        rv = json.loads(body)["review"]
        self.assertIsNotNone(rv)
        self.assertTrue(any(i["code"] == "AUTO_RENEW" for i in rv["issues"]))

    def test_unknown_contract_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/api/contract?id=999")
        self.assertEqual(ctx.exception.code, 404)

    def test_bad_id_400(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/api/contract?id=abc")
        self.assertEqual(ctx.exception.code, 400)

    def test_rm(self):
        _, data = self.post("/api/add", {"title": "待删", "text": CONTRACT + "\n第三条 保密\n双方保密。"})
        cid = data["id"]
        _, payload = self.post("/api/rm", {"id": cid})
        self.assertTrue(payload["ok"])
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get(f"/api/contract?id={cid}")
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
