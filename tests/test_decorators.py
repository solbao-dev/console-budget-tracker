"""실행 기록이 반환값과 오류 처리 동작을 바꾸지 않는지 검증한다."""
import contextlib
import io
import unittest
from unittest.mock import patch

from budget_app.decorators import handle_errors, log_execution, measure_time
from budget_app.models import AppError


class DecoratorTests(unittest.TestCase):
    def test_timing_preserves_arguments_result_and_metadata(self) -> None:
        @measure_time
        def command(value: int, *, extra: int) -> int:
            """시간 측정 후에도 원래 함수 설명을 보존한다."""
            return value + extra

        output = io.StringIO()
        with patch("budget_app.decorators.perf_counter", side_effect=[10.0, 10.25]):
            with contextlib.redirect_stderr(output):
                self.assertEqual(command(2, extra=3), 5)
        self.assertEqual(command.__name__, "command")
        self.assertEqual(command.__doc__, command.__wrapped__.__doc__)
        self.assertEqual(output.getvalue(), "[시간] command: 0.250초\n")

    def test_timing_runs_on_exception_and_help_exit(self) -> None:
        for error in (RuntimeError("unexpected"), SystemExit(0)):
            with self.subTest(error=type(error).__name__):
                @measure_time
                def command() -> int:
                    raise error

                output = io.StringIO()
                with patch("budget_app.decorators.perf_counter", side_effect=[5.0, 5.5]):
                    with contextlib.redirect_stderr(output):
                        with self.assertRaises(type(error)) as caught:
                            command()
                self.assertIs(caught.exception, error)
                self.assertIn("0.500초", output.getvalue())

    def test_stacked_decorators_report_failure_in_order(self) -> None:
        @log_execution
        @measure_time
        @handle_errors
        def command() -> int:
            raise AppError("잘못된 입력")

        output = io.StringIO()
        with patch("budget_app.decorators.perf_counter", side_effect=[1.0, 1.1]):
            with contextlib.redirect_stderr(output):
                self.assertEqual(command(), 1)
        lines = output.getvalue().splitlines()
        self.assertTrue(lines[0].startswith("[실행] command 시작"))
        self.assertTrue(lines[1].startswith("[오류]"))
        self.assertTrue(lines[2].startswith("[힌트]"))
        self.assertEqual(lines[3], "[시간] command: 0.100초")
        self.assertIn("종료 코드: 1", lines[4])

    def test_logging_preserves_arguments_result_and_metadata(self) -> None:
        @log_execution
        def command(value: int, *, extra: int) -> int:
            """설명 보존 확인."""
            return value + extra

        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            self.assertEqual(command(2, extra=3), 5)
        self.assertEqual(command.__name__, "command")
        self.assertEqual(command.__doc__, "설명 보존 확인.")
        self.assertIn("command 시작", output.getvalue())
        self.assertIn("종료 코드: 5", output.getvalue())

    def test_logging_reports_handled_failure_without_input_values(self) -> None:
        @log_execution
        @handle_errors
        def command(secret: str) -> int:
            raise AppError("잘못된 입력")

        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            self.assertEqual(command("private-memo"), 1)
        self.assertIn("[오류]", output.getvalue())
        self.assertIn("종료 코드: 1", output.getvalue())
        self.assertNotIn("private-memo", output.getvalue())

    def test_logging_preserves_help_exit_and_unexpected_error(self) -> None:
        @log_execution
        def help_command() -> int:
            raise SystemExit(0)

        @log_execution
        def broken_command() -> int:
            raise RuntimeError("unexpected")

        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            with self.assertRaises(SystemExit) as caught:
                help_command()
            self.assertEqual(caught.exception.code, 0)
            with self.assertRaises(RuntimeError):
                broken_command()
        self.assertIn("종료 코드: 0", output.getvalue())
        self.assertIn("예외로 종료", output.getvalue())
