"""외부 교환용 CSV 계약."""
import csv
from pathlib import Path

from .models import AppError, Transaction, parse_tags, positive_int, valid_month
from .repository import atomic_text
from .service import BudgetService, validate_period

FIELDS = ["date", "type", "category", "amount", "memo", "tags"]


def import_csv(service: BudgetService, path: Path) -> int:
    incoming = []
    reader = None
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            headers = reader.fieldnames or []
            if not set(FIELDS[:4]).issubset(headers) or len(headers) != len(set(headers)):
                raise AppError("필수 헤더 date,type,category,amount가 없거나 중복 헤더입니다.")
            if set(headers) - set(FIELDS):
                raise AppError("알 수 없는 추가 컬럼은 허용하지 않습니다.")
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise AppError("헤더와 CSV 열 수가 다릅니다.")
                transaction = Transaction(date=row["date"], type=row["type"], category=row["category"],
                                          amount=positive_int(row["amount"]), memo=row.get("memo", ""),
                                          tags=parse_tags(row.get("tags", "")))
                service.validate_category(transaction.category)
                incoming.append(transaction)
        service.transactions.merge(incoming)
    except (AppError, csv.Error, UnicodeError, OSError) as error:
        line = reader.line_num if reader is not None else 0
        raise AppError(f"{path}: CSV 레코드 종료 물리줄 {line}: {error}; imported=0") from error
    return len(incoming)


def export_csv(service: BudgetService, path: Path, month: str | None = None,
               start: str | None = None, end: str | None = None) -> int:
    if month is not None:
        valid_month(month)
        if start is not None or end is not None:
            raise AppError("월과 기간 조건은 동시에 사용할 수 없습니다.")
    elif start is None and end is None:
        raise AppError("export에는 --month 또는 --from/--to 조건이 필요합니다.")
    validate_period(start, end)
    # 내부 파일로 내보내는 실수를 막는다. 반복 파일도 예약한다.
    for name in ("transactions", "categories", "budgets", "recurring"):
        if path.resolve() == (service.directory / f"{name}.jsonl").resolve():
            raise AppError("내부 저장 파일로 export할 수 없습니다.")
    count = 0
    with atomic_text(path) as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for transaction in service.search(start, end):
            if month is not None and transaction.date[:7] != month:
                continue
            writer.writerow({"date": transaction.date, "type": transaction.type,
                             "category": transaction.category, "amount": transaction.amount,
                             "memo": transaction.memo, "tags": ",".join(transaction.tags)})
            count += 1
    return count
