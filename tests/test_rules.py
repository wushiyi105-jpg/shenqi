import unittest

from shenqi import rules
from shenqi import text as T

BAD = """第一条 服务内容
乙方为甲方提供年度顾问服务。

第二条 费用
合同总金额 60,000 元，甲方于签署后一次性支付全部款项。

第三条 续约
本合同到期自动续期一年。

第四条 变更
甲方有权单方面调整服务范围与价格，无需另行通知乙方。

第五条 责任
因乙方原因造成甲方一切损失，乙方全额赔偿，不设上限。

第六条 违约
任一方违约的，应向对方支付合同总额 30% 的违约金。

第七条 保密
双方对合同内容负有保密义务。
"""

GOOD = """第一条 服务内容
乙方为甲方提供年度顾问服务。

第二条 费用与发票
合同总金额 60,000 元（含税），乙方开具 6% 增值税专用发票。甲方分三期支付：签署后 30%、交付后 40%、验收合格后 30%。

第三条 期限
自 2026 年 12 月 1 日起生效，有效期 12 个月。

第四条 交付与验收
乙方按季度交付成果，甲方在收到后 10 个工作日内验收。

第五条 违约责任
任一方违约，赔偿对方实际损失，累计不超过合同总金额。

第六条 解除
任一方可提前 30 日书面通知解除本合同；对方重大违约经催告 15 日未改正的，可立即解除。

第七条 保密
双方对合同内容及商业信息负有保密义务。

第八条 知识产权
交付成果的知识产权归甲方所有。

第九条 争议解决
争议由甲方所在地人民法院管辖。
"""


def codes(issues):
    return {i["code"] for i in issues}


class TestRulesBad(unittest.TestCase):
    def setUp(self):
        self.clauses = T.split_clauses(BAD)
        self.issues = rules.run_rules(self.clauses, BAD)

    def test_auto_renew_flagged(self):
        self.assertIn("AUTO_RENEW", codes(self.issues))

    def test_unilateral_change_flagged(self):
        self.assertIn("UNILATERAL_CHANGE", codes(self.issues))

    def test_unlimited_liability_flagged(self):
        self.assertIn("UNLIMITED_LIABILITY", codes(self.issues))

    def test_full_prepay_flagged(self):
        self.assertIn("FULL_PREPAY", codes(self.issues))

    def test_penalty_flagged(self):
        self.assertIn("PENALTY_HIGH", codes(self.issues))

    def test_missing_termination_flagged(self):
        self.assertIn("NO_TERMINATION", codes(self.issues))

    def test_missing_dispute_flagged(self):
        self.assertIn("NO_DISPUTE", codes(self.issues))

    def test_each_issue_has_evidence(self):
        for issue in self.issues:
            self.assertIn(issue["level"], ("high", "medium", "low"))
            self.assertTrue(issue["why"])
            self.assertTrue(issue["suggestion"])
            self.assertTrue(issue["quote"])

    def test_high_issues_sort_first(self):
        levels = [i["level"] for i in self.issues]
        self.assertEqual(levels[0], "high")
        self.assertEqual(levels, sorted(levels, key=lambda x: {"high": 0, "medium": 1, "low": 2}[x]))


class TestRulesGood(unittest.TestCase):
    def setUp(self):
        self.full = GOOD
        self.clauses = T.split_clauses(GOOD)
        self.issues = rules.run_rules(self.clauses, GOOD)

    def test_clean_contract_has_few_issues(self):
        high = [i for i in self.issues if i["level"] == "high"]
        self.assertEqual(high, [])

    def test_auto_renew_with_exit_not_flagged(self):
        issues = rules.run_rules(T.split_clauses("第三条 本合同到期自动续期一年，任一方可提前 30 日书面通知不续约。"))
        self.assertNotIn("AUTO_RENEW", codes(issues))

    def test_full_refund_is_not_unlimited_liability(self):
        issues = rules.run_rules(T.split_clauses("第五条 服务未提供的，乙方全额退还已收费用。"))
        self.assertNotIn("UNLIMITED_LIABILITY", codes(issues))

    def test_required_all_present(self):
        self.assertEqual(rules.check_required(GOOD), [])

    def test_score_is_high(self):
        s = rules.score(self.issues, rules.check_required(GOOD))
        self.assertGreaterEqual(s["score"], 80)
        self.assertEqual(s["verdict"], "风险不大")


class TestRequiredAndScore(unittest.TestCase):
    def test_missing_items_detected(self):
        missing = rules.check_required("甲方付款，乙方提供服务。")
        keys = {m["key"] for m in missing}
        self.assertIn("dispute", keys)
        self.assertIn("exit", keys)
        self.assertIn("secret", keys)

    def test_score_drops_on_high(self):
        issues = rules.run_rules(T.split_clauses(BAD), BAD)
        s = rules.score(issues, rules.check_required(BAD))
        self.assertLess(s["score"], 60)
        self.assertEqual(s["verdict"], "别签，先改")

    def test_score_never_negative(self):
        issues = [{"level": "high"}] * 30
        self.assertEqual(rules.score(issues, [{}] * 10)["score"], 0)

    def test_broken_rule_does_not_crash(self):
        org = rules.RULE_LIST[:]
        try:
            rules.RULE_LIST.append(lambda c, f: (_ for _ in ()).throw(RuntimeError("boom")))
            issues = rules.run_rules(T.split_clauses(BAD), BAD)
            self.assertIsInstance(issues, list)
        finally:
            rules.RULE_LIST[:] = org


if __name__ == "__main__":
    unittest.main()
