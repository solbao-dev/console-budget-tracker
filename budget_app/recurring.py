"""보너스: 월 반복 규칙. 거래 파일 하나의 교체로 생성과 중복 표시를 함께 저장."""
from calendar import monthrange
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from .models import AppError, Transaction, valid_month
from .repository import read_jsonl, write_jsonl

if TYPE_CHECKING:
    from .service import BudgetService


@dataclass
class RecurringRule:
    type: str
    category: str
    amount: int
    day: int
    memo: str = ""
    tags: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        if type(self.day) is not int or not 1 <= self.day <= 31:
            raise AppError("반복 일자는 1~31 정수여야 합니다.")
        Transaction(date="2000-01-01", type=self.type, category=self.category,
                    amount=self.amount, memo=self.memo, tags=self.tags, id=self.id)


class RecurringStore:
    def __init__(self, directory: Path) -> None:
        self.path = directory / "recurring.jsonl"
        if not self.path.exists():
            write_jsonl(self.path, ())

    def load(self) -> list[RecurringRule]:
        rules = []
        ids = set()
        for line, record in read_jsonl(self.path):
            try:
                if not {"id", "type", "category", "amount", "day"}.issubset(record):
                    raise AppError("반복 규칙 필수 필드가 없습니다.")
                rule = RecurringRule(**record)
                if rule.id in ids:
                    raise AppError("중복 규칙 id")
                ids.add(rule.id)
                rules.append(rule)
            except (ValueError, TypeError, AttributeError) as error:
                raise AppError(f"{self.path}:{line}: {error}. 백업으로 복구하세요.") from error
        return rules

    def save(self, rules: list[RecurringRule]) -> None:
        write_jsonl(self.path, (asdict(rule) for rule in rules))


class RecurringService:
    def __init__(self, service: "BudgetService") -> None:
        self.service = service
        self.store = RecurringStore(service.directory)

    def add(self, rule: RecurringRule) -> str:
        self.service.validate_category(rule.category)
        rules = self.store.load()
        rules.append(rule)
        self.store.save(rules)
        return rule.id

    def remove(self, rule_id: str) -> None:
        rules = self.store.load()
        remaining = [rule for rule in rules if rule.id != rule_id]
        if len(remaining) == len(rules):
            raise AppError(f"없는 반복 규칙: {rule_id}")
        self.store.save(remaining)

    def generate(self, month: str) -> tuple[int, int]:
        valid_month(month)
        rules = self.store.load()
        rule_ids = {rule.id for rule in rules}
        existing = set()
        for transaction in self.service.transactions.iter_transactions():
            if transaction.recurring_month == month and transaction.recurring_rule_id in rule_ids:
                existing.add(transaction.recurring_rule_id)
        year, month_number = map(int, month.split("-"))
        last_day = monthrange(year, month_number)[1]
        incoming = []
        skipped = 0
        for rule in rules:
            if rule.id in existing:
                skipped += 1
                continue
            self.service.validate_category(rule.category)
            day = min(rule.day, last_day)
            incoming.append(Transaction(date=f"{month}-{day:02d}", type=rule.type,
                                        category=rule.category, amount=rule.amount,
                                        memo=rule.memo, tags=rule.tags,
                                        recurring_rule_id=rule.id, recurring_month=month))
        # 별도 실행 이력 파일 없이 거래와 연결 필드를 한 번에 확정한다.
        self.service.transactions.merge(incoming)
        return len(incoming), skipped
