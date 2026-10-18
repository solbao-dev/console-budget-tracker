# 나만의 용돈 기입장

Python 3.10 이상, 표준 라이브러리만 사용하는 한국어 콘솔 가계부입니다. 거래 관리·검색·월별 요약·CSV 교환에 더해 백업, 반복 내역, 출력 포맷 테이블 정렬, 저장 원자성 강화를 구현했습니다. 외부 패키지 설치 없이 실행할 수 있습니다.

## 실행 환경과 첫 실행

프로젝트 폴더에서 아래 명령을 실행하세요. Windows / Python 3.14.5에서 검증합니다. `--help`는 저장 파일을 만들지 않습니다.

```powershell
python -m budget_app --help
python -m budget_app --data-dir ./demo_data import --from ./examples/import_sample.csv
python -m budget_app --data-dir ./demo_data summary --month 2026-10
```

새 연습 폴더라면 imported=4, 총 수입 100000원 / 총 지출 23000원 / 잔액 77000원입니다. 같은 CSV를 다시 가져오면 새로운 id로 중복 거래가 생깁니다. 연습은 `demo_data`, 실제 사용은 기본 `data`로 구분하세요. `--data-dir`는 **명령 앞**에 씁니다. 경로 기준은 현재 작업 폴더입니다.

## 전체 명령

아래 `python -m budget_app` 뒤에 각 명령을 붙입니다. 모든 명령·하위명령에 `--help`가 있습니다.

| 명령 예 | 동작 |
| --- | --- |
| `add` | 날짜 → income/expense → 등록 카테고리 → 양수 정수 금액 → 메모 → 쉼표 구분 태그를 input으로 입력, id 출력 |
| `list --limit 4` | 기본 10, 양수 개수만 허용, 날짜/id 내림차순 |
| `search --from 2026-10-01 --to 2026-10-31 --category food --type expense --q 점심 --tag 친구` | 모든 조건 AND, 양끝 포함, 메모 부분 문자열(대소문자 구분), 태그 정확 일치 |
| `summary --month 2026-10 --top 3` | 수입/지출/잔액, 지출 TOP(기본 3), 예산 사용률·초과 경고; 빈 달도 표시 |
| `budget set --month 2026-10 --amount 20000` | 월 예산 저장 |
| `budget get --month 2026-10` | 설정 금액 또는 미설정 |
| `category add` / `category list` / `category remove` | 추가·삭제 이름은 대화형, 거래/활성 반복 규칙에서 사용 중이면 삭제 차단 |
| `update --id ID --date 2026-10-12 --amount 7000 --memo "수정" --tags "식사,친구"` | **옵션 방식으로 고정**; date/type/category/amount/memo/tags 중 최소 하나; 전체 거래 재검증 |
| `update --id ID --memo= --tags=` | 메모·태그 비우기 |
| `delete --id ID` | 없는 id는 실패 |
| `import --from ./examples/import_sample.csv` | 전수 검증 뒤 일괄 반영, 처리 건수 출력 |
| `export --out ./demo_export.csv --month 2026-10` | 월별 CSV |
| `export --out ./demo_export.csv --from 2026-10-01 --to 2026-10-31` | 기간별 CSV; 한쪽만 주는 열린 구간 허용; 월+기간 동시 사용 거부 |
| `backup --out-dir ./backups` | 타임스탬프+UUID ZIP 경로 출력 |
| `recurring add` | type/category/amount/day(1~31)/memo/tags 순서 대화형 |
| `recurring list` | 규칙 id와 내용 |
| `recurring remove --id RULE_ID` | 규칙만 삭제, 기존 생성 거래 유지 |
| `recurring generate --month 2026-10` | 월말 보정 후 generated/skipped 건수; 백그라운드 실행 없음 |

명령의 `ID`와 `RULE_ID`는 추가 또는 조회 결과에 나온 실제 식별자로 바꿉니다. 메모·태그를 비울 때는 `--memo= --tags=`로 빈 값을 명시할 수 있습니다.

잘못된 입력은 원인+힌트를 출력하고 종료 코드 1을 반환합니다. 성공은 0, argparse의 `--help` 정상 종료도 0입니다. PowerShell에서는 실행 직후 `$LASTEXITCODE`로 확인합니다. 사용자 입력 취소/EOF도 실패 처리합니다. 예상 밖 프로그래밍 오류까지 숨기는 포괄적인 except는 사용하지 않았습니다.

## 공통 기능을 분리한 데코레이터

`decorators.py`에 실행 기록·시간 측정·오류 처리를 각각 별도 함수로 구현하고 `cli.py`의 `main`에 적용했습니다.

```python
@log_execution
@measure_time
@handle_errors
def main(argv: list[str] | None = None) -> int:
    ...
```

- `log_execution`: 명령 실행의 시작과 종료 코드(성공 0 / 실패 1)를 stderr에 기록합니다. 입력 인자나 거래 메모는 로그에 남기지 않습니다.
- `measure_time`: `perf_counter()`로 시작과 종료 시점의 차이를 계산해 stderr에 초 단위로 출력합니다. `finally`에서 출력하므로 오류나 `--help` 종료에도 측정 결과가 남습니다. 반환값과 예외는 그대로 전달합니다.
- `handle_errors`: 예상 가능한 입력·파일 오류를 원인과 해결 힌트로 안내하고 실패 코드 1을 반환합니다.

실행 순서는 `실행 시작 기록 → 측정 시작 → 오류 처리로 감싼 main → 경과 시간 출력 → 종료 결과 기록`입니다. 오류 안내 형식·실행 기록·시간 측정을 독립적으로 바꿀 수 있도록 책임을 분리했습니다. `--help`의 정상 종료와 예상 밖 오류도 원래 동작을 유지합니다. 거래 목록 등 결과는 stdout에, 실행 기록·경과 시간·오류 안내는 stderr에 출력합니다. 실행 기록은 파일로 영구 저장하지 않습니다.

측정값은 main 전체의 경과 시간으로, 대화형 명령에서는 사용자가 입력을 기다리는 시간도 포함합니다. 저장 함수만의 처리 시간이나 CPU 사용 시간은 아닙니다. 파일이 작은 명령은 소수점 셋째 자리로 반올림되어 `0.000초`로 표시될 수 있습니다.

예: `python -m budget_app --help` 실행 시 도움말과 함께 `[실행] main 시작`, `[시간] main: 0.012초`, `[실행] main 종료 (종료 코드: 0)`이 표시됩니다. 시간 값은 실행마다 달라집니다.

## 파일 구조와 책임

| 파일 | 책임 |
| --- | --- |
| `budget_app/__main__.py` | CLI 반환값을 프로세스 종료 코드로 연결 |
| `models.py` | Transaction dataclass, 날짜/월/금액 검증, 태그 변환 |
| `cli.py` | argparse, input, 명령 연결과 결과 출력 |
| `service.py` | BudgetService의 CRUD/검색/요약/카테고리 사용 규칙 |
| `repository.py` | TransactionRepository/CategoryStore/BudgetStore, JSONL I/O, 병합과 교체 |
| `exchange.py` | CSV import/export, UTF-8·헤더·인용 규칙 |
| `decorators.py` | main에 적용하는 실행 기록·시간 측정·오류 처리 데코레이터와 wraps |
| `backup.py` / `formatting.py` / `recurring.py` | 보너스 전용 처리 |
| `tests/` | tempfile·unittest·subprocess·실패 주입 검증 |

## 저장 형식과 정책

내부는 UTF-8 **JSONL**(한 줄 JSON 객체), 외부 교환만 CSV입니다. 첫 명령에서 디렉터리와 거래·카테고리·예산·반복 파일을 만듭니다. 카테고리 파일이 없거나 0바이트면 food, transport, rent, salary, etc를 채웁니다. 마지막 카테고리를 삭제해 비게 되면 다음 실행에서 기본값이 다시 생깁니다. 빈 줄만 있는 파일은 빈 파일 정책이 아니라 손상으로 처리합니다.

```jsonl
{"date":"2026-10-02","type":"expense","category":"food","amount":15000,"memo":"점심","tags":["식사","친구"],"id":"UUID문자열","recurring_rule_id":null,"recurring_month":null}
```

위는 `transactions.jsonl` 한 줄입니다. 예시 id는 설명용이며 실제 추가는 uuid4 문자열입니다. 금액은 소수/0/음수/bool을 거부하는 양수 정수입니다. id는 거래 식별자이며 날짜 동률일 때의 순서를 결정합니다. **추가 시각 순서가 아닙니다.** 저장소가 `(date, id)` 내림차순을 유지하므로 list/search는 전체 거래 리스트나 전체 정렬 없이 한 줄씩 읽습니다.

```jsonl
{"name":"food"}
```

`categories.jsonl`은 이름당 한 줄입니다.

```jsonl
{"month":"2026-10","amount":20000}
```

`budgets.jsonl`은 월당 한 줄입니다.

```jsonl
{"type":"expense","category":"rent","amount":50000,"day":31,"memo":"월세","tags":["고정"],"id":"규칙UUID"}
```

`recurring.jsonl`은 규칙당 한 줄입니다. 생성 거래에는 `recurring_rule_id`와 `recurring_month`가 함께 저장됩니다. 같은 규칙·월이면 재생성을 건너뜁니다. 생성 거래를 수정해 날짜를 옮겨도 연결은 보존합니다. 거래를 삭제한 뒤 generate하면 다시 생성합니다. 규칙을 편집하는 명령은 없으며 직접 파일 변경은 권장하지 않습니다. 규칙을 삭제·새로 등록하면 새 id가 부여되고 기존 거래는 자동 변경되지 않습니다.

손상된 JSON/필드/정렬 위반은 경로·행·복구 안내와 함께 실패합니다. 변경 작업은 기존 거래 끝까지 읽으며 검사합니다. `list --limit 1`처럼 조기 종료하면 뒤쪽 손상까지 검사하지 않습니다. 수작업으로 id를 바꾸거나 파일을 편집해 생기는 모든 무결성 위반을 검출하는 데이터베이스는 아닙니다.

## CSV 계약

UTF-8, 헤더 포함. 입력 UTF-8 BOM도 허용합니다. 필수 컬럼은 date,type,category,amount이며 memo/tags는 생략 가능합니다. 추가 컬럼·중복 헤더·열 수 불일치는 거부합니다. 입력 헤더 순서는 자유, 출력 순서는 다음과 같습니다.

```csv
date,type,category,amount,memo,tags
2026-10-02,expense,food,15000,"점심, 친구","식사,친구"
```

CSV 행은 csv 모듈이 해석합니다. 쉼표 split은 태그 **셀 내부**에만 사용합니다. 메모의 쉼표·따옴표·한글·줄바꿈을 보존합니다. 태그는 앞뒤 공백 제거/빈 항목 제거하며 태그 하나 안에 쉼표는 허용하지 않습니다.

import는 입력 묶음 전체를 검증·정렬하고 기존 파일과 순차 병합해 한 번 교체합니다. 실패하면 imported=0과 CSV 레코드 종료 물리줄을 표시하며 거래 원본은 유지됩니다. 한 레코드가 여러 물리줄을 차지할 수 있습니다. 파일 열기/헤더 오류는 0 또는 헤더 위치입니다. 재수입은 새 id를 발급하므로 중복입니다. 반복 연결 메타데이터는 원본 CSV 스키마에 없어서 왕복 시 사라집니다. 재수입 행은 반복 중복 방지 대상이 아닙니다. export는 기간 조건 필수이고 내부 저장 파일 덮어쓰기를 거부하며 기존 출력 파일도 교체 실패 시 보존합니다.

## 입력 검증과 전체 반영 정책

이 과제의 중심은 “예외 상황에서도 데이터가 안전한 작은 서비스”입니다. 따라서 잘못된 행만 건너뛰는 부분 성공 대신 **한 명령의 입력을 모두 검증한 뒤 전부 반영하거나, 오류가 하나라도 있으면 해당 명령의 변경을 전혀 반영하지 않는 정책**을 선택했습니다.

- **CSV 10건 중 1건 오류:** 먼저 모든 행의 날짜·타입·금액·카테고리·CSV 구조를 검증합니다. 마지막 행에 오류가 있어도 앞의 정상 9건을 저장하지 않습니다. 오류 위치와 이유, `imported=0`을 알리고 기존 거래 파일은 유지합니다.
- **거래 추가·수정:** 필수 값과 업무 규칙 검증이 끝나기 전에는 저장하지 않습니다. 수정 값 중 하나라도 잘못되면 기존 거래 전체를 유지합니다.
- **반복 거래 일괄 생성:** 생성 대상 규칙과 거래를 준비한 뒤 한 번에 반영합니다. 준비 또는 저장 과정에서 실패하면 이번 명령에서 생성하려던 거래를 모두 반영하지 않습니다. 이미 생성된 규칙을 `skipped`로 표시하는 것은 오류 행의 부분 성공이 아니라 중복 생성 방지입니다.
- **저장 실패:** 검증을 통과해도 임시 파일 쓰기나 교체가 실패하면 기존 파일을 유지합니다. 입력 검증은 잘못된 데이터를 막고, 원자적 교체는 저장 중 실패에 대비합니다.

일부만 반영되면 사용자가 원래 의도한 묶음과 실제 저장 내용이 달라져 누락을 알아채기 어렵습니다. 수정 후 재시도할 때 앞서 저장된 행이 중복될 수도 있습니다. 전체 반영 정책은 오류를 고쳐 다시 제출해야 하는 비용이 있지만, 이번 요청이 반영됐는지 명확하게 판단할 수 있어 데이터 무결성과 사용자 신뢰를 우선한다는 미션에 맞습니다.

이 정책의 단위는 **한 명령의 데이터 변경**입니다. 앞서 성공한 별도 명령까지 되돌리는 정책은 아닙니다. 첫 실행의 저장 파일 생성·기본 카테고리 초기화는 입력 실패 시에도 일어날 수 있으며, 여러 파일을 묶은 트랜잭션이나 동시 실행 제어까지 보장하지는 않습니다.

## 보너스 과제 구현 및 적용 위치

아래 표는 각 보너스의 적용 코드와 검증 근거입니다.

| 보너스명 | 적용 기능·명령 | 실제 파일·클래스·함수 | 적용 효과 | 검증 근거 |
| --- | --- | --- | --- | --- |
| 백업 기능 | `backup --out-dir` | [backup.py](budget_app/backup.py): `create_backup` | 모든 현재 JSONL을 고유 ZIP에 보관, 반복 규칙 포함 | `test_backup_contents_unique_and_failure_cleanup` |
| 반복 내역 | `recurring add/list/remove/generate` | [recurring.py](budget_app/recurring.py): `RecurringRule`, `RecurringStore`, `RecurringService.generate` | 월말 보정·연결 필드 기반 중복 방지 | `test_recurring_month_end_idempotency_and_delete_policies`, `test_recurring_failure_preserves_transactions` |
| 표 정렬 | list/search | [formatting.py](budget_app/formatting.py): `display_width`, `cell`, `print_transactions` | 한글 폭·제어문자·긴 메모의 표시 처리, 고정 폭 스트리밍 | `test_table_width_control_characters_and_lazy_values` |
| 저장 원자성 강화 | 아래 전체 쓰기 경로 | [repository.py](budget_app/repository.py): `atomic_text`, `write_jsonl`, `TransactionRepository.merge`; [exchange.py](budget_app/exchange.py): `export_csv` | 같은 폴더 임시 파일→flush/fsync→닫기→os.replace | `test_atomic_write_and_replace_failures`, `test_export_validation_and_preserves_existing_output` |

원자성 helper의 실제 사용 경로:

| 쓰기 경로 | 연결 |
| --- | --- |
| add/update/delete | `BudgetService` → `TransactionRepository.merge` → `write_jsonl` → `atomic_text` |
| import | `import_csv` → `merge` → 동일 경로 |
| 반복 generate | `RecurringService.generate` → `merge` → 동일 경로 (생성 거래와 연결 필드 함께 저장) |
| 카테고리 추가/삭제/초기화 | `CategoryStore.save` → `write_jsonl` → `atomic_text` |
| 예산 설정/초기화 | `BudgetStore.set` 또는 생성자 → `write_jsonl` → `atomic_text` |
| 반복 규칙 추가/삭제/초기화 | `RecurringStore.save` 또는 생성자 → `write_jsonl` → `atomic_text` |
| 거래 초기화 | `TransactionRepository.__init__` → `write_jsonl` → `atomic_text` |
| export | `export_csv` → `atomic_text` (CSV writer 사용) |
| ZIP 백업 | `create_backup`은 **atomic_text 미사용**. 새 고유 파일을 배타 생성하고 ZipFile 종료로 완성, 예외 시 삭제. 저장소 교체와 달리 작성 중 ZIP이 디렉터리에 보일 수 있음 |

동시 프로세스 잠금·여러 파일 동시 트랜잭션·전원 차단 시 디렉터리 메타데이터 영속성은 보장하지 않습니다. ZIP은 단일 실행 중 복사이며 동시 쓰기의 일관된 스냅샷이 아닙니다. 복구 명령은 범위 밖입니다. ZIP을 수동 확인한 뒤 별도 폴더에 복원하는 방식으로 운영해야 합니다.

## 검증

```powershell
python -m unittest tests.test_required -v
python -m unittest tests.test_bonus -v
python -m unittest discover -s tests -v
```

2026-10-18 Windows / Python 3.14.5에서 **필수 10개 + 보너스 5개 + 데코레이터 6개, 총 21개 테스트가 통과**했습니다. 임시 폴더와 별도 CLI 프로세스로 영속성·오류 종료·CSV 교환·백업·반복 생성·실패 시 원본 보존을 검증합니다. CSV 10건 중 마지막 1건에 오류가 있으면 전체가 반영되지 않는 검증도 통과했습니다. 실행 기록과 시간 측정의 인자·반환값·함수 정보 보존, 정상/오류 종료, 데코레이터 실행 순서도 확인합니다.

조회는 파일 순서로 읽어 list N개에서 중단 가능하지만 검색/요약은 최악 O(n)입니다. 추가/수정/삭제는 전체 순회·재작성 O(n), 수정은 찾기와 재작성 두 번입니다. import는 입력 m건을 메모리에 보관·정렬(O(m log m))하고 기존 n건과 병합합니다. 요약은 카테고리별 합계를 보관합니다. 반복 생성은 활성 규칙과 해당 월 중복 규칙 id를 보관합니다. 10만 건 실측은 미실행입니다. 월별 파일 분할·일괄 쓰기·인덱스가 개선 후보이며 제너레이터만으로 모든 메모리/디스크 문제가 해결되지는 않습니다.

원본은 최신순·3개 이상 파일·표준 라이브러리·대화형 add·필수 명령·모듈/클래스/제너레이터/데코레이터/타입 힌트를 요구합니다. JSONL 고정·동률 id순·UUID·전수 import 롤백·ZIP·반복 중복 처리·고정 폭은 상세 프롬프트의 추가 설계 정책입니다. 원본 옵션 표기의 `-`/`--` 충돌은 상세 기능 요구와 예시를 우선해 `--`로 통일했습니다.
