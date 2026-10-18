"""거래 구조와 실행 시 입력 검증."""
from dataclasses import dataclass, field
from datetime import date
import re
from uuid import uuid4


class AppError(ValueError):
    """사용자가 입력이나 파일을 고쳐 해결할 수 있는 오류."""


def valid_date(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise AppError("날짜는 YYYY-MM-DD 형식이어야 합니다.")
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise AppError("실제로 존재하는 날짜를 입력하세요.") from error
    return value


def valid_month(value: str) -> str:
    if not isinstance(value, str):
        raise AppError("월은 YYYY-MM 문자열이어야 합니다.")
    valid_date(value + "-01")
    return value


def positive_int(value: object) -> int:
    # bool은 int의 하위 타입이므로 정확한 타입을 확인한다.
    if type(value) is int and value > 0:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
        try:
            number = int(value)
        except ValueError as error:
            raise AppError("정수가 너무 큽니다. 더 짧은 숫자를 입력하세요.") from error
        if number > 0:
            return number
    raise AppError("금액/개수는 0보다 큰 정수여야 합니다 (bool, 소수 불가).")


def valid_type(value: str) -> str:
    if value not in ("income", "expense"):
        raise AppError("type은 income 또는 expense여야 합니다.")
    return value


def category_name(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AppError("카테고리 이름은 비어 있을 수 없습니다.")
    if any(ord(char) < 32 for char in value):
        raise AppError("카테고리에 제어문자를 사용할 수 없습니다.")
    return value.strip()


def parse_tags(value: str) -> list[str]:
    return [tag.strip() for tag in value.split(",") if tag.strip()]


@dataclass
class Transaction:
    date: str
    type: str
    category: str
    amount: int
    memo: str = ""
    tags: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid4()))
    recurring_rule_id: str | None = None
    recurring_month: str | None = None

    def __post_init__(self) -> None:
        valid_date(self.date)
        valid_type(self.type)
        if type(self.amount) is not int:
            raise AppError("저장 금액은 정수여야 합니다.")
        positive_int(self.amount)
        if category_name(self.category) != self.category:
            raise AppError("카테고리 앞뒤 공백을 제거하세요.")
        if not isinstance(self.id, str) or not self.id.strip():
            raise AppError("거래 id는 비어 있지 않은 문자열이어야 합니다.")
        if not isinstance(self.memo, str) or not isinstance(self.tags, list):
            raise AppError("메모는 문자열, tags는 문자열 목록이어야 합니다.")
        if any(not isinstance(tag, str) or not tag.strip() or "," in tag for tag in self.tags):
            raise AppError("태그는 비어 있지 않고 쉼표를 포함하지 않는 문자열이어야 합니다.")
        if (self.recurring_rule_id is None) != (self.recurring_month is None):
            raise AppError("반복 연결 필드는 함께 있어야 합니다.")
        if self.recurring_month is not None:
            valid_month(self.recurring_month)
            if not isinstance(self.recurring_rule_id, str) or not self.recurring_rule_id:
                raise AppError("반복 규칙 id가 잘못되었습니다.")

    def sort_key(self) -> tuple[str, str]:
        return self.date, self.id
