"""사용자 입력, 옵션 해석, 결과 출력."""
import argparse
from itertools import islice
from pathlib import Path

from .decorators import handle_errors, log_execution, measure_time
from .backup import create_backup
from .exchange import export_csv, import_csv
from .formatting import print_transactions
from .models import AppError, Transaction, parse_tags, positive_int
from .recurring import RecurringRule, RecurringService
from .service import BudgetService


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise AppError(f"옵션 오류: {message}")


def build_parser() -> argparse.ArgumentParser:
    parser = Parser(description="나만의 용돈 기입장")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("add", help="대화형 거래 추가")
    listing = commands.add_parser("list", help="최신순 목록")
    listing.add_argument("--limit", default="10")
    search = commands.add_parser("search", help="AND 조건 검색")
    for name in ("from", "to", "category", "type", "q", "tag"):
        search.add_argument("--" + name, dest="start" if name == "from" else "end" if name == "to" else name)
    summary = commands.add_parser("summary")
    summary.add_argument("--month", required=True)
    summary.add_argument("--top", default="3")
    budget = commands.add_parser("budget").add_subparsers(dest="action", required=True)
    for name in ("set", "get"):
        child = budget.add_parser(name)
        child.add_argument("--month", required=True)
        if name == "set":
            child.add_argument("--amount", required=True)
    category = commands.add_parser("category").add_subparsers(dest="action", required=True)
    for name in ("add", "list", "remove"):
        category.add_parser(name)
    update = commands.add_parser("update")
    update.add_argument("--id", required=True)
    for name in ("date", "type", "category", "amount", "memo", "tags"):
        update.add_argument("--" + name)
    deletion = commands.add_parser("delete")
    deletion.add_argument("--id", required=True)
    importing = commands.add_parser("import")
    importing.add_argument("--from", dest="source", required=True, type=Path)
    exporting = commands.add_parser("export")
    exporting.add_argument("--out", required=True, type=Path)
    exporting.add_argument("--month")
    exporting.add_argument("--from", dest="start")
    exporting.add_argument("--to", dest="end")
    backup = commands.add_parser("backup", help="타임스탬프 ZIP 백업")
    backup.add_argument("--out-dir", required=True, type=Path)
    recurring = commands.add_parser("recurring", help="월 반복 내역").add_subparsers(dest="action", required=True)
    recurring.add_parser("add")
    recurring.add_parser("list")
    removing = recurring.add_parser("remove")
    removing.add_argument("--id", required=True)
    generating = recurring.add_parser("generate")
    generating.add_argument("--month", required=True)
    return parser


def input_transaction() -> Transaction:
    day = input("날짜(YYYY-MM-DD): ").strip()
    kind = input("타입(income/expense): ").strip()
    category = input("카테고리: ").strip()
    amount = positive_int(input("금액(양수 정수): "))
    memo = input("메모(선택): ")
    tags = parse_tags(input("태그(쉼표 구분): "))
    return Transaction(date=day, type=kind, category=category, amount=amount, memo=memo, tags=tags)


def input_rule() -> RecurringRule:
    kind = input("타입(income/expense): ").strip()
    category = input("카테고리: ").strip()
    amount = positive_int(input("금액: "))
    day = positive_int(input("매월 일자(1~31): "))
    memo = input("메모: ")
    tags = parse_tags(input("태그(쉼표 구분): "))
    return RecurringRule(type=kind, category=category, amount=amount, day=day, memo=memo, tags=tags)


@log_execution
@measure_time
@handle_errors
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service = BudgetService(args.data_dir)
    command = args.command
    if command == "add":
        print(f"[저장 완료] id={service.add(input_transaction())}")
    elif command == "list":
        print_transactions(islice(service.transactions.iter_transactions(), positive_int(args.limit)))
    elif command == "search":
        print_transactions(service.search(args.start, args.end, args.category, args.type, args.q, args.tag))
    elif command == "summary":
        result = service.summary(args.month, positive_int(args.top))
        if not result["count"]:
            print("데이터 없음")
        print(f"총 수입: {result['income']}원\n총 지출: {result['expense']}원\n잔액: {result['balance']}원")
        if result["budget"] is not None:
            print(f"예산: {result['budget']}원 (사용률 {result['expense'] / result['budget'] * 100:.1f}%)")
            if result["expense"] > result["budget"]:
                print("[경고] 예산 초과")
        for category, amount in result["top"]:
            print(f"{category}: {amount}원")
    elif command == "budget":
        from .models import valid_month
        month = valid_month(args.month)
        if args.action == "set":
            service.budgets.set(month, positive_int(args.amount))
            print("[저장 완료] 예산")
        else:
            print(f"예산: {service.budgets.load().get(month, '미설정')}")
    elif command == "category":
        if args.action == "list":
            for name in service.categories.load():
                print(name)
        elif args.action == "add":
            service.category_add(input("카테고리명: "))
            print("[저장 완료] category")
        else:
            service.category_remove(input("카테고리명: "))
            print("[삭제 완료] category")
    elif command == "update":
        changes = {}
        for name in ("date", "type", "category", "amount", "memo", "tags"):
            value = getattr(args, name)
            if value is not None:
                if name == "amount":
                    value = positive_int(value)
                elif name == "tags":
                    value = parse_tags(value)
                changes[name] = value
        service.update(args.id, changes)
        print("[수정 완료]")
    elif command == "delete":
        service.delete(args.id)
        print("[삭제 완료]")
    elif command == "import":
        print(f"[완료] imported={import_csv(service, args.source)}, skipped=0")
    elif command == "export":
        print(f"[완료] {args.out} ({export_csv(service, args.out, args.month, args.start, args.end)} records)")
    elif command == "backup":
        print(f"[백업 완료] {create_backup(service.directory, args.out_dir)}")
    elif command == "recurring":
        recurring = RecurringService(service)
        if args.action == "add":
            print(f"[저장 완료] rule_id={recurring.add(input_rule())}")
        elif args.action == "list":
            rules = recurring.store.load()
            if not rules:
                print("데이터 없음")
            for rule in rules:
                print(f"{rule.id} | {rule.type} | {rule.category} | {rule.amount} | 매월 {rule.day}일")
        elif args.action == "remove":
            recurring.remove(args.id)
            print("[삭제 완료] 반복 규칙 (기존 거래 유지)")
        else:
            generated, skipped = recurring.generate(args.month)
            print(f"[완료] generated={generated}, skipped={skipped}")
    return 0
