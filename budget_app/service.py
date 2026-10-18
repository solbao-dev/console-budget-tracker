"""가계부 업무 규칙. JSONL/CSV 세부 입출력은 별도 모듈에 위임."""
from dataclasses import replace
from pathlib import Path
from typing import Iterator

from .models import AppError, Transaction, category_name, positive_int, valid_date, valid_month
from .repository import BudgetStore, CategoryStore, TransactionRepository


class BudgetService:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.transactions = TransactionRepository(directory)
        self.categories = CategoryStore(directory)
        self.budgets = BudgetStore(directory)
        from .recurring import RecurringStore
        self.recurring = RecurringStore(directory)

    def validate_category(self, name: str) -> None:
        if name not in self.categories.load():
            raise AppError(f"등록되지 않은 카테고리: {name}. category add로 먼저 등록하세요.")

    def add(self, transaction: Transaction) -> str:
        self.validate_category(transaction.category)
        self.transactions.merge([transaction])
        return transaction.id

    def find(self, transaction_id: str) -> Transaction:
        found = None
        # 변경 전 전체 파일을 검사해 뒤쪽 손상도 놓치지 않는다.
        for transaction in self.transactions.iter_transactions():
            if transaction.id == transaction_id:
                found = transaction
        if found is None:
            raise AppError(f"없는 데이터: {transaction_id}")
        return found

    def update(self, transaction_id: str, changes: dict) -> None:
        if not changes:
            raise AppError("수정할 필드를 하나 이상 지정하세요.")
        transaction = replace(self.find(transaction_id), **changes)
        self.validate_category(transaction.category)
        self.transactions.merge([transaction], transaction_id)

    def delete(self, transaction_id: str) -> None:
        self.transactions.merge([], transaction_id)

    def search(self, start: str | None = None, end: str | None = None,
               category: str | None = None, kind: str | None = None,
               query: str | None = None, tag: str | None = None) -> Iterator[Transaction]:
        validate_period(start, end)
        if category is not None:
            self.validate_category(category)
        if kind is not None and kind not in ("income", "expense"):
            raise AppError("type은 income 또는 expense여야 합니다.")
        for transaction in self.transactions.iter_transactions():
            if start and transaction.date < start:
                continue
            if end and transaction.date > end:
                continue
            if category is not None and transaction.category != category:
                continue
            if kind is not None and transaction.type != kind:
                continue
            if query is not None and query not in transaction.memo:
                continue
            if tag is not None and tag not in transaction.tags:
                continue
            yield transaction

    def summary(self, month: str, top: int) -> dict:
        valid_month(month)
        positive_int(top)
        income = expense = count = 0
        categories = {}
        for transaction in self.transactions.iter_transactions():
            if transaction.date[:7] != month:
                continue
            count += 1
            if transaction.type == "income":
                income += transaction.amount
            else:
                expense += transaction.amount
                categories[transaction.category] = categories.get(transaction.category, 0) + transaction.amount
        return {"income": income, "expense": expense, "balance": income - expense,
                "count": count, "top": sorted(categories.items(), key=lambda item: (-item[1], item[0]))[:top],
                "budget": self.budgets.load().get(month)}

    def category_add(self, name: str) -> None:
        name = category_name(name)
        names = self.categories.load()
        if name in names:
            raise AppError("이미 등록된 카테고리입니다.")
        names.append(name)
        self.categories.save(names)

    def category_remove(self, name: str) -> None:
        name = category_name(name)
        names = self.categories.load()
        if name not in names:
            raise AppError("없는 카테고리입니다.")
        if any(transaction.category == name for transaction in self.transactions.iter_transactions()):
            raise AppError("사용 중인 카테고리는 삭제할 수 없습니다.")
        if any(rule.category == name for rule in self.recurring.load()):
            raise AppError("활성 반복 규칙에서 사용 중인 카테고리는 삭제할 수 없습니다.")
        names.remove(name)
        self.categories.save(names)


def validate_period(start: str | None, end: str | None) -> None:
    if start is not None:
        valid_date(start)
    if end is not None:
        valid_date(end)
    if start is not None and end is not None and start > end:
        raise AppError("시작일이 종료일보다 늦습니다.")
