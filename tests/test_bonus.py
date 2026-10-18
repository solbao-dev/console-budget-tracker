import contextlib
import io
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from budget_app.backup import create_backup
from budget_app.formatting import cell, display_width, print_transactions
from budget_app.models import AppError
from budget_app.recurring import RecurringRule, RecurringService
from tests.test_required import CashbookCase


class BonusTests(CashbookCase):
    def test_recurring_input_retries_before_saving_rule(self) -> None:
        result = self.cli("recurring", "add", text=(
            "\nexpense\nmissing\nrent\n0\n50000\n32\n31\n월세\n고정\n"
        ))
        rules = RecurringService(self.service).store.load()
        self.assertEqual(len(rules), 1)
        self.assertEqual((rules[0].amount, rules[0].day), (50000, 31))
        self.assertEqual(result.stdout.count("매월 일자(1~31):"), 2)

    def test_bonus_help_and_recurring_cli_persistence(self) -> None:
        for path in (["backup"], ["recurring"], ["recurring", "add"], ["recurring", "list"],
                     ["recurring", "remove"], ["recurring", "generate"]):
            self.cli(*path, "--help")
        result = self.cli("recurring", "add", text="expense\nrent\n50000\n31\n월세\n고정\n")
        rule_id = result.stdout.split("rule_id=")[-1].strip()
        self.assertIn(rule_id, self.cli("recurring", "list").stdout)
        self.assertIn("generated=1", self.cli("recurring", "generate", "--month", "2026-02").stdout)
        self.assertIn("skipped=1", self.cli("recurring", "generate", "--month", "2026-02").stdout)
        self.cli("backup", "--out-dir", str(self.directory / "backups"))
        self.cli("recurring", "remove", "--id", rule_id)
        self.assertEqual(RecurringService(self.service).store.load(), [])

    def test_backup_contents_unique_and_failure_cleanup(self) -> None:
        self.service.add(self.transaction())
        output = self.directory / "backups"
        first = create_backup(self.service.directory, output)
        second = create_backup(self.service.directory, output)
        self.assertNotEqual(first, second)
        with ZipFile(first) as archive:
            self.assertEqual(set(archive.namelist()), {path.name for path in self.service.directory.glob("*.jsonl")})
            for source in self.service.directory.glob("*.jsonl"):
                self.assertEqual(archive.read(source.name), source.read_bytes())
        with patch("budget_app.backup.ZipFile.write", side_effect=OSError("backup failed")):
            with self.assertRaises(OSError):
                create_backup(self.service.directory, output)
        self.assertEqual(set(output.glob("*.zip")), {first, second})

    def test_table_width_control_characters_and_lazy_values(self) -> None:
        transaction = self.transaction(memo="한글\n\t\x1b" + "아주 긴 메모" * 20)
        original = transaction.memo
        self.assertEqual(display_width("한글a"), 5)
        self.assertEqual(display_width(cell(transaction.memo, 24)), 24)
        self.assertNotIn("\x1b", cell(transaction.memo, 24))
        events = []

        def rows():
            for _ in range(2):
                events.append("yield")
                yield transaction
                self.assertIn(transaction.id, captured.getvalue())

        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            print_transactions(rows())
        self.assertEqual(events, ["yield", "yield"])
        self.assertEqual(transaction.memo, original)

    def test_recurring_month_end_idempotency_and_delete_policies(self) -> None:
        recurring = RecurringService(self.service)
        rule = RecurringRule(type="expense", category="rent", amount=50000, day=31)
        recurring.add(rule)
        with self.assertRaises(AppError):
            self.service.category_remove("rent")
        self.assertEqual(recurring.generate("2026-02"), (1, 0))
        first = list(self.service.transactions.iter_transactions())[0]
        self.assertEqual(first.date, "2026-02-28")
        self.service.update(first.id, {"date": "2026-03-01", "amount": 60000})
        self.assertEqual(recurring.generate("2026-02"), (0, 1))
        self.service.delete(first.id)
        self.assertEqual(recurring.generate("2026-02"), (1, 0))
        self.assertEqual(recurring.generate("2028-02"), (1, 0))
        self.assertEqual(list(self.service.transactions.iter_transactions())[0].date, "2028-02-29")
        self.assertEqual(recurring.generate("2028-03"), (1, 0))
        recurring.remove(rule.id)
        self.assertEqual(len(list(self.service.transactions.iter_transactions())), 3)
        with self.assertRaises(AppError):
            recurring.remove(rule.id)

    def test_recurring_failure_preserves_transactions(self) -> None:
        recurring = RecurringService(self.service)
        recurring.add(RecurringRule(type="income", category="salary", amount=100, day=31))
        before = self.service.transactions.path.read_bytes()
        with patch("budget_app.repository.os.replace", side_effect=OSError("failed")):
            with self.assertRaises(OSError):
                recurring.generate("2026-10")
        self.assertEqual(self.service.transactions.path.read_bytes(), before)
        self.assertEqual(recurring.generate("2026-10"), (1, 0))
        for day in (0, 32, True, 1.5):
            with self.assertRaises(AppError):
                RecurringRule(type="income", category="salary", amount=1, day=day)
