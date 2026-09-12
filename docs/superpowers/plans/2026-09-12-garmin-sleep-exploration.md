# Garmin Sleep Exploration Phase 0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide one UV-managed command that authenticates with Garmin Connect, preserves nightly endpoint responses in unique local run directories, analyzes their observed temporal structure, and writes a local Markdown report.

**Architecture:** `src.garmin_client` is the only Garmin boundary and owns current-token login plus the fixed, verified endpoint registry. `src.explore` validates dates and orchestrates fetch/write/report work; `src.analysis` reads the raw files and conservatively describes structures and timestamps without normalizing them. All durable behavior is covered with standard-library `unittest`; the real account is used only for the final local smoke run.

**Tech Stack:** Python 3.12+, UV, `garminconnect==0.3.13`, `curl-cffi`, Python standard library (`argparse`, `datetime`, `getpass`, `json`, `logging`, `statistics`, `unittest`).

**Spec:** `docs/superpowers/specs/2026-09-12-garmin-sleep-exploration-design.md`

## Global Constraints

- Use UV for all environment, dependency, lockfile, test, and CLI commands; do not add `requirements.txt`.
- Keep `garminconnect` pinned to the inspected release 0.3.13 and call only methods verified in the spec.
- Never store email, password, MFA codes, token contents, raw Garmin data, or generated reports in tracked files.
- Never overwrite a raw response or report.
- Preserve returned JSON field names and values; formatting JSON on disk is the only transformation.
- Do not infer medical meaning, thresholds, diagnoses, or an unspecified timezone.
- A failed endpoint must not stop the remaining endpoints for that date or later dates.
- Do not add Docker, a database, a web framework, or a dashboard in Phase 0.
- Commit after each task and keep unrelated user files untouched.

---

### Task 1: UV foundation, date selection, and exclusive raw writes

**Files:**
- Create: `README.md`
- Create: `pyproject.toml`
- Create: `uv.lock`
- Modify: `.gitignore`
- Create: `src/__init__.py`
- Create: `src/explore.py`
- Create: `tests/test_phase0.py`

**Interfaces:**
- Produces: `resolve_dates(*, days: int | None, start: date | None, end: date | None, today: date | None = None) -> list[str]`
- Produces: `new_run_id(now: datetime | None = None) -> str`
- Produces: `write_raw(run_dir: Path, cdate: str, endpoint: str, payload: Any) -> Path`

- [ ] **Step 1: Add the UV metadata and public-safety ignores**

Create `pyproject.toml` with exactly one runtime API dependency plus its recommended authentication transport:

```toml
[project]
name = "sleeplikeafeenix"
version = "0.1.0"
description = "Local exploration of personal Garmin sleep data"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "curl-cffi",
    "garminconnect==0.3.13",
]

[tool.uv]
package = false
```

Create a minimal `README.md` containing the project title, the exploration-only/non-medical scope, and the statement that setup instructions follow in Task 4. Extend `.gitignore` with:

```gitignore
.venv/
__pycache__/
*.py[cod]
.coverage
.pytest_cache/
.mypy_cache/
.ruff_cache/
.env
.env.*
data/
reports/
.garminconnect/
garmin_tokens.json
oauth1_token.json
oauth2_token.json
```

Keep the existing `garmin-cycling-merge/` entry. Add an empty `src/__init__.py`, then run:

```text
uv lock
uv sync
```

Expected: `.venv` is created, `uv.lock` pins `garminconnect` 0.3.13, and neither path is accidentally staged by the ignore rules.

- [ ] **Step 2: Write failing date and storage tests**

Create `tests/test_phase0.py` with literal expectations:

```python
import json
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path

from src.explore import new_run_id, resolve_dates, write_raw


class DateRangeTests(unittest.TestCase):
    def test_days_includes_today_and_preceding_dates(self):
        self.assertEqual(
            resolve_dates(days=3, start=None, end=None, today=date(2026, 9, 12)),
            ["2026-09-10", "2026-09-11", "2026-09-12"],
        )

    def test_explicit_range_is_inclusive(self):
        self.assertEqual(
            resolve_dates(
                days=None,
                start=date(2026, 9, 1),
                end=date(2026, 9, 3),
            ),
            ["2026-09-01", "2026-09-02", "2026-09-03"],
        )

    def test_invalid_ranges_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            resolve_dates(days=0, start=None, end=None)
        with self.assertRaisesRegex(ValueError, "together"):
            resolve_dates(days=None, start=date(2026, 9, 1), end=None)
        with self.assertRaisesRegex(ValueError, "before"):
            resolve_dates(
                days=None,
                start=date(2026, 9, 2),
                end=date(2026, 9, 1),
            )


class RawStorageTests(unittest.TestCase):
    def test_run_id_is_utc_and_microsecond_precise(self):
        self.assertEqual(
            new_run_id(datetime(2026, 9, 12, 10, 11, 12, 345678, tzinfo=UTC)),
            "20260912T101112345678Z",
        )

    def test_raw_payload_is_preserved_and_never_overwritten(self):
        payload = {"values": [[1726099200000, None], [1726099260000, 97]]}
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            target = write_raw(run_dir, "2026-09-12", "spo2", payload)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), payload)
            with self.assertRaises(FileExistsError):
                write_raw(run_dir, "2026-09-12", "spo2", {"changed": True})
```

- [ ] **Step 3: Run the tests and verify the expected failure**

Run:

```text
uv run python -m unittest tests.test_phase0.DateRangeTests tests.test_phase0.RawStorageTests -v
```

Expected: import failure because `src.explore` does not yet provide the three functions.

- [ ] **Step 4: Implement the minimum date and storage behavior**

Implement in `src/explore.py`:

```python
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any


def resolve_dates(*, days, start, end, today=None):
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
        raise ValueError("from must not be after to")
    return [
        (start + timedelta(days=offset)).isoformat()
        for offset in range((end - start).days + 1)
    ]


def new_run_id(now=None):
    instant = now or datetime.now(UTC)
    return instant.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def write_raw(run_dir, cdate, endpoint, payload):
    target = run_dir / cdate / f"{endpoint}.json"
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as output:
        output.write(encoded)
        output.write("\n")
    return target
```

Use the full annotations from the Interfaces block in the final implementation.

- [ ] **Step 5: Verify Task 1 and commit**

Run:

```text
uv run python -m unittest tests.test_phase0.DateRangeTests tests.test_phase0.RawStorageTests -v
git check-ignore .venv data reports garmin_tokens.json oauth1_token.json
```

Expected: five tests pass and every sensitive/local path is listed as ignored.

Commit:

```text
git add .gitignore README.md pyproject.toml uv.lock src/__init__.py src/explore.py tests/test_phase0.py
git commit -m "feat: add safe phase 0 project foundation"
```

---

### Task 2: Current-token authentication and isolated Garmin endpoint fetching

**Files:**
- Create: `src/garmin_client.py`
- Modify: `tests/test_phase0.py`

**Interfaces:**
- Produces: `ENDPOINTS: tuple[tuple[str, str], ...]`
- Produces: `authenticate(tokenstore: Path) -> Garmin`
- Produces: `fetch_date(client: Garmin, cdate: str) -> tuple[dict[str, Any], dict[str, str]]`
- Consumes later: Task 4 imports all three symbols without wrapping them in another client abstraction.

- [ ] **Step 1: Write the failing authentication and endpoint-isolation tests**

Append imports and tests to `tests/test_phase0.py`:

```python
from unittest.mock import patch

from garminconnect import Garmin, GarminConnectAuthenticationError
from src.garmin_client import ENDPOINTS, authenticate, fetch_date


class GarminBoundaryTests(unittest.TestCase):
    def test_every_registered_endpoint_exists_on_installed_client(self):
        missing = [method for _, method in ENDPOINTS if not hasattr(Garmin, method)]
        self.assertEqual(missing, [])

    @patch("src.garmin_client.getpass", return_value="secret")
    @patch("builtins.input", return_value="person@example.invalid")
    @patch("src.garmin_client.Garmin")
    def test_authentication_prompts_only_after_cached_token_failure(
        self, garmin_class, input_prompt, password_prompt
    ):
        class LoginClient:
            def __init__(self, fails=False):
                self.fails = fails
                self.login_paths = []

            def login(self, path):
                self.login_paths.append(path)
                if self.fails:
                    raise GarminConnectAuthenticationError("no current token")

        cached_client = LoginClient(fails=True)
        fresh_client = LoginClient()
        garmin_class.side_effect = [cached_client, fresh_client]
        result = authenticate(Path("token-dir"))
        self.assertIs(result, fresh_client)
        self.assertEqual(cached_client.login_paths, ["token-dir"])
        self.assertEqual(fresh_client.login_paths, ["token-dir"])
        input_prompt.assert_called_once()
        password_prompt.assert_called_once()
```

Add a real fake for endpoint behavior:

```python
    def test_endpoint_failure_does_not_stop_sibling_calls(self):
        calls = []

        class FakeGarmin:
            def __getattr__(self, method_name):
                def call(*args):
                    calls.append((method_name, args))
                    if method_name == "get_spo2_data":
                        raise RuntimeError("not available")
                    return {"method": method_name, "args": list(args)}
                return call

        payloads, errors = fetch_date(FakeGarmin(), "2026-09-12")
        self.assertNotIn("spo2", payloads)
        self.assertEqual(errors, {"spo2": "RuntimeError: not available"})
        self.assertEqual(payloads["sleep"]["args"], ["2026-09-12"])
        self.assertEqual(
            payloads["body_battery"]["args"],
            ["2026-09-12", "2026-09-12"],
        )
        self.assertEqual(len(calls), len(ENDPOINTS))
```

- [ ] **Step 2: Run the tests and verify the expected failure**

Run:

```text
uv run python -m unittest tests.test_phase0.GarminBoundaryTests -v
```

Expected: import failure because `src.garmin_client` does not exist.

- [ ] **Step 3: Implement token-first login and the verified registry**

Create `src/garmin_client.py` with these mechanics:

```python
from getpass import getpass
from pathlib import Path
from typing import Any

from garminconnect import Garmin, GarminConnectAuthenticationError

ENDPOINTS = (
    ("sleep", "get_sleep_data"),
    ("spo2", "get_spo2_data"),
    ("respiration", "get_respiration_data"),
    ("heart_rate", "get_heart_rates"),
    ("stress", "get_all_day_stress"),
    ("hrv", "get_hrv_data"),
    ("body_battery", "get_body_battery"),
    ("body_battery_events", "get_body_battery_events"),
    ("stats", "get_stats"),
)


def authenticate(tokenstore: Path) -> Garmin:
    tokenstore_text = str(tokenstore.expanduser())
    cached = Garmin()
    try:
        cached.login(tokenstore_text)
        return cached
    except (FileNotFoundError, GarminConnectAuthenticationError):
        pass

    email = input("Garmin email: ").strip()
    password = getpass("Garmin password: ")
    client = Garmin(
        email=email,
        password=password,
        prompt_mfa=lambda: input("Garmin MFA code: ").strip(),
    )
    del password
    client.login(tokenstore_text)
    return client


def fetch_date(client: Garmin, cdate: str) -> tuple[dict[str, Any], dict[str, str]]:
    payloads = {}
    errors = {}
    for endpoint, method_name in ENDPOINTS:
        try:
            method = getattr(client, method_name)
            payloads[endpoint] = (
                method(cdate, cdate)
                if method_name == "get_body_battery"
                else method(cdate)
            )
        except Exception as error:
            detail = str(error).splitlines()[0] or "no details"
            errors[endpoint] = f"{type(error).__name__}: {detail}"
    return payloads, errors
```

The broad exception is intentional only around one external endpoint call so sibling requests continue. Authentication errors remain outside that loop and fail the run.

- [ ] **Step 4: Verify installed methods, tests, and commit**

Run:

```text
uv run python -c "from garminconnect import Garmin; from src.garmin_client import ENDPOINTS; missing=[method for _, method in ENDPOINTS if not hasattr(Garmin, method)]; assert not missing, missing"
uv run python -m unittest tests.test_phase0.GarminBoundaryTests -v
```

Expected: method assertion exits successfully and all three boundary tests pass.

Commit:

```text
git add src/garmin_client.py tests/test_phase0.py
git commit -m "feat: add Garmin authentication and endpoint fetching"
```

---

### Task 3: Conservative timestamp and time-series analysis

**Files:**
- Create: `src/analysis.py`
- Modify: `tests/test_phase0.py`

**Interfaces:**
- Produces: `classify_timestamp(path: str, value: Any, requested_date: date) -> dict[str, Any] | None`
- Produces: `summarize_intervals(instants: list[datetime]) -> dict[str, int | float]`
- Produces: `analyze_payload(payload: Any, requested_date: date) -> dict[str, Any]`
- Analysis result keys: `paths`, `timestamps`, `series`, and `relevant_paths`.

- [ ] **Step 1: Write failing timestamp classification tests**

Append:

```python
from src.analysis import analyze_payload, classify_timestamp, summarize_intervals


class TimestampAnalysisTests(unittest.TestCase):
    def test_classifies_offset_gmt_local_and_nearby_epoch_without_guessing(self):
        requested = date(2026, 9, 12)
        self.assertEqual(
            classify_timestamp("$.start", "2026-09-12T01:00:00+02:00", requested)["representation"],
            "iso-offset",
        )
        self.assertEqual(
            classify_timestamp("$.startGMT", "2026-09-11 23:00:00", requested)["representation"],
            "explicit-utc-field",
        )
        local = classify_timestamp("$.startLocal", "2026-09-12 01:00:00", requested)
        self.assertEqual(local["representation"], "naive-local")
        self.assertIsNone(local["instant"])
        self.assertEqual(
            classify_timestamp("$.values[]", 1789174800000, requested)["representation"],
            "epoch-ms-candidate",
        )
        self.assertIsNone(classify_timestamp("$.score", 97, requested))

    def test_interval_summary_uses_sorted_unique_instants_and_reports_order(self):
        instants = [
            datetime(2026, 9, 12, 0, 2, tzinfo=UTC),
            datetime(2026, 9, 12, 0, 0, tzinfo=UTC),
            datetime(2026, 9, 12, 0, 1, tzinfo=UTC),
            datetime(2026, 9, 12, 0, 1, tzinfo=UTC),
        ]
        self.assertEqual(
            summarize_intervals(instants),
            {
                "samples": 4,
                "duplicates": 1,
                "out_of_order": 1,
                "min_seconds": 60.0,
                "median_seconds": 60.0,
                "max_seconds": 60.0,
            },
        )
```

- [ ] **Step 2: Run the timestamp tests and verify the expected failure**

Run:

```text
uv run python -m unittest tests.test_phase0.TimestampAnalysisTests -v
```

Expected: import failure because `src.analysis` does not exist.

- [ ] **Step 3: Implement timestamp classification and interval statistics**

Use `datetime.fromisoformat`, `datetime.fromtimestamp`, `statistics.median`, and these exact rules:

```python
TIME_WORDS = ("time", "date", "gmt", "utc")


def classify_timestamp(path, value, requested_date):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        divisor = 1000 if abs(value) >= 100_000_000_000 else 1 if abs(value) >= 1_000_000_000 else None
        if divisor is None:
            return None
        try:
            instant = datetime.fromtimestamp(value / divisor, UTC)
        except (OverflowError, OSError, ValueError):
            return None
        if abs((instant.date() - requested_date).days) > 2:
            return None
        return {
            "representation": "epoch-ms-candidate" if divisor == 1000 else "epoch-s-candidate",
            "instant": instant,
        }
    if not isinstance(value, str) or not any(word in path.casefold() for word in TIME_WORDS):
        return None
    if "T" not in value and ":" not in value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return {"representation": "iso-offset", "instant": parsed.astimezone(UTC)}
    if "gmt" in path.casefold() or "utc" in path.casefold():
        return {"representation": "explicit-utc-field", "instant": parsed.replace(tzinfo=UTC)}
    return {"representation": "naive-local", "instant": None}
```

`summarize_intervals` must count equal adjacent values as duplicates, count descending adjacent values as out of order, then sort unique instants and calculate positive chronological gaps. Return only sample/order counts when fewer than two unique instants exist.

- [ ] **Step 4: Write a failing structural-series test**

Append:

```python
    def test_payload_analysis_finds_pair_series_nulls_and_relevant_fields(self):
        payload = {
            "dailySleepDTO": {
                "sleepStartTimestampGMT": "2026-09-11 23:00:00",
                "sleepStartTimestampLocal": "2026-09-12 01:00:00",
                "deepSleepSeconds": 3600,
            },
            "heartRateValues": [
                [1789167600000, 60],
                [1789167660000, None],
                [1789167720000, 61],
            ],
        }
        result = analyze_payload(payload, date(2026, 9, 12))
        self.assertEqual(result["paths"]["$.heartRateValues[][1]"]["nulls"], 1)
        series = next(item for item in result["series"] if item["path"] == "$.heartRateValues")
        self.assertEqual(series["intervals"]["median_seconds"], 60.0)
        self.assertIn("$.dailySleepDTO.deepSleepSeconds", result["relevant_paths"])
        local = next(
            item for item in result["timestamps"]
            if item["path"] == "$.dailySleepDTO.sleepStartTimestampLocal"
        )
        self.assertEqual(local["representation"], "naive-local")
```

- [ ] **Step 5: Run the structural test and verify the expected failure**

Run:

```text
uv run python -m unittest tests.test_phase0.TimestampAnalysisTests.test_payload_analysis_finds_pair_series_nulls_and_relevant_fields -v
```

Expected: failure because `analyze_payload` does not yet return the required observations.

- [ ] **Step 6: Implement one recursive walker and series detector**

Implement a single recursive walk that records type occurrence/null/empty counts by path and calls `classify_timestamp` only on scalar values. Generic array members use `[]`; detected pair-series members use `[][0]` and `[][1]`, so null measurements aggregate at paths such as `$.heartRateValues[][1]`. When visiting a list, detect either:

1. pair samples where every non-empty element is a list/tuple of at least two items and its first item classifies as a timestamp; or
2. object samples where one key produces the greatest number of parseable timestamps.

For each detected series, store:

```python
{
    "path": path,
    "timestamp_path": "[0]" or selected_key,
    "samples": len(value),
    "intervals": summarize_intervals(parseable_instants),
}
```

Relevant paths are unique sorted paths containing one of:

```python
RELEVANT_WORDS = (
    "sleep", "stage", "movement", "restless", "spo2", "respiration",
    "heartrate", "heart_rate", "stress", "hrv", "bodybattery", "body_battery",
)
```

Store path observations as plain JSON-compatible dictionaries with sorted type names. Do not add a schema/model dependency.

- [ ] **Step 7: Verify Task 3 and commit**

Run:

```text
uv run python -m unittest tests.test_phase0.TimestampAnalysisTests -v
```

Expected: all timestamp and structural tests pass.

Commit:

```text
git add src/analysis.py tests/test_phase0.py
git commit -m "feat: analyze Garmin timestamp structures"
```

---

### Task 4: Markdown report, CLI orchestration, documentation, and live handoff

**Files:**
- Modify: `src/analysis.py`
- Modify: `src/explore.py`
- Modify: `tests/test_phase0.py`
- Replace: `README.md`

**Interfaces:**
- Produces: `render_report(raw_dir: Path, *, run_id: str, dates: list[str], failures: dict[str, dict[str, str]], metadata: dict[str, str]) -> str`
- Produces: `build_parser() -> argparse.ArgumentParser`
- Produces: `main(argv: list[str] | None = None) -> int`
- Consumes: `authenticate`, `fetch_date`, `new_run_id`, `resolve_dates`, `write_raw`, and `render_report`.

- [ ] **Step 1: Write a failing report test**

Append:

```python
from src.analysis import render_report


class ReportTests(unittest.TestCase):
    def test_report_describes_files_series_timezone_evidence_and_failures(self):
        with tempfile.TemporaryDirectory() as temporary:
            raw_dir = Path(temporary) / "raw"
            write_raw(
                raw_dir,
                "2026-09-12",
                "heart_rate",
                {"heartRateValues": [[1789167600000, 60], [1789167660000, 61]]},
            )
            report = render_report(
                raw_dir,
                run_id="20260912T120000000000Z",
                dates=["2026-09-12"],
                failures={"2026-09-12": {"spo2": "RuntimeError: unavailable"}},
                metadata={"python": "3.14.3", "garminconnect": "0.3.13"},
            )
        self.assertIn("# Garmin-Schlafdaten: Exploration", report)
        self.assertIn("heart_rate.json", report)
        self.assertIn("Median: 60", report)
        self.assertIn("epoch-ms-candidate", report)
        self.assertIn("spo2", report)
        self.assertIn("UTC-Normalisierung", report)
```

- [ ] **Step 2: Run the report test and verify the expected failure**

Run:

```text
uv run python -m unittest tests.test_phase0.ReportTests -v
```

Expected: import failure because `render_report` does not exist.

- [ ] **Step 3: Implement deterministic Markdown rendering**

`render_report` must read every `raw_dir/<date>/*.json` in sorted path order, call `analyze_payload`, and render these German sections:

```text
# Garmin-Schlafdaten: Exploration
## Lauf
## Abrufstatus
## Rohdateien
## Gefundene Strukturen
## Zeitreihen und Sampling-Intervalle
## Zeitstempel und Zeitzonenhinweise
## Für die Schlafanalyse relevante Felder
## Antworten aus den beobachteten Daten
## Empfehlung für spätere UTC-Normalisierung
## Einschränkungen
```

Under “Antworten”, group matching observed paths for sleep boundaries, phases, respiration, SpO2, movement/restlessness, heart rate, stress, HRV, and Body Battery. State “keine passenden Felder beobachtet” when a group is empty; do not state that the device cannot provide the metric. Render interval seconds with compact numeric formatting and list original timestamp representation names. The final normalization section must retain original value, timezone evidence, conversion rule, and canonical UTC as four future fields, while explicitly leaving naive local timestamps unresolved in Phase 0.

- [ ] **Step 4: Write failing parser and orchestration tests**

Append:

```python
from unittest.mock import patch
from src.explore import build_parser, main


class CliTests(unittest.TestCase):
    def test_parser_accepts_days_and_inclusive_range(self):
        self.assertEqual(build_parser().parse_args(["--days", "7"]).days, 7)
        parsed = build_parser().parse_args(["--from", "2026-09-01", "--to", "2026-09-07"])
        self.assertEqual(parsed.start, date(2026, 9, 1))
        self.assertEqual(parsed.end, date(2026, 9, 7))

    @patch("src.explore.authenticate")
    @patch("src.explore.fetch_date")
    @patch("src.explore.new_run_id", return_value="20260912T120000000000Z")
    def test_main_writes_successes_and_report_while_retaining_failures(
        self, run_id, fetch, auth
    ):
        auth.return_value = object()
        fetch.return_value = ({"sleep": {"dailySleepDTO": {}}}, {"spo2": "unavailable"})
        with tempfile.TemporaryDirectory() as temporary:
            previous = Path.cwd()
            try:
                os.chdir(temporary)
                exit_code = main(["--days", "1", "--tokenstore", "tokens"])
                raw = Path("data/raw/20260912T120000000000Z")
                reports = list(Path("reports/20260912T120000000000Z").glob("*.md"))
                self.assertEqual(exit_code, 0)
                self.assertEqual(len(list(raw.rglob("sleep.json"))), 1)
                self.assertEqual(len(reports), 1)
                self.assertIn("spo2", reports[0].read_text(encoding="utf-8"))
            finally:
                os.chdir(previous)
```

Also import `os`. Patch `src.explore.date` or pass a private `today` keyword into `main` only if the test date must be deterministic; prefer asserting the one generated date directory rather than its calendar name.

- [ ] **Step 5: Run the CLI tests and verify the expected failure**

Run:

```text
uv run python -m unittest tests.test_phase0.CliTests -v
```

Expected: import failure because `build_parser` and `main` do not exist.

- [ ] **Step 6: Implement CLI orchestration**

Build one `argparse.ArgumentParser` with mutually exclusive `--days` and `--from`, a required companion `--to` validation in `main`, and `--tokenstore` defaulting to `os.getenv("GARMINTOKENS", "~/.garminconnect")`. Parse dates with `date.fromisoformat` via an argparse type function that raises `ArgumentTypeError` on invalid values.

`main` must execute in this order:

1. resolve dates and authenticate;
2. create the run ID and in-memory failure map;
3. call `fetch_date` per date and `write_raw` for every success;
4. call `render_report` against `data/raw/<run-id>`;
5. exclusively create `reports/<run-id>/exploration.md`;
6. log each endpoint failure to stderr and print the raw/report paths;
7. return 0.

Catch date-validation errors through `parser.error`. Do not catch authentication exceptions into a successful exit code. Add:

```python
if __name__ == "__main__":
    raise SystemExit(main())
```

Use `importlib.metadata.version("garminconnect")` and `platform.python_version()` for report metadata.

- [ ] **Step 7: Replace README with complete German operating instructions**

Document:

- exploration-only and non-medical scope;
- `uv sync` installation;
- current token file `~/.garminconnect/garmin_tokens.json` and `--tokenstore`/`GARMINTOKENS` override;
- the verified incompatibility of legacy `oauth1_token.json`/`oauth2_token.json`, requiring one interactive login;
- why credentials and MFA must be entered only in the local terminal;
- `uv run python -m src.explore --days 7`;
- `uv run python -m src.explore --from 2026-09-01 --to 2026-09-07`;
- raw and report paths by run ID;
- endpoint failure isolation;
- timestamp/UTC limitations, Garmin API instability, device/account-dependent fields, and lack of medical interpretation;
- the inspected endpoint/method table from the spec.

- [ ] **Step 8: Run complete non-personal verification**

Run fresh:

```text
uv sync --locked
uv run python -m unittest discover -s tests -p "test_*.py" -v
uv run python -m src.explore --help
uv run python -c "import importlib.metadata as m; assert m.version('garminconnect') == '0.3.13'"
git diff --check
git status --short
```

Expected: UV reports a locked environment, all tests pass, help lists all four date/token arguments, the version assertion succeeds, and Git reports only intended project changes before commit.

- [ ] **Step 9: Commit the completed Phase 0 implementation**

```text
git add README.md src/analysis.py src/explore.py tests/test_phase0.py
git commit -m "feat: complete Garmin sleep exploration CLI"
```

- [ ] **Step 10: Perform security and live-access checks**

Run:

```text
git status --short --ignored
git ls-files data reports .env .garminconnect garmin_tokens.json oauth1_token.json oauth2_token.json
uv run python -m src.explore --days 1
```

Expected before credentials: the tracked-file query prints nothing sensitive. If `~/.garminconnect/garmin_tokens.json` is still absent, the CLI prompts in the local terminal. Enter Garmin email, password, and MFA only there. On successful authentication, verify that one unique raw run directory and `reports/<run-id>/exploration.md` exist, inspect only their file names and report structure in agent output, and never stage those ignored paths.

If interactive input is unavailable to the agent process, open the running terminal for the user and pause at the credential prompt. Resume verification after the user completes that local prompt; do not ask for credentials in chat.

---

## Subagent execution and review gates

Execute Tasks 1–4 sequentially because later tasks consume earlier interfaces and append to the same test file. For each task:

1. dispatch a fresh implementation worker with only the spec, plan task, current commit, TDD requirement, and that task's write set;
2. inspect its diff and rerun the task's verification locally;
3. dispatch a fresh spec-compliance reviewer that may read but not edit;
4. send required corrections back to the same implementer and repeat the spec review;
5. dispatch a fresh code-quality reviewer that may read but not edit;
6. send required corrections back to the same implementer and repeat the quality review;
7. close all three agents before starting the next task.

After Task 4, run the complete verification suite in the controller, inspect the commit range from `9217ae7` to `HEAD`, and perform one final repository-wide review before attempting the real credential-gated run.
