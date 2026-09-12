import argparse
import importlib.metadata
import json
import os
import platform
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from src.analysis import render_report
from src.garmin_client import authenticate, fetch_date


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


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"invalid date {value!r}; expected YYYY-MM-DD"
        ) from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Garmin-Schlafdaten lokal und ohne medizinische Interpretation untersuchen."
    )
    date_options = parser.add_mutually_exclusive_group()
    date_options.add_argument(
        "--days",
        type=int,
        metavar="N",
        help="heute und die N-1 vorherigen Kalendertage abrufen (Standard: 7)",
    )
    date_options.add_argument(
        "--from",
        dest="start",
        type=_parse_date,
        metavar="YYYY-MM-DD",
        help="inklusiver Beginn des Datumsbereichs",
    )
    parser.add_argument(
        "--to",
        dest="end",
        type=_parse_date,
        metavar="YYYY-MM-DD",
        help="inklusives Ende; zusammen mit --from verwenden",
    )
    parser.add_argument(
        "--tokenstore",
        default=os.getenv("GARMINTOKENS", "~/.garminconnect"),
        metavar="PATH",
        help="Garmin-Tokenverzeichnis (Standard: GARMINTOKENS oder ~/.garminconnect)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        dates = resolve_dates(
            days=args.days,
            start=args.start,
            end=args.end,
        )
    except ValueError as error:
        parser.error(str(error))

    client = authenticate(Path(args.tokenstore))
    run_id = new_run_id()
    failures: dict[str, dict[str, str]] = {}
    raw_dir = Path("data") / "raw" / run_id
    for cdate in dates:
        payloads, errors = fetch_date(client, cdate)
        failures[cdate] = errors
        for endpoint, payload in payloads.items():
            write_raw(raw_dir, cdate, endpoint, payload)

    metadata = {
        "python": platform.python_version(),
        "garminconnect": importlib.metadata.version("garminconnect"),
    }
    report = render_report(
        raw_dir,
        run_id=run_id,
        dates=dates,
        failures=failures,
        metadata=metadata,
    )
    report_path = Path("reports") / run_id / "exploration.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("x", encoding="utf-8", newline="\n") as output:
        output.write(report)

    for cdate in dates:
        for endpoint, error in sorted(failures[cdate].items()):
            print(f"Fehler {cdate}/{endpoint}: {error}", file=sys.stderr)
    print(f"Rohdaten: {raw_dir}")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
