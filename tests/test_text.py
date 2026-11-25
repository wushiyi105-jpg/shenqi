import unittest

from shenqi import text as T

SAMPLE = """第一条 服务内容
乙方为甲方提供云盘企业版服务，账号数量 50 个。

第二条 服务费用
本合同总金额为人民币 36,000 元，甲方于签署后 5 个工作日内一次性支付全部款项。

第三条 服务期限
自 2026 年 12 月 1 日起至 2027 年 11 月 30 日止，共 12 个月。
"""


class TestCnToInt(unittest.TestCase):
    def test_digits(self):
        self.assertEqual(T.cn_to_int("30"), 30)

    def test_ten(self):
        self.assertEqual(T.cn_to_int("十"), 10)
        self.assertEqual(T.cn_to_int("十五"), 15)
        self.assertEqual(T.cn_to_int("三十"), 30)

    def test_hundred(self):
        self.assertEqual(T.cn_to_int("一百二十"), 120)

    def test_garbage(self):
        self.assertIsNone(T.cn_to_int("工作日"))


class TestNormalize(unittest.TestCase):
    def test_removes_zero_width_and_crlf(self):
        raw = "甲方\r\n乙方\u200b丙方\ufeff"
        self.assertEqual(T.normalize(raw), "甲方\n乙方丙方")

    def test_fullwidth_space(self):
        self.assertEqual(T.normalize("甲\u3000方"), "甲 方")


class TestSplitClauses(unittest.TestCase):
    def test_splits_by_clause_number(self):
        clauses = T.split_clauses(SAMPLE)
        self.assertEqual(len(clauses), 3)
        self.assertEqual(clauses[0]["no"], "第一条")
        self.assertIn("云盘企业版", clauses[0]["body"])

    def test_body_keeps_single_line_clause(self):
        """一条一行的情况最容易丢正文：编号后面就是内容，不是标题。"""
        clauses = T.split_clauses("第一条 本合同自签署之日起生效，有效期 12 个月。\n第二条 双方另行约定。")
        self.assertEqual(len(clauses), 2)
        self.assertIn("自签署之日起生效", clauses[0]["body"])
        self.assertIn("另行约定", clauses[1]["body"])

    def test_title_extracted_when_multiline(self):
        clause = T.split_clauses("第一条 服务内容\n乙方为甲方提供云盘服务。")[0]
        self.assertEqual(clause["title"], "服务内容")

    def test_no_number_falls_back_to_full_text(self):
        clauses = T.split_clauses("甲乙双方经协商一致，就服务事宜达成如下协议。")
        self.assertEqual(len(clauses), 1)
        self.assertEqual(clauses[0]["no"], "全文")
        self.assertIn("协商一致", clauses[0]["body"])

    def test_drops_empty_catalog_lines(self):
        clauses = T.split_clauses("一、\n二、\n第一条 甲方委托乙方提供服务，期限一年。")
        self.assertEqual(len(clauses), 1)
        self.assertEqual(clauses[0]["no"], "第一条")

    def test_chinese_numbering(self):
        clauses = T.split_clauses("一、甲方义务\n甲方应按期付款。\n二、乙方义务\n乙方应按期交付。")
        self.assertEqual([c["no"] for c in clauses], ["一", "二"])

    def test_offsets_point_back_to_source(self):
        body = SAMPLE
        clauses = T.split_clauses(body)
        for c in clauses:
            self.assertTrue(body[c["start"]: c["end"]].startswith(c["no"][:2]))


class TestExtract(unittest.TestCase):
    def test_amounts_with_comma(self):
        self.assertEqual(T.find_amounts("人民币 36,000 元"), [("人民币 36,000 元", 36000.0)])

    def test_amounts_in_wan(self):
        self.assertEqual(T.find_amounts("总价 5 万元")[0][1], 50000.0)

    def test_dates(self):
        found = T.find_dates("自 2026 年 12 月 1 日起")
        self.assertEqual(found[0][1], "2026-12-01")

    def test_dates_with_dash(self):
        self.assertEqual(T.find_dates("截止 2027-11-30")[0][1], "2027-11-30")

    def test_percents(self):
        self.assertEqual(T.find_percents("违约金为合同总额的 30%")[0][1], 30.0)

    def test_days(self):
        self.assertEqual(T.find_days("提前七个工作日通知")[0][1], 7)
        self.assertEqual(T.find_days("30 日内付清")[0][1], 30)

    def test_window_keeps_context(self):
        text = "甲" * 40 + "关键句" + "乙" * 40
        self.assertIn("关键句", T.window(text, 40, 43))


class TestSplitSentences(unittest.TestCase):
    def test_splits_and_drops_short(self):
        sentences = T.split_sentences("甲方应在十日内完成付款义务。乙方应按时交付成果；丙方负责验收。短")
        self.assertEqual(len(sentences), 3)
        self.assertNotIn("短", sentences)


if __name__ == "__main__":
    unittest.main()
