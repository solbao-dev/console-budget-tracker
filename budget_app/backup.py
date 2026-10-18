"""한 실행 시점의 JSONL 파일을 ZIP으로 복사한다. 동시 쓰기 잠금은 없다."""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile


def create_backup(directory: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = out_dir / f"cashbook-{stamp}-{uuid4().hex}.zip"
    created = False
    try:
        # x는 기존 파일을 덮어쓰지 않는다. UUID 충돌 시에도 기존 ZIP을 보존한다.
        with path.open("xb") as handle:
            created = True
            with ZipFile(handle, "w", compression=ZIP_DEFLATED) as archive:
                for source in sorted(directory.glob("*.jsonl")):
                    archive.write(source, arcname=source.name)
    except BaseException:
        if created:
            path.unlink(missing_ok=True)
        raise
    return path
