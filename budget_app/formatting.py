"""고정 표시 폭 테이블: 조회 행을 모으지 않고 하나씩 출력."""
from typing import Iterable
import unicodedata

from .models import Transaction


def display_width(value: str) -> int:
    width = 0
    for char in value:
        if unicodedata.combining(char):
            continue
        width += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
    return width


def cell(value: object, width: int) -> str:
    cleaned = ""
    for char in str(value):
        if unicodedata.category(char).startswith("C") or char in "\r\n\t":
            cleaned += " "
        else:
            cleaned += char
    if display_width(cleaned) > width:
        shortened = ""
        for char in cleaned:
            if display_width(shortened + char) > width - 1:
                break
            shortened += char
        cleaned = shortened + "…"
    return cleaned + " " * max(0, width - display_width(cleaned))


def print_transactions(transactions: Iterable[Transaction]) -> None:
    widths = (36, 10, 7, 14, 12, 24, 18)
    headers = ("id", "날짜", "type", "카테고리", "금액", "메모", "태그")
    print(" | ".join(cell(value, width) for value, width in zip(headers, widths)))
    count = 0
    for transaction in transactions:
        values = (transaction.id, transaction.date, transaction.type, transaction.category,
                  transaction.amount, transaction.memo, ",".join(transaction.tags))
        print(" | ".join(cell(value, width) for value, width in zip(values, widths)))
        count += 1
    if count == 0:
        print("데이터 없음")
