import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any


def resolve_dates(
    *,
    days: int | None,
    start: date | None,
    end: date | None,
    today: date | None = None,
) -> list[str]:
    if start is None and end is None:
        days = 7 if days is None else days
        if days < 1:
            raise ValueError("days must be positive")
        end = today or date.today()
        start = end - timedelta(days=days - 1)
    elif start is None or end is None:
        raise ValueError("from and to must be supplied together")
    elif days is not None:
        raise ValueError("days cannot be combined with from/to")
    if start > end:
        raise ValueError("from must not be after to (from must be before)")
    return [
        (start + timedelta(days=offset)).isoformat()
        for offset in range((end - start).days + 1)
    ]


def new_run_id(now: datetime | None = None) -> str:
    if now is not None and (now.tzinfo is None or now.utcoffset() is None):
        raise ValueError("now must be timezone-aware")
    instant = now or datetime.now(UTC)
    return instant.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def write_raw(run_dir: Path, cdate: str, endpoint: str, payload: Any) -> Path:
    target = run_dir / cdate / f"{endpoint}.json"
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as output:
        output.write(encoded)
        output.write("\n")
    return target
