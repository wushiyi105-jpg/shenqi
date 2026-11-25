import unittest
from unittest import mock

from shenqi import llm, review
from shenqi import text as T

CONTRACT = """第一条 费用
合同总金额 60,000 元，甲方一次性支付全部款项。

第二条 续约
本合同到期自动续期一年。

第三条 责任
因乙方原因造成甲方一切损失的，乙方全额赔偿，不设上限。
"""


class TestVerifyQuotes(unittest.TestCase):
    def setUp(self):
        self.full = T.normalize(CONTRACT)

    def test_real_quote_kept(self):
        risks = [{"clause_no": "第一条", "quote": "甲方一次性支付全部款项", "level": "high"}]
        kept, dropped = review.verify_quotes(risks, self.full)
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped, [])

    def test_quote_with_punctuation_diff_still_kept(self):
        risks = [{"clause_no": "第一条", "quote": "合同总金额 60,000 元，甲方一次性支付", "level": "high"}]
        kept, _ = review.verify_quotes(risks, self.full)
        self.assertEqual(len(kept), 1)

    def test_fabricated_quote_dropped(self):
        risks = [{"clause_no": "第一条", "quote": "甲方应在三十日内分三期支付尾款", "level": "high"}]
        kept, dropped = review.verify_quotes(risks, self.full)
        self.assertEqual(kept, [])
        self.assertEqual(len(dropped), 1)
        self.assertIn("找不到", dropped[0]["why_dropped"])

    def test_empty_quote_dropped(self):
        kept, dropped = review.verify_quotes([{"quote": "  "}], self.full)
        self.assertEqual(kept, [])
        self.assertEqual(dropped[0]["why_dropped"], "没有引原文")

    def test_partial_prefix_match_marked(self):
        risks = [{"clause_no": "第一条", "quote": "甲方一次性支付全部款项并开具发票", "level": "medium"}]
        kept, _ = review.verify_quotes(risks, self.full)
        self.assertTrue(kept[0].get("partial"))


class TestDedup(unittest.TestCase):
    def test_model_duplicate_of_rule_is_dropped(self):
        rule_issues = [{"clause_no": "第三条", "quote": "乙方全额赔偿，不设上限", "name": "无上限"}]
        risks = [{"clause_no": "第三条", "quote": "乙方全额赔偿，不设上限", "why": "模型也看到了"}]
        out = review._dedup(risks, rule_issues)
        self.assertEqual(out, [])

    def test_different_clause_kept(self):
        rule_issues = [{"clause_no": "第三条", "quote": "乙方全额赔偿，不设上限", "name": "无上限"}]
        risks = [{"clause_no": "第一条", "quote": "甲方一次性支付全部款项", "why": "付款在前"}]
        self.assertEqual(len(review._dedup(risks, rule_issues)), 1)


class TestReviewOffline(unittest.TestCase):
    def test_rules_only_runs_without_model(self):
        result = review.review(CONTRACT, use_model=False)
        codes = {i["code"] for i in result["issues"]}
        self.assertIn("AUTO_RENEW", codes)
        self.assertIn("UNLIMITED_LIABILITY", codes)
        self.assertEqual(result["model_count"], 0)
        self.assertEqual(result["error"], "")

    def test_side_changes_jurisdiction_verdict(self):
        text = CONTRACT + "\n第四条 争议\n争议由乙方所在地人民法院管辖。"
        as_jia = review.review(text, use_model=False, side="甲方")
        as_yi = review.review(text, use_model=False, side="乙方")
        self.assertIn("ODD_JURISDICTION", {i["code"] for i in as_jia["issues"]})
        self.assertNotIn("ODD_JURISDICTION", {i["code"] for i in as_yi["issues"]})

    def test_clauses_and_score_present(self):
        result = review.review(CONTRACT, use_model=False)
        self.assertEqual(len(result["clauses"]), 3)
        self.assertIn("score", result["score"])
        self.assertIn(result["score"]["verdict"], ("别签，先改", "可以谈，改完再签", "风险不大"))


class TestModelFailure(unittest.TestCase):
    def test_llm_error_does_not_raise(self):
        with mock.patch.object(llm, "chat", side_effect=llm.LLMError("接口 429")):
            result = review.review(CONTRACT, use_model=True)
        self.assertIn("429", result["error"])
        self.assertEqual(result["model_count"], 0)
        self.assertTrue(result["issues"])  # 规则那部分照常在

    def test_model_returns_bad_json(self):
        with mock.patch.object(llm, "chat", return_value="我觉得这份合同还行"):
            result = review.review(CONTRACT, use_model=True)
        self.assertTrue(result["error"])
        self.assertEqual(result["model_count"], 0)

    def test_model_output_used_and_verified(self):
        canned = '{"risks":[{"clause_no":"第一条","quote":"甲方一次性支付全部款项","level":"medium","why":"钱先给完","fix":"分期支付"}],"summary":"先改付款"}'
        with mock.patch.object(llm, "chat", return_value=canned):
            result = review.review(CONTRACT, use_model=True)
        self.assertEqual(result["model_count"], 1)
        self.assertEqual(result["summary"], "先改付款")
        self.assertEqual(result["dropped"], [])

    def test_fabricated_quote_not_listed(self):
        canned = '{"risks":[{"clause_no":"第一条","quote":"双方约定以比特币结算","level":"high","why":"编的","fix":"无"}],"summary":""}'
        with mock.patch.object(llm, "chat", return_value=canned):
            result = review.review(CONTRACT, use_model=True)
        self.assertEqual(result["model_count"], 0)
        self.assertEqual(len(result["dropped"]), 1)

    def test_model_risk_sorted_into_levels(self):
        canned = '{"risks":[{"clause_no":"第一条","quote":"甲方一次性支付全部款项","level":"乱写","why":"x","fix":"y"}],"summary":""}'
        with mock.patch.object(llm, "chat", return_value=canned):
            result = review.review(CONTRACT, use_model=True)
        model_issue = [i for i in result["issues"] if i["code"] == "MODEL"][0]
        self.assertEqual(model_issue["level"], "medium")


if __name__ == "__main__":
    unittest.main()
