"""CLI 경계에서 예상 가능한 실패를 사용자 메시지와 종료 코드로 변환."""
import csv
import sys
from functools import wraps
from typing import Callable

from .models import AppError


def handle_errors(function: Callable[..., int]) -> Callable[..., int]:
    @wraps(function)
    def wrapper(*args: object, **kwargs: object) -> int:
        try:
            return function(*args, **kwargs)
        except (AppError, OSError, UnicodeError, csv.Error, EOFError, KeyboardInterrupt) as error:
            reason = str(error) or "입력이 끝났거나 사용자가 취소했습니다."
            print(f"[오류] {reason}", file=sys.stderr)
            print("[힌트] --help로 입력 형식과 경로/권한을 확인하세요. 저장 파일 손상은 백업과 비교해 복구하세요.", file=sys.stderr)
            return 1
    return wrapper
