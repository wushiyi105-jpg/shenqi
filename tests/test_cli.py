import contextlib
import io
import os
import tempfile
import unittest

from shenqi import cli

CONTRACT = """第一条 费用
合同总金额 60,000 元，甲方一次性支付全部款项。

第二条 续约
本合同到期自动续期一年。

第三条 责任
因乙方原因造成甲方一切损失的，乙方全额赔偿，不设上限。
"""


class TestCli(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "cli.db")
        self.file = os.path.join(self.dir, "合同.txt")
        with open(self.file, "w", encoding="utf-8") as f:
            f.write(CONTRACT)

    def run_cli(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(["--db", self.db, *args])
        return code, buf.getvalue()

    def test_add_then_list(self):
        code, out = self.run_cli("add", self.file)
        self.assertEqual(code, 0)
        self.assertIn("切出 3 条", out)
        code, out = self.run_cli("list")
        self.assertIn("合同", out)
        self.assertIn("未体检", out)

    def test_add_missing_file_is_reported(self):
        code, out = self.run_cli("add", os.path.join(self.dir, "没有.txt"))
        self.assertEqual(code, 0)
        self.assertIn("找不到文件", out)

    def test_add_custom_title(self):
        self.run_cli("add", self.file, "--title", "云盘服务合同")
        _, out = self.run_cli("list")
        self.assertIn("云盘服务合同", out)

    def test_review_rules_only(self):
        self.run_cli("add", self.file)
        code, out = self.run_cli("review", "1", "--rules-only")
        self.assertEqual(code, 0)
        self.assertIn("别签，先改", out)
        self.assertIn("自动续约没写退出方式", out)
        self.assertIn("规则", out)

    def test_review_unknown_id(self):
        code, out = self.run_cli("review", "9", "--rules-only")
        self.assertEqual(code, 1)
        self.assertIn("没有 id=9", out)

    def test_review_json(self):
        self.run_cli("add", self.file)
        _, out = self.run_cli("review", "1", "--rules-only", "--json")
        self.assertIn('"issues"', out)
        self.assertIn('"score"', out)

    def test_review_writes_markdown(self):
        self.run_cli("add", self.file)
        out_path = os.path.join(self.dir, "报告.md")
        self.run_cli("review", "1", "--rules-only", "--out", out_path)
        self.assertTrue(os.path.isfile(out_path))
        with open(out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("体检报告", content)
        self.assertIn("怎么改", content)

    def test_show(self):
        self.run_cli("add", self.file)
        _, out = self.run_cli("show", "1")
        self.assertIn("第一条", out)
        self.assertIn("还没体检过", out)

    def test_show_after_review_prints_history(self):
        self.run_cli("add", self.file)
        self.run_cli("review", "1", "--rules-only")
        _, out = self.run_cli("show", "1")
        self.assertIn("最近一次体检", out)
        self.assertIn("历史", out)

    def test_rm(self):
        self.run_cli("add", self.file)
        code, out = self.run_cli("rm", "1")
        self.assertEqual(code, 0)
        self.assertIn("已删除", out)
        _, listing = self.run_cli("list")
        self.assertIn("还没有合同", listing)

    def test_stats(self):
        self.run_cli("add", self.file)
        self.run_cli("review", "1", "--rules-only")
        _, out = self.run_cli("stats")
        self.assertIn("contracts", out)

    def test_side_option_passes_through(self):
        self.run_cli("add", self.file)
        _, out = self.run_cli("review", "1", "--rules-only", "--side", "乙方")
        self.assertEqual(out.count("==="), 2)  # 抬头一行标题两侧
        self.assertIn("高", out)


if __name__ == "__main__":
    unittest.main()
