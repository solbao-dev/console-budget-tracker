"""JSONL 저장과 순차 병합. 사용자 입출력이나 업무 계산은 하지 않는다."""
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, Iterator, TextIO
import json
import os
import tempfile

from .models import AppError, Transaction, category_name, positive_int, valid_month


@contextmanager
def atomic_text(path: Path) -> Iterator[TextIO]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                         dir=path.parent, prefix=".cashbook-", delete=False) as handle:
            temporary = Path(handle.name)
            yield handle
            handle.flush()
            os.fsync(handle.fileno())
        # 소비한 원본 제너레이터와 출력 핸들을 모두 닫은 뒤 교체한다.
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def read_jsonl(path: Path) -> Iterator[tuple[int, dict]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise AppError("JSON 객체가 아닙니다.")
            except (ValueError, TypeError) as error:
                raise AppError(f"{path}:{line_number}: {error}. 백업과 비교해 복구하세요.") from error
            yield line_number, record


def write_jsonl(path: Path, records: Iterable[dict]) -> None:
    with atomic_text(path) as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


class TransactionRepository:
    def __init__(self, directory: Path) -> None:
        self.path = directory / "transactions.jsonl"
        if not self.path.exists():
            write_jsonl(self.path, ())

    def iter_transactions(self) -> Iterator[Transaction]:
        previous = None
        for line, record in read_jsonl(self.path):
            try:
                if not {"id", "date", "type", "category", "amount"}.issubset(record):
                    raise AppError("거래 필수 필드(id/date/type/category/amount)가 없습니다.")
                transaction = Transaction(**record)
                key = transaction.sort_key()
                if previous is not None and key >= previous:
                    raise AppError("날짜/id 내림차순 위반 또는 중복 정렬 키")
                previous = key
            except (ValueError, TypeError, AttributeError) as error:
                raise AppError(f"{self.path}:{line}: {error}. 백업과 비교해 복구하세요.") from error
            yield transaction

    def merge(self, incoming: list[Transaction], remove_id: str | None = None) -> None:
        incoming = sorted(incoming, key=Transaction.sort_key, reverse=True)

        def merged_records() -> Iterator[dict]:
            index = 0
            found = False
            for old in self.iter_transactions():
                if old.id == remove_id:
                    found = True
                    continue
                while index < len(incoming) and incoming[index].sort_key() > old.sort_key():
                    yield asdict(incoming[index])
                    index += 1
                yield asdict(old)
            if remove_id is not None and not found:
                raise AppError(f"없는 데이터: {remove_id}")
            for new in incoming[index:]:
                yield asdict(new)

        write_jsonl(self.path, merged_records())


class CategoryStore:
    def __init__(self, directory: Path) -> None:
        self.path = directory / "categories.jsonl"
        if not self.path.exists() or self.path.stat().st_size == 0:
            self.save(["food", "transport", "rent", "salary", "etc"])

    def load(self) -> list[str]:
        names = []
        for line, record in read_jsonl(self.path):
            try:
                if set(record) != {"name"}:
                    raise AppError("name 필드가 필요합니다.")
                name = category_name(record["name"])
                if name != record["name"] or name in names:
                    raise AppError("중복 또는 공백이 있는 카테고리")
                names.append(name)
            except (ValueError, TypeError) as error:
                raise AppError(f"{self.path}:{line}: {error}. 백업으로 복구하세요.") from error
        return names

    def save(self, names: list[str]) -> None:
        write_jsonl(self.path, ({"name": name} for name in names))


class BudgetStore:
    def __init__(self, directory: Path) -> None:
        self.path = directory / "budgets.jsonl"
        if not self.path.exists():
            write_jsonl(self.path, ())

    def load(self) -> dict[str, int]:
        budgets = {}
        for line, record in read_jsonl(self.path):
            try:
                if set(record) != {"month", "amount"} or type(record["amount"]) is not int:
                    raise AppError("month/정수 amount 필드를 확인하세요.")
                month = valid_month(record["month"])
                if month in budgets:
                    raise AppError("중복 월")
                budgets[month] = positive_int(record["amount"])
            except (ValueError, TypeError) as error:
                raise AppError(f"{self.path}:{line}: {error}. 백업으로 복구하세요.") from error
        return budgets

    def set(self, month: str, amount: int) -> None:
        budgets = self.load()
        budgets[valid_month(month)] = positive_int(amount)
        write_jsonl(self.path, ({"month": key, "amount": value} for key, value in sorted(budgets.items())))
