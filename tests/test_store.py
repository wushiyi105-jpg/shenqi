import os
import tempfile
import unittest

from shenqi import store

CONTRACT = "第一条 费用\n合同总金额 60,000 元。\n第二条 期限\n有效期 12 个月。"

RESULT = {
    "score": {"score": 72, "verdict": "可以谈，改完再签", "high": 1, "medium": 1, "low": 0, "missing": 2},
    "issues": [{"code": "NO_TAX", "level": "low", "clause_no": "—", "name": "金额没写是否含税",
                "quote": "（全文检索无命中）", "why": "x", "suggestion": "y"}],
    "missing": [{"key": "dispute", "name": "争议解决"}],
    "summary": "先补税和管辖",
    "rule_count": 1,
    "model_count": 0,
}


class TestStore(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "t.db")
        self.conn = store.connect(self.path)

    def tearDown(self):
        self.conn.close()

    def test_add_returns_id(self):
        self.assertEqual(store.add_contract(self.conn, "测试合同", CONTRACT), 1)

    def test_same_content_not_duplicated(self):
        a = store.add_contract(self.conn, "合同A", CONTRACT, source="x")
        b = store.add_contract(self.conn, "合同A改名", CONTRACT, source="y")
        self.assertEqual(a, b)
        self.assertEqual(len(store.list_contracts(self.conn)), 1)
        self.assertEqual(store.get_contract(self.conn, a)["title"], "合同A改名")

    def test_different_content_new_row(self):
        store.add_contract(self.conn, "A", CONTRACT)
        store.add_contract(self.conn, "B", CONTRACT + "\n第三条 保密\n双方保密。")
        self.assertEqual(len(store.list_contracts(self.conn)), 2)

    def test_save_and_read_review(self):
        cid = store.add_contract(self.conn, "A", CONTRACT)
        store.save_review(self.conn, cid, RESULT)
        rv = store.latest_review(self.conn, cid)
        self.assertEqual(rv["score"], 72)
        self.assertEqual(rv["issues"][0]["code"], "NO_TAX")
        self.assertEqual(rv["missing"][0]["key"], "dispute")

    def test_latest_review_is_newest(self):
        cid = store.add_contract(self.conn, "A", CONTRACT)
        store.save_review(self.conn, cid, RESULT)
        better = {**RESULT, "score": {**RESULT["score"], "score": 95, "verdict": "风险不大"}}
        store.save_review(self.conn, cid, better)
        self.assertEqual(store.latest_review(self.conn, cid)["score"], 95)

    def test_history_in_order(self):
        cid = store.add_contract(self.conn, "A", CONTRACT)
        store.save_review(self.conn, cid, RESULT)
        store.save_review(self.conn, cid, {**RESULT, "score": {**RESULT["score"], "score": 90}})
        scores = [h["score"] for h in store.history(self.conn, cid)]
        self.assertEqual(scores, [72, 90])

    def test_list_shows_latest_score(self):
        cid = store.add_contract(self.conn, "A", CONTRACT)
        store.save_review(self.conn, cid, RESULT)
        row = store.list_contracts(self.conn)[0]
        self.assertEqual(row["score"], 72)
        self.assertEqual(row["reviews"], 1)

    def test_list_without_review_is_none(self):
        store.add_contract(self.conn, "A", CONTRACT)
        self.assertIsNone(store.list_contracts(self.conn)[0]["score"])

    def test_delete_removes_reviews_too(self):
        cid = store.add_contract(self.conn, "A", CONTRACT)
        store.save_review(self.conn, cid, RESULT)
        store.delete_contract(self.conn, cid)
        self.assertIsNone(store.get_contract(self.conn, cid))
        self.assertIsNone(store.latest_review(self.conn, cid))

    def test_stats(self):
        cid = store.add_contract(self.conn, "A", CONTRACT)
        store.save_review(self.conn, cid, RESULT)
        s = store.stats(self.conn)
        self.assertEqual(s["contracts"], 1)
        self.assertEqual(s["reviews"], 1)
        self.assertEqual(s["avg_score"], 72.0)
        self.assertEqual(s["rule_issues"], 1)

    def test_connect_creates_parent_dir(self):
        nested = os.path.join(self.dir, "a", "b", "x.db")
        conn = store.connect(nested)
        self.assertTrue(os.path.isfile(nested))
        conn.close()

    def test_sha_stable(self):
        self.assertEqual(store.sha("abc"), store.sha("abc"))
        self.assertNotEqual(store.sha("abc"), store.sha("abd"))


if __name__ == "__main__":
    unittest.main()
