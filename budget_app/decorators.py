"""CLI 실행 기록, 시간 측정, 사용자용 오류 처리를 각각 분리한다."""
import csv
import sys
from functools import wraps
from time import perf_counter
from typing import Callable

from .models import AppError


def log_execution(function: Callable[..., int]) -> Callable[..., int]:
    """함수 시작과 종료 결과를 stderr에 기록한다. 입력 데이터는 기록하지 않는다."""
    @wraps(function)
    def wrapper(*args: object, **kwargs: object) -> int:
        print(f"[실행] {function.__name__} 시작", file=sys.stderr)
        try:
            result = function(*args, **kwargs)
        except SystemExit as error:
            # argparse의 --help는 정상적으로 SystemExit(0)을 발생시킨다.
            print(f"[실행] {function.__name__} 종료 (종료 코드: {error.code})", file=sys.stderr)
            raise
        except BaseException:
            # 기록만 남기고 오류는 그대로 전달한다. 오류 변환은 handle_errors의 책임이다.
            print(f"[실행] {function.__name__} 예외로 종료", file=sys.stderr)
            raise
        print(f"[실행] {function.__name__} 종료 (종료 코드: {result})", file=sys.stderr)
        return result
    return wrapper


def measure_time(function: Callable[..., int]) -> Callable[..., int]:
    """성공/실패와 관계없이 경과 시간을 stderr에 출력한다."""
    @wraps(function)
    def wrapper(*args: object, **kwargs: object) -> int:
        started = perf_counter()
        try:
            return function(*args, **kwargs)
        finally:
            # return 또는 예외로 함수를 나가더라도 finally는 실행된다.
            elapsed = perf_counter() - started
            print(f"[시간] {function.__name__}: {elapsed:.3f}초", file=sys.stderr)
    return wrapper


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
