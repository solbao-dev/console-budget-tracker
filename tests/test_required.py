"""실제 사용자 data 대신 매번 독립 임시 폴더에서 검증한다."""
import csv
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from budget_app.exchange import export_csv, import_csv
from budget_app.models import AppError, Transaction, positive_int
from budget_app.repository import atomic_text
from budget_app.service import BudgetService

ROOT = Path(__file__).resolve().parents[1]


class CashbookCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.service = BudgetService(self.directory / "data")

    def cli(self, *args: str, text: str = "", ok: bool = True) -> subprocess.CompletedProcess:
        result = subprocess.run([sys.executable, "-X", "utf8", "-m", "budget_app", "--data-dir",
                                 str(self.service.directory), *args], input=text, text=True,
                                encoding="utf-8", capture_output=True, cwd=ROOT)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("힌트", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
        return result

    def transaction(self, day: str = "2026-10-02", **values: object) -> Transaction:
        fields = dict(date=day, type="expense", category="food", amount=15000)
        fields.update(values)
        return Transaction(**fields)


class RequiredTests(CashbookCase):
    def test_add_retries_each_invalid_field_and_saves_once(self) -> None:
        result = self.cli("add", text=(
            "2026-02-30\n2026-10-18\n\nwrong\nexpense\nmissing\nfood\n"
            "0\n-1\n1.5\n15000\n점심\n식사\n"
        ))
        rows = list(self.service.transactions.iter_transactions())
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0].date, rows[0].type, rows[0].category, rows[0].amount),
                         ("2026-10-18", "expense", "food", 15000))
        self.assertEqual(result.stdout.count("날짜(YYYY-MM-DD):"), 2)
        self.assertEqual(result.stdout.count("타입(income/expense):"), 3)
        self.assertEqual(result.stdout.count("카테고리(food/transport/rent/salary/etc):"), 2)
        self.assertIn("같은 항목을 다시 입력", result.stderr)

    def test_category_prompt_uses_current_registered_names(self) -> None:
        self.service.category_add("book")
        self.service.category_remove("etc")
        result = self.cli("add", text="2026-10-18\nexpense\nbook\n1000\n독서\n\n")
        self.assertIn("카테고리(food/transport/rent/salary/book):", result.stdout)
        self.assertNotIn("/etc", result.stdout)
        self.assertEqual(list(self.service.transactions.iter_transactions())[0].category, "book")

    def test_add_eof_or_cancel_during_retry_preserves_transactions(self) -> None:
        from budget_app.cli import main

        self.service.add(self.transaction())
        before = self.service.transactions.path.read_bytes()
        self.cli("add", text="2026-10-18\nwrong\n", ok=False)
        self.assertEqual(before, self.service.transactions.path.read_bytes())
        with patch("builtins.input", side_effect=["2026-10-18", "wrong", KeyboardInterrupt]):
            with patch("sys.stderr"), patch("sys.stdout"):
                self.assertEqual(main(["--data-dir", str(self.service.directory), "add"]), 1)
        self.assertEqual(before, self.service.transactions.path.read_bytes())

    def test_cli_all_commands_and_persistence(self) -> None:
        result = self.cli("add", text="2026-10-02\nexpense\nfood\n15000\n점심\n식사,친구\n")
        transaction_id = result.stdout.split("id=")[-1].strip()
        self.assertIn(transaction_id, self.cli("list", "--limit", "1").stdout)
        self.assertIn(transaction_id, self.cli("search", "--tag", "친구").stdout)
        self.cli("budget", "set", "--month", "2026-10", "--amount", "10000")
        self.assertIn("10000", self.cli("budget", "get", "--month", "2026-10").stdout)
        self.assertIn("예산 초과", self.cli("summary", "--month", "2026-10").stdout)
        self.cli("category", "add", text="book\n")
        self.assertIn("book", self.cli("category", "list").stdout)
        self.cli("category", "remove", text="food\n", ok=False)
        self.cli("category", "remove", text="book\n")
        self.cli("update", "--id", transaction_id, "--memo", "", "--tags", "")
        self.assertEqual(self.service.find(transaction_id).tags, [])
        output = self.directory / "out.csv"
        self.cli("export", "--out", str(output), "--month", "2026-10")
        self.cli("import", "--from", str(output))
        self.cli("delete", "--id", transaction_id)
        self.cli("delete", "--id", transaction_id, ok=False)
        self.assertEqual(len(list(self.service.transactions.iter_transactions())), 1)
        self.assertGreaterEqual(len(list(self.service.directory.glob("*.jsonl"))), 3)

    def test_all_required_help(self) -> None:
        paths = [[], ["add"], ["list"], ["search"], ["summary"], ["update"], ["delete"],
                 ["import"], ["export"], ["category"], ["budget"], ["budget", "get"],
                 ["budget", "set"], ["category", "add"], ["category", "list"], ["category", "remove"]]
        for path in paths:
            with self.subTest(path=path):
                self.assertIn("usage:", self.cli(*path, "--help").stdout)

    def test_sort_after_add_update_import_and_and_search(self) -> None:
        newer = self.transaction("2026-10-20", memo="한글, 점심", tags=["식사"])
        older = self.transaction("2026-01-01")
        self.service.add(newer)
        self.service.add(older)
        self.service.update(older.id, {"date": "2026-12-01"})
        import_csv(self.service, ROOT / "examples/import_sample.csv")
        rows = list(self.service.transactions.iter_transactions())
        self.assertEqual([row.sort_key() for row in rows], sorted([row.sort_key() for row in rows], reverse=True))
        matches = list(self.service.search("2026-10-20", "2026-10-20", "food", "expense", "점심", "식사"))
        self.assertEqual([row.id for row in matches], [newer.id])
        self.assertEqual(list(self.service.search(tag="식")), [])

    def test_invalid_inputs_and_exit_codes(self) -> None:
        for value in (0, -1, 1.5, True, False, "0", "-1", "1.5"):
            with self.subTest(value=value), self.assertRaises(AppError):
                positive_int(value)
        for values in ({"date": "2026-02-30"}, {"type": "other"}, {"amount": True}):
            with self.assertRaises(AppError):
                self.transaction(**values)
        failures = [("list", "--limit", "0"), ("summary", "--month", "2026-13"),
                    ("summary", "--month", "2026-10", "--top", "0"),
                    ("search", "--from", "2026-10-02", "--to", "2026-01-01"),
                    ("search", "--type", "bad"), ("search", "--category", "unknown"),
                    ("update", "--id", "missing"), ("update", "--id", "missing", "--memo", "x"),
                    ("delete", "--id", "missing"), ("unknown",)]
        for args in failures:
            with self.subTest(args=args):
                self.cli(*args, ok=False)
        self.cli("add", text="2026-10-01\nexpense\nmissing\n1\n\n\n", ok=False)
        self.cli("add", text="", ok=False)
        self.cli("category", "add", text="\n", ok=False)
        self.cli("category", "add", text="food\n", ok=False)
        self.cli("category", "remove", text="missing\n", ok=False)

    def test_sample_summary_and_empty_budget(self) -> None:
        import_csv(self.service, ROOT / "examples/import_sample.csv")
        result = self.service.summary("2026-10", 3)
        self.assertEqual((result["income"], result["expense"], result["balance"]), (100000, 23000, 77000))
        self.assertEqual(result["top"], [("food", 20000), ("transport", 3000)])
        self.cli("budget", "set", "--month", "2027-01", "--amount", "100")
        self.assertIn("데이터 없음", self.cli("summary", "--month", "2027-01").stdout)

    def test_csv_roundtrip_optional_headers_and_rollback(self) -> None:
        transaction = self.transaction(memo='한글, "따옴표"\n다음 줄', tags=["하나", "둘"])
        self.service.add(transaction)
        output = self.directory / "roundtrip.csv"
        export_csv(self.service, output, month="2026-10")
        import_csv(self.service, output)
        rows = list(self.service.transactions.iter_transactions())
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row.memo == transaction.memo and row.tags == transaction.tags for row in rows))
        csv_path = self.directory / "in.csv"
        csv_path.write_text("date,type,category,amount\n2026-10-01,income,salary,1\n", encoding="utf-8")
        self.assertEqual(import_csv(self.service, csv_path), 1)
        before = self.service.transactions.path.read_bytes()
        for content in ("date,type,category,amount\n2026-10-01,income,salary,1\n2026-02-30,expense,food,2\n",
                        "date,type,category,amount\n2026-10-01,expense,missing,1\n",
                        "date,type,category,amount\n2026-10-01,expense,food,0\n",
                        "date,type,category,amount\n\"unterminated", "date,type\n"):
            csv_path.write_text(content, encoding="utf-8")
            with self.assertRaisesRegex(AppError, "imported=0"):
                import_csv(self.service, csv_path)
            self.assertEqual(before, self.service.transactions.path.read_bytes())

        # 정상 9건 뒤 마지막 입력이 잘못되어도 0건만 반영되어야 한다.
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["date", "type", "category", "amount"])
            for index in range(10):
                writer.writerow(["2026-10-01", "expense", "food", 100 if index < 9 else 0])
        with self.assertRaisesRegex(AppError, "imported=0"):
            import_csv(self.service, csv_path)
        self.assertEqual(before, self.service.transactions.path.read_bytes())

    def test_atomic_write_and_replace_failures(self) -> None:
        self.service.add(self.transaction())
        path = self.service.transactions.path
        before = path.read_bytes()
        with self.assertRaises(OSError):
            with atomic_text(path) as handle:
                handle.write("partial")
                raise OSError("注入: write failed")
        self.assertEqual(before, path.read_bytes())
        with patch("budget_app.repository.os.replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError):
                self.service.add(self.transaction())
        self.assertEqual(before, path.read_bytes())
        self.assertEqual(list(path.parent.glob(".cashbook-*")), [])

    def test_corruption_and_order_violation_preserve_original(self) -> None:
        path = self.service.transactions.path
        valid = json.dumps(asdict(self.transaction()), ensure_ascii=False) + "\n"
        for content in (valid + "broken\n", valid + valid, '{"amount": 1}\n'):
            path.write_text(content, encoding="utf-8")
            before = path.read_bytes()
            self.cli("list", "--limit", "10", ok=False)
            with self.assertRaises(AppError):
                self.service.add(self.transaction())
            self.assertEqual(before, path.read_bytes())

    def test_export_validation_and_preserves_existing_output(self) -> None:
        output = self.directory / "out.csv"
        output.write_text("old", encoding="utf-8")
        for kwargs in ({}, {"month": "2026-10", "start": "2026-01-01"},
                       {"start": "2026-12-01", "end": "2026-01-01"}):
            with self.assertRaises(AppError):
                export_csv(self.service, output, **kwargs)
            self.assertEqual(output.read_text(encoding="utf-8"), "old")
        with self.assertRaises(AppError):
            export_csv(self.service, self.service.transactions.path, month="2026-10")
        with patch("budget_app.repository.os.replace", side_effect=OSError("failed")):
            with self.assertRaises(OSError):
                export_csv(self.service, output, start="2026-01-01")
        self.assertEqual(output.read_text(encoding="utf-8"), "old")

    def test_lazy_read_stops_before_tail_corruption(self) -> None:
        self.service.add(self.transaction())
        with self.service.transactions.path.open("a", encoding="utf-8") as handle:
            handle.write("broken\n")
        self.cli("list", "--limit", "1")
        self.cli("list", "--limit", "2", ok=False)


if __name__ == "__main__":
    unittest.main()
