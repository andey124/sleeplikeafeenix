# Local Sleep Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved local Variant-C dashboard and lean Derived Store without weakening raw-data immutability, privacy, or the non-diagnostic product boundary.

**Architecture:** Keep fetching, derivation, and serving as three separate processes. A shared run-manifest module records value-free Fetch Result state, while the deep `src.sleep_store` module hides SQLite schemas, Garmin JSON interpretation, latest-usable selection, raw-series loading, and annotation transactions behind four operations. The standard-library web adapter consumes only that interface and serves local HTML, CSS, JavaScript, and SVG.

**Tech Stack:** Python 3.12+, UV, standard-library `sqlite3`, `http.server`, `html`, `json`, `urllib.parse`, `secrets`, native HTML/CSS/JavaScript/SVG, and `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-26-sleep-dashboard-design.md`

## Global Constraints

- Preserve the public store interface exactly: `import_run()`, `list_nights()`, `load_night_detail()`, and `save_annotation()`; callers never query SQLite tables or interpret Garmin JSON.
- Use UV and the existing `pyproject.toml`/`uv.lock`; require Python `>=3.12`; add no runtime dependency and no `requirements.txt`.
- Raw Responses stay exclusive, immutable, authoritative, ignored by Git, and located at `data/raw/<run-id>/<date>/<endpoint>.json`.
- Keep the Derived Store rebuildable at `data/derived/sleep.sqlite3`; keep the Annotation Store durable and separate at `data/user/annotations.sqlite3`.
- Move the endpoint registry once into a standard-library-only module and reuse it from fetching, manifest creation, and derivation.
- Reuse `src.analysis.classify_timestamp()` and its conservative date-near epoch logic; never assign a timezone to a naive local timestamp.
- Fetching remains CLI-only. `src.dashboard` must not import `src.garmin_client`, read token paths, request credentials, perform network requests, or expose a Fetch action.
- Bind the dashboard to `127.0.0.1` by default. Non-loopback binding requires an explicit host plus explicit accepted Host header names.
- Use parameterized SQL, a per-process CSRF token, strict Host validation, HTML/JSON escaping, a 16 KiB form-body limit, a 4,000-character note limit, at most 20 tags, and at most 40 characters per tag.
- Serve no CDN, remote font, image, analytics, or other external browser request. Keep CSS and JavaScript in local project files.
- Use short, neutral German UI copy, semantic forms/tables, visible keyboard focus, responsive layout, and reduced-motion support.
- Preserve gaps and source ordering in charts; do not interpolate Samples or draw medical reference lines.
- Do not implement breathing-pause detection, apnea events, medical thresholds, risk scores, diagnosis, treatment guidance, or a primary aggregate health judgment.
- Put no private measurements, notes, tags, identifiers, credentials, token contents, Raw Responses, generated databases, generated reports, or private screenshots in Git, fixtures, task messages, or review artifacts.
- Use synthetic values only in committed tests. Private acceptance may print structural counts and status names, never values or identifiers.
- Preserve all existing Phase-0 behavior and endpoint-failure isolation until the specific compact-report replacement step.

## Review Focus

1. A manifest, run directory, or stored `raw_path` containing `..`, an absolute path, or a run-ID mismatch must be rejected before any read outside the configured raw root; Task 3 pins this with path-containment tests.
2. Runs with equal `created_at_utc` must resolve latest-usable sources deterministically by descending `run_id`; Task 4 pins the tie-break and verifies that a newer Error/Fetched No Data result does not hide older Data.
3. Empty stores, a missing selected raw file, or one malformed series payload must leave history/annotations usable and mark only the affected panel unavailable; Tasks 1 and 4 pin these cases.
4. Duplicate form fields, invalid UTF-8, oversized bodies, excessive tags, long tags, and CSRF/Host failures must produce a bounded 4xx response without writing an Annotation; Task 7 pins every branch.
5. Legacy manifestless runs must infer only registered endpoints and requested date directories, classify missing files as Error with unavailable detail, and never reconstruct error text or measurements; Task 2 pins the fallback.

---

## Locked File Map

- Create `src/run_manifest.py`: shared endpoint registry, endpoint-specific value-aware classification, immutable manifest serialization/loading, legacy-manifest inference, and sanitized errors.
- Create `src/sleep_store.py`: four-operation deep interface, dataclasses, schema ownership, transactional import, latest-usable selection, raw-series loading, compact report rendering, and Annotation Store ownership.
- Create `src/derive.py`: retry/rebuild CLI over `import_run()` with no Garmin import.
- Create `src/dashboard.py`: argument parsing, secure local HTTP routes, server-side HTML shell, and calls to the four store operations.
- Create `src/dashboard.css`: production Variant-C visual system copied selectively from the approved prototype, with prototype controls removed.
- Create `src/dashboard.js`: history/comparison interactions, synchronized cursor, axis toggle, and gap-preserving SVG rendering.
- Create `tests/test_run_manifest.py`: registry, classification, manifest, sanitization, and legacy fallback tests.
- Create `tests/test_sleep_store.py`: tracer, schema, transactions, latest-usable selection, detail loading, compact report, and annotation tests.
- Create `tests/test_dashboard.py`: live local HTTP route, security, escaping, input-limit, asset, and UI contract tests.
- Create `tests/test_derive.py`: one-run import and atomic rebuild CLI tests.
- Modify `src/garmin_client.py`: import the shared endpoint registry; retain authentication and sibling-failure isolation.
- Modify `src/analysis.py`: retain timestamp/payload analysis helpers; delete the obsolete value-heavy report renderer after CLI migration.
- Modify `src/explore.py`: write Raw Responses, then manifest, then import/report; never expose credentials to derivation.
- Modify `tests/test_phase0.py`: retain Phase-0 coverage, adapt registry imports, and replace obsolete value-heavy report expectations with manifest/import integration expectations.
- Modify `README.md`: document fetch/derive/dashboard commands, local/LAN boundary, rebuild semantics, annotation backup, value-free reports, and medical/privacy limits.
- Do not modify `pyproject.toml`, `uv.lock`, `.gitignore`, `CONTEXT.md`, or private ignored data unless a test proves an approved requirement cannot be met without it.

## Locked Interfaces and Data Shapes

Use `Path` parameters throughout. Keep these dataclasses frozen and return tuples rather than mutable collections:

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

FetchState = Literal["data", "fetched_no_data", "error"]

@dataclass(frozen=True)
class ImportSummary:
    run_id: str
    imported_at_utc: str
    fetch_counts: tuple[tuple[FetchState, int], ...]
    raw_file_count: int
    night_count: int
    metric_count: int
    metric_names: tuple[str, ...]
    series_names: tuple[str, ...]
    timestamp_evidence_counts: tuple[tuple[str, int], ...]
    report: str

@dataclass(frozen=True)
class FetchCoverage:
    endpoint: str
    latest_state: FetchState
    latest_run_id: str
    latest_created_at_utc: str
    latest_error: str | None
    selected_run_id: str | None
    selected_created_at_utc: str | None
    selected_raw_path: str | None

@dataclass(frozen=True)
class Metric:
    name: str
    value: int | float | str
    unit: str | None
    scope: Literal["day", "night"]
    source_endpoint: str
    source_path: str
    source_run_id: str

@dataclass(frozen=True)
class Annotation:
    night_date: str
    note: str
    tags: tuple[str, ...]
    updated_at_utc: str

@dataclass(frozen=True)
class NightFilters:
    date_from: str | None = None
    date_to: str | None = None
    tag: str | None = None

@dataclass(frozen=True)
class NightSummary:
    night_date: str
    sleep_start_original: str
    sleep_start_utc: str | None
    sleep_start_evidence: str
    sleep_start_rule: str | None
    sleep_end_original: str
    sleep_end_utc: str | None
    sleep_end_evidence: str
    sleep_end_rule: str | None
    sleep_time_seconds: int
    deep_sleep_seconds: int | None
    light_sleep_seconds: int | None
    rem_sleep_seconds: int | None
    awake_sleep_seconds: int | None
    metrics: tuple[Metric, ...]
    coverage: tuple[FetchCoverage, ...]
    annotation: Annotation | None
    last_imported_at_utc: str

@dataclass(frozen=True)
class Sample:
    original_timestamp: str | int | float | None
    canonical_utc: str | None
    timezone_evidence: str | None
    conversion_rule: str | None
    value: int | float | str | None
    source_payload: Any

@dataclass(frozen=True)
class SignalSeries:
    name: str
    unit: str | None
    source_endpoint: str
    source_path: str
    source_run_id: str
    samples: tuple[Sample, ...]

@dataclass(frozen=True)
class NightDetail:
    summary: NightSummary
    series: tuple[SignalSeries, ...]
    unavailable_panels: tuple[str, ...]

def import_run(
    derived_database: Path,
    raw_run_dir: Path,
    manifest: Mapping[str, Any] | None = None,
) -> ImportSummary: ...

def list_nights(
    derived_database: Path,
    annotation_database: Path,
    filters: NightFilters,
) -> list[NightSummary]: ...

def load_night_detail(
    derived_database: Path,
    raw_root: Path,
    night_date: str,
) -> NightDetail: ...

def save_annotation(
    derived_database: Path,
    annotation_database: Path,
    night_date: str,
    note: str,
    tags: Sequence[str],
) -> Annotation: ...
```

The manifest format is versioned and value-free:

```json
{
  "schema_version": 1,
  "run_id": "20260926T120000000000Z",
  "created_at_utc": "2026-09-26T12:00:00+00:00",
  "requested_from": "2026-09-25",
  "requested_to": "2026-09-26",
  "versions": {"python": "3.12.0", "garminconnect": "0.3.13"},
  "expected_endpoints": ["sleep", "spo2", "respiration", "heart_rate", "stress", "hrv", "body_battery", "body_battery_events", "stats"],
  "fetches": [
    {"date": "2026-09-25", "endpoint": "sleep", "state": "data", "error": null}
  ]
}
```

The initial allowlist is exact. A scalar counts only when its full path is listed and its value is not `null`; a series counts only when at least one allowlisted sample value is not `null`:

```python
METRIC_RULES = {
    "sleep": {
        "sleep_score": ("dailySleepDTO.sleepScores.overall.value", "night", None),
        "sleep_time": ("dailySleepDTO.sleepTimeSeconds", "night", "s"),
        "deep_sleep": ("dailySleepDTO.deepSleepSeconds", "night", "s"),
        "light_sleep": ("dailySleepDTO.lightSleepSeconds", "night", "s"),
        "rem_sleep": ("dailySleepDTO.remSleepSeconds", "night", "s"),
        "awake_sleep": ("dailySleepDTO.awakeSleepSeconds", "night", "s"),
        "spo2_average": ("dailySleepDTO.averageSpO2Value", "night", "%"),
        "spo2_lowest": ("dailySleepDTO.lowestSpO2Value", "night", "%"),
        "respiration_average": ("dailySleepDTO.averageRespirationValue", "night", "breaths/min"),
        "resting_heart_rate": ("restingHeartRate", "night", "bpm"),
        "hrv_average": ("avgOvernightHrv", "night", "ms"),
        "stress_average": ("dailySleepDTO.avgSleepStress", "night", None),
        "body_battery_change": ("bodyBatteryChange", "night", None),
        "restless_moments": ("restlessMomentsCount", "night", None),
    },
    "spo2": {
        "spo2_average": ("avgSleepSpO2", "night", "%"),
        "spo2_lowest": ("lowestSpO2", "night", "%"),
    },
    "respiration": {
        "respiration_average": ("avgSleepRespirationValue", "night", "breaths/min"),
        "respiration_highest": ("highestRespirationValue", "night", "breaths/min"),
        "respiration_lowest": ("lowestRespirationValue", "night", "breaths/min"),
    },
    "heart_rate": {
        "resting_heart_rate": ("restingHeartRate", "day", "bpm"),
    },
    "stress": {
        "stress_average": ("avgStressLevel", "day", None),
        "stress_maximum": ("maxStressLevel", "day", None),
    },
    "hrv": {
        "hrv_average": ("hrvSummary.lastNightAvg", "night", "ms"),
        "hrv_five_minute_high": ("hrvSummary.lastNight5MinHigh", "night", "ms"),
    },
    "stats": {
        "resting_heart_rate": ("restingHeartRate", "day", "bpm"),
        "stress_average": ("averageStressLevel", "day", None),
        "body_battery_during_sleep": ("bodyBatteryDuringSleep", "night", None),
        "body_battery_charged": ("bodyBatteryChargedValue", "day", None),
        "body_battery_at_wake": ("bodyBatteryAtWakeTime", "night", None),
    },
}

SERIES_RULES = {
    "sleep": (
        ("sleep_stages", "sleepLevels", "startGMT", "activityLevel", None),
        ("sleep_movement", "sleepMovement", "startGMT", "activityLevel", None),
        ("spo2", "wellnessEpochSPO2DataDTOList", "epochTimestamp", "spo2Reading", "%"),
        ("respiration", "wellnessEpochRespirationDataDTOList", "startTimeGMT", "respirationValue", "breaths/min"),
        ("heart_rate", "sleepHeartRate", "startGMT", "value", "bpm"),
        ("hrv", "hrvData", "startGMT", "value", "ms"),
        ("stress", "sleepStress", "startGMT", "value", None),
        ("body_battery", "sleepBodyBattery", "startGMT", "value", None),
    ),
    "spo2": (("spo2", "spO2SingleValues", 0, 1, "%"),),
    "respiration": (("respiration", "respirationValuesArray", 0, 1, "breaths/min"),),
    "heart_rate": (("heart_rate", "heartRateValues", 0, 1, "bpm"),),
    "stress": (
        ("stress", "stressValuesArray", 0, 1, None),
        ("body_battery", "bodyBatteryValuesArray", 0, 1, None),
    ),
    "hrv": (("hrv", "hrvReadings", "readingTimeGMT", "hrvValue", "ms"),),
    "body_battery": (("body_battery", "bodyBatteryValuesArray", 0, 1, None),),
    "body_battery_events": (),
    "stats": (),
}
```

For `sleep`, Data additionally requires non-null `dailySleepDTO.sleepStartTimestampGMT`, `dailySleepDTO.sleepEndTimestampGMT`, and `dailySleepDTO.sleepTimeSeconds`. Identity/profile fields, insights, qualifiers, thresholds, unknown scalars, descriptor arrays, and empty/null allowlisted fields never make a Fetch Result usable.

### Task 1: Deliver the smallest vertical tracer

**Files:**
- Create: `src/sleep_store.py`
- Create: `src/dashboard.py`
- Create: `tests/test_sleep_store.py`
- Create: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: a synthetic Raw Response directory and the version-1 manifest mapping above.
- Produces: the locked dataclasses, `import_run()`, `list_nights()`, `load_night_detail()`, and `create_server(host, port, raw_root, derived_database, annotation_database, allowed_hosts, csrf_token) -> ThreadingHTTPServer`.

- [ ] **Step 1: Write the failing end-to-end tracer test**

Create one helper in `tests/test_sleep_store.py` that writes only this synthetic Night:

```python
def write_synthetic_sleep_run(raw_root: Path) -> tuple[Path, dict[str, object]]:
    run_id = "20260926T120000000000Z"
    run_dir = raw_root / run_id
    target = run_dir / "2026-09-26" / "sleep.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({
        "dailySleepDTO": {
            "sleepStartTimestampGMT": "2026-09-25 22:00:00",
            "sleepEndTimestampGMT": "2026-09-26 06:00:00",
            "sleepTimeSeconds": 27000,
            "deepSleepSeconds": 3600,
        },
        "sleepHeartRate": [
            {"startGMT": "2026-09-25 22:00:00", "value": 55},
            {"startGMT": "2026-09-25 22:01:00", "value": None},
        ],
    }), encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at_utc": "2026-09-26T12:00:00+00:00",
        "requested_from": "2026-09-26",
        "requested_to": "2026-09-26",
        "versions": {"python": "3.12.0", "garminconnect": "0.3.13"},
        "expected_endpoints": ["sleep"],
        "fetches": [{"date": "2026-09-26", "endpoint": "sleep", "state": "data", "error": None}],
    }
    return run_dir, manifest
```

Add `test_vertical_tracer_imports_lists_and_loads_one_night()` to `tests/test_sleep_store.py`; import the run, assert one `NightSummary`, and assert one `heart_rate` `SignalSeries` with the `None` gap preserved.

In `tests/test_dashboard.py`, repeat this smallest synthetic fixture locally, start `create_server(..., port=0, csrf_token="test-token")` in a thread, request `GET /nights/2026-09-26` with `Host: 127.0.0.1`, and assert `200`, `text/html`, `Historie`, `Analysebank`, and `2026-09-26`. The small duplication keeps production code free of a test-fixture abstraction.

- [ ] **Step 2: Run the tracer to verify the red state**

Run: `uv run python -m unittest discover -s tests -p "test_sleep_store.py" -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'src.sleep_store'`.

Run: `uv run python -m unittest discover -s tests -p "test_dashboard.py" -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'src.dashboard'`.

- [ ] **Step 3: Implement only the tracer slice**

In `src/sleep_store.py`, create the locked dataclasses, a private `_connect()` that enables `PRAGMA foreign_keys = ON`, minimal `runs/fetches/nights/metrics` tables, and the three read/import operations needed by the test. Use `classify_timestamp()` for the two GMT boundaries and one SQL transaction for the run.

In `src/dashboard.py`, implement `create_server()` with a closure-backed `BaseHTTPRequestHandler`, disabled `log_message()`, one `GET /nights/<ISO-date>` route, and escaped server-rendered headings. Do not add assets, POST, comparison, or LAN behavior yet.

- [ ] **Step 4: Run the tracer and complete baseline**

Run: `uv run python -m unittest discover -s tests -p "test_sleep_store.py" -v`

Expected: PASS with one test and `OK`.

Run: `uv run python -m unittest discover -s tests -p "test_dashboard.py" -v`

Expected: PASS with one test and `OK`.

Run: `uv run python -m unittest discover -s tests -v`

Expected: all existing 26 Phase-0 tests plus both tracer tests pass.

- [ ] **Step 5: Commit the tracer**

```text
git add src/sleep_store.py src/dashboard.py tests/test_sleep_store.py tests/test_dashboard.py
git commit -m "feat: add sleep dashboard vertical tracer"
```

- [ ] **Review gate 1: Deep-interface review**

Have a fresh reviewer compare the commit with the four locked operations and confirm that the handler has no SQL, Garmin JSON paths, or Garmin client import. Resolve Important/Critical findings and rerun the full suite before Task 2.

### Task 2: Add immutable manifests and value-aware Fetch Results

**Files:**
- Create: `src/run_manifest.py`
- Create: `tests/test_run_manifest.py`
- Modify: `src/garmin_client.py`
- Modify: `src/sleep_store.py`
- Modify: `tests/test_phase0.py`

**Interfaces:**
- Consumes: existing endpoint calls, completed Raw Responses, sanitized endpoint errors, and optional manifest mappings passed to `import_run()`.
- Produces: `ENDPOINTS`, `EXPECTED_ENDPOINTS`, `classify_fetch_result(endpoint, payload) -> FetchState`, `write_manifest(...) -> Path`, and `load_manifest(raw_run_dir, manifest=None) -> RunManifest`; these remain implementation helpers, not HTTP/CLI JSON interpretation.

- [ ] **Step 1: Write failing manifest and classification tests**

In `tests/test_run_manifest.py`, add exact tests for:

```python
def test_sleep_requires_all_three_night_fields(self):
    placeholder = {"dailySleepDTO": {
        "sleepStartTimestampGMT": None,
        "sleepEndTimestampGMT": None,
        "sleepTimeSeconds": None,
        "sleepScoreInsight": "synthetic prose",
    }}
    self.assertEqual(classify_fetch_result("sleep", placeholder), "fetched_no_data")

def test_allowlisted_values_or_series_are_data_but_identity_only_is_not(self):
    self.assertEqual(classify_fetch_result("spo2", {"calendarDate": "2026-09-26"}), "fetched_no_data")
    self.assertEqual(classify_fetch_result("spo2", {"avgSleepSpO2": 96.0}), "data")
    self.assertEqual(classify_fetch_result("heart_rate", {"heartRateValues": [[1_799_000_000_000, None]]}), "fetched_no_data")
    self.assertEqual(classify_fetch_result("heart_rate", {"heartRateValues": [[1_799_000_000_000, 55]]}), "data")
```

Also test all registered endpoints, `null`, `{}`, `[]`, unknown scalars, exclusive `manifest.json` creation, absence of synthetic measurement values and secret-like keys in serialized manifest text, run-ID mismatch rejection, invalid date/state rejection, and manifestless inference. Pass an exception whose message contains synthetic email/URL/token text through `fetch_date()` and assert the retained error is exactly its exception class name, never `str(error)`. Validate manifest error names against `^[A-Za-z_][A-Za-z0-9_.-]{0,99}$` and replace any externally supplied non-matching string with `EndpointError`. For the legacy case, create one successful `sleep.json`, omit all sibling endpoint files, and assert those siblings become Error with exactly `"unavailable for manifestless run"`.

- [ ] **Step 2: Run the focused tests to verify red**

Run: `uv run python -m unittest discover -s tests -p "test_run_manifest.py" -v`

Expected: FAIL because `src.run_manifest` does not exist.

- [ ] **Step 3: Implement the registry, classifier, and manifest module**

Move the existing registry unchanged from `src.garmin_client`:

```python
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
EXPECTED_ENDPOINTS = tuple(endpoint for endpoint, _ in ENDPOINTS)
```

Implement the locked scalar/series rules, path lookup for dotted object paths, pair/object series checks, dataclass validation for `RunManifest`/`ManifestFetch`, exclusive UTF-8 JSON writing with sorted keys and a trailing newline, and legacy inference from ISO-date directories plus the UTC run-ID timestamp. Change `fetch_date()` to retain only `type(error).__name__`; no arbitrary exception message may reach a manifest, report, terminal, or web response. Do not infer profile/identity/insight fields.

Update `src.garmin_client.py` and `tests/test_phase0.py` to import `ENDPOINTS` from `src.run_manifest`. Update `import_run()` to call `load_manifest()` and independently verify that manifest state agrees with each raw file's classification; reject a manifest claiming Data for a non-usable payload.

- [ ] **Step 4: Run focused and complete tests**

Run: `uv run python -m unittest discover -s tests -p "test_run_manifest.py" -v`

Expected: all manifest tests pass.

Run: `uv run python -m unittest discover -s tests -v`

Expected: all Phase-0, tracer, and manifest tests pass.

- [ ] **Step 5: Commit manifest support**

```text
git add src/run_manifest.py src/garmin_client.py src/sleep_store.py tests/test_run_manifest.py tests/test_phase0.py
git commit -m "feat: classify fetch results and write run manifests"
```

- [ ] **Review gate 2: Raw/manifest boundary review**

Have a fresh reviewer verify exclusive writes, no values/secrets in manifests, exact endpoint coverage, sleep-placeholder handling, and no duplicated endpoint registry. Resolve findings before Task 3.

### Task 3: Complete transactional Derived Store import and compact reporting

**Files:**
- Modify: `src/sleep_store.py`
- Modify: `tests/test_sleep_store.py`

**Interfaces:**
- Consumes: validated `RunManifest`, allowlisted Raw Responses, and timestamp evidence from `src.analysis`.
- Produces: a complete `ImportSummary.report` and rebuildable schema hidden behind `import_run()`.

- [ ] **Step 1: Write failing transaction, schema, path, and report tests**

Add tests that:

1. import two runs and assert their separate summary counts;
2. re-import one changed synthetic run and assert only that run's derived rows are replaced;
3. make the replacement payload malformed JSON and assert the previous summary/list result survives unchanged;
4. inspect `PRAGMA foreign_keys` and verify an orphan `fetches.run_id` insert raises `sqlite3.IntegrityError`;
5. reject absolute, parent-traversing, and run-ID-mismatched raw locations before opening them;
6. assert the report contains state counts, raw/derived counts, Night coverage, metric/series names, units, timestamp-evidence counts, and the non-diagnostic limitation;
7. assert a Data endpoint contributes Metrics even when the same run/date has no Night;
8. assert malformed JSON errors name only the affected relative file and never include payload content;
9. assert the report does not contain any supplied synthetic scalar, Sample, note, identifier, raw JSON fragment, or error control character.

Use this direct schema check only for the explicit foreign-key requirement; exercise all other behavior through `import_run()` and `list_nights()`.

- [ ] **Step 2: Run the focused suite to verify red**

Run: `uv run python -m unittest discover -s tests -p "test_sleep_store.py" -v`

Expected: FAIL on missing tables/columns, replacement behavior, report coverage, and path validation.

- [ ] **Step 3: Implement the complete private schema and one-run transaction**

Create these private tables with `CHECK` constraints and cascading foreign keys:

```sql
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    requested_from TEXT NOT NULL,
    requested_to TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    imported_at_utc TEXT NOT NULL,
    python_version TEXT,
    garminconnect_version TEXT
);

CREATE TABLE fetches (
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('data', 'fetched_no_data', 'error')),
    raw_path TEXT,
    error TEXT,
    PRIMARY KEY (run_id, date, endpoint),
    CHECK ((state = 'error' AND raw_path IS NULL AND error IS NOT NULL)
        OR (state != 'error' AND raw_path IS NOT NULL AND error IS NULL))
);

CREATE TABLE nights (
    run_id TEXT NOT NULL,
    night_date TEXT NOT NULL,
    source_endpoint TEXT NOT NULL DEFAULT 'sleep' CHECK (source_endpoint = 'sleep'),
    sleep_start_original TEXT NOT NULL,
    sleep_start_utc TEXT,
    sleep_start_evidence TEXT NOT NULL,
    sleep_start_rule TEXT,
    sleep_end_original TEXT NOT NULL,
    sleep_end_utc TEXT,
    sleep_end_evidence TEXT NOT NULL,
    sleep_end_rule TEXT,
    sleep_time_seconds INTEGER NOT NULL,
    deep_sleep_seconds INTEGER,
    light_sleep_seconds INTEGER,
    rem_sleep_seconds INTEGER,
    awake_sleep_seconds INTEGER,
    PRIMARY KEY (run_id, night_date),
    FOREIGN KEY (run_id, night_date, source_endpoint) REFERENCES fetches(run_id, date, endpoint) ON DELETE CASCADE
);

CREATE TABLE metrics (
    run_id TEXT NOT NULL,
    date TEXT NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN ('day', 'night')),
    metric TEXT NOT NULL,
    numeric_value REAL,
    text_value TEXT,
    unit TEXT,
    source_endpoint TEXT NOT NULL,
    source_path TEXT NOT NULL,
    PRIMARY KEY (run_id, date, metric, source_endpoint, source_path),
    FOREIGN KEY (run_id, date, source_endpoint) REFERENCES fetches(run_id, date, endpoint) ON DELETE CASCADE,
    CHECK ((numeric_value IS NULL) != (text_value IS NULL))
);
```

Keep the `nights.source_endpoint` implementation detail out of dataclasses and callers.

Within `BEGIN IMMEDIATE`, create schema, delete the matching `runs` row, insert the run/fetch rows, parse every successful Raw Response, insert allowlisted Metrics from every Data Fetch Result whether or not that run/date has a Night, insert a Night only for valid sleep Data, and commit. Roll back on any exception. Store raw paths as `<run-id>/<date>/<endpoint>.json` after `Path.resolve()` containment checks against `raw_run_dir.parent`. Wrap malformed JSON with an exception that names the relative file only; never append payload text.

Render `ImportSummary.report` from counters and distinct names only. It may include dates and run metadata in the local ignored report, but never measurement values, Samples, raw fragments, credentials, user-authored text, or identifiers from payloads.

- [ ] **Step 4: Run focused and complete tests**

Run: `uv run python -m unittest discover -s tests -p "test_sleep_store.py" -v`

Expected: all transaction/schema/report tests pass.

Run: `uv run python -m unittest discover -s tests -v`

Expected: full suite passes.

- [ ] **Step 5: Commit transactional import**

```text
git add src/sleep_store.py tests/test_sleep_store.py
git commit -m "feat: import derived sleep records transactionally"
```

- [ ] **Review gate 3: Persistence review**

Have a fresh reviewer inspect the SQL constraints, transaction scope, idempotent replacement, path containment, parameter binding, and report value-elision. Resolve findings before Task 4.

### Task 4: Resolve Logical Nights and load selected raw series

**Files:**
- Modify: `src/sleep_store.py`
- Modify: `tests/test_sleep_store.py`

**Interfaces:**
- Consumes: multiple imported run versions, the configured Raw Response root, and `NightFilters`.
- Produces: fully populated `NightSummary`, `FetchCoverage`, `Metric`, `NightDetail`, `SignalSeries`, and `Sample` objects with per-endpoint provenance.

- [ ] **Step 1: Write failing latest-usable and detail tests**

Create three synthetic runs for one Night Date:

- oldest: usable sleep and SpO2;
- middle: usable respiration and HRV but sleep Fetched No Data;
- newest: sleep Error, SpO2 Fetched No Data, and usable heart rate.

Assert `list_nights()` returns one Logical Night whose sleep comes from the oldest run, respiration/HRV from the middle run, heart rate from the newest run, and SpO2 from the oldest run. Assert SpO2 coverage still reports the newest state as `fetched_no_data`; sleep coverage reports newest `error`; every selected source exposes its own run/path/date provenance.

Add a same-`created_at_utc` pair and assert descending `run_id` wins. Add date-range tests, an empty-store test, and ensure all captured Night Dates remain selectable.

For `load_night_detail()`, use ordered pair/object Samples containing `None`, duplicate/out-of-order timestamps, explicit GMT, offset ISO, epoch, and naive-local values. Assert source order and payloads are unchanged, `None` remains a gap, canonical UTC exists only when evidence permits, and naive-local has no canonical UTC. Delete one selected raw file and corrupt another; assert only those panels appear in `unavailable_panels` while other series and the summary still load.

- [ ] **Step 2: Run focused tests to verify red**

Run: `uv run python -m unittest discover -s tests -p "test_sleep_store.py" -v`

Expected: FAIL on cross-run selection, provenance, tie-break, series extraction, and panel isolation.

- [ ] **Step 3: Implement latest-usable selection once inside the deep module**

Use a parameterized window query ordered by `runs.created_at_utc DESC, fetches.run_id DESC` to rank Data independently per `(date, endpoint)`. Use a second ranking over all states for latest coverage. Select Metrics only from each endpoint's chosen Data run. Load selected raw paths on demand and apply the locked series rules without sorting Samples or filling gaps.

Query `MAX(runs.imported_at_utc)` once and copy that global store timestamp into every returned `NightSummary.last_imported_at_utc`. When no Night exists, the dashboard shows `Noch kein erfolgreicher Nacht-Import` rather than bypassing the interface to inspect SQLite.

For each timestamp, store the original value and reuse `classify_timestamp()`; map representations to these conversion rules only:

```python
CONVERSION_RULES = {
    "explicit-utc-field": "explicit-utc-field",
    "iso-offset": "iso-offset-to-utc",
    "epoch-ms-candidate": "epoch-ms-to-utc",
    "epoch-s-candidate": "epoch-s-to-utc",
    "naive-local": None,
}
```

Catch file-not-found and `json.JSONDecodeError` per selected series source, append the panel name once to `unavailable_panels`, and continue. Do not catch database or programmer errors.

- [ ] **Step 4: Run focused and complete tests**

Run: `uv run python -m unittest discover -s tests -p "test_sleep_store.py" -v`

Expected: all selection/detail tests pass.

Run: `uv run python -m unittest discover -s tests -v`

Expected: full suite passes.

- [ ] **Step 5: Commit Logical Night selection**

```text
git add src/sleep_store.py tests/test_sleep_store.py
git commit -m "feat: select logical nights and load raw series"
```

- [ ] **Review gate 4: Provenance/timestamp review**

Have a fresh reviewer trace one Logical Night end to end and verify deterministic selection, explicit mixed-run provenance, no interpolation/reordering, conservative timestamp conversion, and isolated malformed panels. Resolve findings before Task 5.

### Task 5: Persist Annotations outside derivation

**Files:**
- Modify: `src/sleep_store.py`
- Modify: `tests/test_sleep_store.py`

**Interfaces:**
- Consumes: existing Night Dates, note text, and an ordered tag sequence.
- Produces: transactional `Annotation` upserts and tag-aware `list_nights()` filtering without coupling Annotation lifecycle to derivation.

- [ ] **Step 1: Write failing Annotation tests**

Add tests that call `save_annotation()` twice for one Night Date and assert update behavior, trim tags, drop empty tags, deduplicate with `casefold()`, and preserve the first entered display spelling:

```python
saved = save_annotation(
    derived,
    annotations,
    "2026-09-26",
    "  synthetic note  ",
    [" Training ", "training", "", "SPÄT"],
)
self.assertEqual(saved.note, "synthetic note")
self.assertEqual(saved.tags, ("Training", "SPÄT"))
```

Assert rejection for an unknown Night Date, note length 4,001, 21 tags, and a 41-character tag. Assert a tag filter matches case-insensitively. Rebuild the Derived Store into a new file, leave the Annotation Store untouched, re-import the run, and assert the Annotation remains attached. Assert derivation never creates, deletes, or modifies `annotations.sqlite3`.

- [ ] **Step 2: Run focused tests to verify red**

Run: `uv run python -m unittest discover -s tests -p "test_sleep_store.py" -v`

Expected: FAIL because `save_annotation()` and tag filtering are incomplete.

- [ ] **Step 3: Implement the separate Annotation Store**

Use exactly this schema in a separate connection/transaction:

```sql
CREATE TABLE annotations (
    night_date TEXT PRIMARY KEY,
    note TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);
```

Verify the Night Date exists through the Derived Store before opening the Annotation transaction. Normalize tags in Python, serialize the tuple deterministically as JSON, and upsert with parameters. `list_nights()` reads annotations in a separate connection, joins them by date in memory, and applies the tag filter by normalized `casefold()` equality.

- [ ] **Step 4: Run focused and complete tests**

Run: `uv run python -m unittest discover -s tests -p "test_sleep_store.py" -v`

Expected: all Annotation tests pass.

Run: `uv run python -m unittest discover -s tests -v`

Expected: full suite passes.

- [ ] **Step 5: Commit Annotation persistence**

```text
git add src/sleep_store.py tests/test_sleep_store.py
git commit -m "feat: persist sleep annotations separately"
```

- [ ] **Review gate 5: Durable-user-data review**

Have a fresh reviewer verify that derivation cannot touch the Annotation Store, validation exists at the store seam, SQL is parameterized, and rebuild survival is covered. Resolve findings before Task 6.

### Task 6: Integrate fetch, retry, rebuild, and value-free reports

**Files:**
- Create: `src/derive.py`
- Create: `tests/test_derive.py`
- Modify: `src/explore.py`
- Modify: `src/analysis.py`
- Modify: `tests/test_phase0.py`

**Interfaces:**
- Consumes: completed fetch payloads/errors, existing raw-run directories, and `import_run()`.
- Produces: `src.explore` writing Raw Responses -> manifest -> Derived Store/report in that order, plus `src.derive` one-run retry and atomic all-run rebuild.

- [ ] **Step 1: Write failing fetch/import and derive CLI tests**

Extend the mocked `src.explore.main()` test to assert:

- all Raw Responses are written before `manifest.json`;
- manifest classification is value-aware;
- `import_run()` is called only after the manifest exists;
- the compact report is exclusively written to `reports/<run-id>/exploration.md`;
- an import exception leaves Raw Responses and manifest intact;
- stdout/stderr name paths, endpoint/status names, and counts but contain no synthetic measurement, note, token, or payload fragment.

In `tests/test_derive.py`, call:

```python
main([str(run_dir), "--derived-db", str(derived), "--report-root", str(reports)])
main([str(raw_root), "--rebuild", "--derived-db", str(derived), "--report-root", str(reports)])
```

Assert one-run retry is idempotent. For rebuild, prepopulate the target DB, include one malformed run, assert nonzero exit and byte-for-byte preservation of the target DB; fix the synthetic run, rerun, and assert atomic replacement via a same-directory temporary database. Assert the Annotation Store path is never accepted or touched by this CLI.

- [ ] **Step 2: Run focused tests to verify red**

Run: `uv run python -m unittest discover -s tests -p "test_derive.py" -v`

Expected: FAIL because `src.derive` does not exist.

Run: `uv run python -m unittest discover -s tests -p "test_phase0.py" -v`

Expected: FAIL on manifest/import/report ordering expectations.

- [ ] **Step 3: Implement CLI ordering and atomic rebuild**

In `src.explore.main()`:

1. authenticate before creating output directories;
2. fetch every requested date with sibling failure isolation;
3. exclusively write every successful Raw Response;
4. call `write_manifest()` after all fetches finish;
5. call `import_run()` with the in-memory manifest only after the manifest file exists;
6. exclusively write `ImportSummary.report`;
7. print value-free path/status/count lines.

In `src.derive`, define one positional `source`: a run directory normally, or a raw root when `--rebuild` is present. Defaults are `data/derived/sleep.sqlite3` and `reports`. A rebuild imports sorted run directories into `sleep.sqlite3.<random>.tmp` in the target directory and uses `os.replace()` only after every run succeeds. On failure, remove only the verified same-directory temporary file and retain the current target DB. After a successful import/rebuild, write each report to a same-directory temporary file and `os.replace()` the old value-heavy or stale report; reports are rebuildable, unlike Raw Responses and Annotations.

Delete `render_report()` and its report-only helpers from `src.analysis.py` after no caller remains. Keep timestamp and payload analysis functions/tests used by derivation.

- [ ] **Step 4: Run CLI help, focused tests, and full suite**

Run: `uv run python -m src.derive --help`

Expected: exit 0 and documented positional source, `--rebuild`, `--derived-db`, and `--report-root`.

Run: `uv run python -m unittest discover -s tests -p "test_derive.py" -v`

Expected: all derive tests pass.

Run: `uv run python -m unittest discover -s tests -v`

Expected: full suite passes with obsolete value-heavy report assertions removed, not skipped.

- [ ] **Step 5: Commit CLI integration**

```text
git add src/derive.py src/explore.py src/analysis.py tests/test_derive.py tests/test_phase0.py
git commit -m "feat: integrate derived imports with sleep CLI"
```

- [ ] **Review gate 6: Raw-write/import ordering review**

Have a fresh reviewer verify the exact Raw -> manifest -> import -> report order, atomic rebuild replacement, preservation on import failure, no Garmin dependency in `src.derive`, and value-free output. Resolve findings before Task 7.

### Task 7: Secure the local HTTP adapter and complete routes

**Files:**
- Modify: `src/dashboard.py`
- Modify: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: only the four `src.sleep_store` operations, configured filesystem paths, accepted Host names, and a per-process CSRF token.
- Produces: `GET /`, `GET /nights/<date>`, `GET /assets/dashboard.css`, `GET /assets/dashboard.js`, and `POST /nights/<date>/annotation`.

- [ ] **Step 1: Write failing route and security tests against a live ephemeral server**

Use `http.client.HTTPConnection` and a server thread. Add exact tests for:

- parser default `--host 127.0.0.1` and `--port 8765`;
- non-loopback `--host` rejected unless at least one `--allowed-host` is present;
- missing/malformed/unaccepted Host returns `400` before any store call;
- accepted Host with an optional matching numeric port succeeds;
- `GET /` redirects to the newest Night or renders an escaped empty-state page;
- detail, date/tag-filtered history, comparison query, and annotation POST/303 routes;
- absent/wrong/duplicate CSRF field returns `403` and no write;
- missing/invalid/duplicate note or tags fields returns `400` and no write;
- `Content-Length` absent/invalid returns `411`/`400`; over 16 KiB returns `413` without reading/writing further;
- invalid UTF-8 returns `400`;
- note/tag/store limit violations return `400` with short neutral German text;
- a note containing SQL punctuation and `</script><script>` persists as text, leaves tables intact, is HTML-escaped, and is JSON-script escaped as `\u003c`;
- handler logs contain no measurement, note, tag, body, query value, or payload.

- [ ] **Step 2: Run dashboard tests to verify red**

Run: `uv run python -m unittest discover -s tests -p "test_dashboard.py" -v`

Expected: FAIL on parser, Host, CSRF, POST, limits, escaping, and routes.

- [ ] **Step 3: Implement the bounded web adapter**

Build the handler in `create_server()` so tests can inject a fixed token while `main()` uses `secrets.token_urlsafe(32)`. Parse Host with `urllib.parse.urlsplit("//" + value)`, reject userinfo/path/query/fragment, compare normalized host names against the configured set, and never trust `X-Forwarded-*` headers.

For non-loopback binding, require one or more `--allowed-host` values; do not silently accept `0.0.0.0`, arbitrary DNS names, or all Host headers. Print the approved trusted-LAN assumptions at startup without logging request data.

Parse forms only as `application/x-www-form-urlencoded`, enforce the byte cap before reading, decode strict UTF-8, use `parse_qs(..., keep_blank_values=True, max_num_fields=25)`, require exactly one value for `csrf`, `note`, and `tags`, split tags on commas, and delegate final limits/normalization to `save_annotation()`.

Use `html.escape(..., quote=True)` for text/attributes. Serialize the dashboard state with `json.dumps(..., ensure_ascii=False)` then replace `&`, `<`, and `>` with `\u0026`, `\u003c`, and `\u003e` before placing it in `<script type="application/json">`. Send `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and `Cache-Control: no-store` on HTML/form responses.

Override `log_message()` to return without formatting request details. Return fixed short error bodies; never echo rejected input.

- [ ] **Step 4: Run security-focused and full tests**

Run: `uv run python -m unittest discover -s tests -p "test_dashboard.py" -v`

Expected: all route/security tests pass.

Run: `uv run python -m unittest discover -s tests -v`

Expected: full suite passes.

- [ ] **Step 5: Commit the secure adapter**

```text
git add src/dashboard.py tests/test_dashboard.py
git commit -m "feat: serve secure local sleep dashboard"
```

- [ ] **Review gate 7: Security review**

Have a fresh security reviewer inspect Host parsing, explicit LAN binding, CSRF, body limits, strict decoding, field cardinality, escaping, CSP, parameterized SQL usage through the store seam, and value-free logging. Resolve all validated findings before Task 8.

### Task 8: Implement the approved Variant-C workbench

**Files:**
- Create: `src/dashboard.css`
- Create: `src/dashboard.js`
- Modify: `src/dashboard.py`
- Modify: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: escaped embedded `NightSummary`/`NightDetail` state, local asset routes, URL query state (`from`, `to`, `tag`, repeated `compare`, `axis`).
- Produces: the approved history rail, analysis workbench, inspector, comparison mode, synchronized gap-preserving charts, and accessible responsive behavior.

- [ ] **Step 1: Write failing UI contract tests**

Assert the detail response contains semantic `<main>`, `<nav aria-label="Historie">`, central `<section aria-labelledby="analysis-title">`, inspector `<aside>`, a labelled annotation `<form>`, `aria-live` save status, coverage terms `Daten`, `Abgerufen, keine Daten`, and `Fehler`, plus the non-diagnostic German limitation.

Assert the newest three Night Dates are selected for comparison when available, explicit repeated `compare` values override the default, date/tag filters remain in links/forms, no Garmin score receives a hero/primary class, and all equal-weight metrics appear in the matrix.

Assert `/assets/dashboard.css` and `/assets/dashboard.js` return correct MIME types, `nosniff`, local content, and no `http://`, `https://`, `//`, `@import`, external font, prototype switcher, synthetic dataset, or Fetch action.

Add `seed_browser_qa(root: Path) -> None` to `tests/test_dashboard.py`. It writes the same synthetic run under `root / "raw"`, calls `import_run(root / "derived.sqlite3", run_dir, manifest)`, and leaves `root / "annotations.sqlite3"` for dashboard writes. The helper must refuse a root outside `data/qa` so it cannot overwrite arbitrary paths; add one test that passes a temporary directory outside `data/qa` and expects `ValueError` before any file is created.

- [ ] **Step 2: Run UI contract tests to verify red**

Run: `uv run python -m unittest discover -s tests -p "test_dashboard.py" -v`

Expected: FAIL on missing assets, regions, comparison defaults, and UI text.

- [ ] **Step 3: Port only Variant C into production assets**

Retain the approved visual tokens and three-region layout from prototype commit `0e4cf24`, including the light instrument-panel surface, restrained SpO2 blue, respiration copper, sleep violet, system typography, sticky rail/inspector, visible `:focus-visible`, responsive two-/one-column breakpoints, and `prefers-reduced-motion` rule. Remove the prototype flag, variant switcher, embedded synthetic values, decorative variant A/B styles, and keyboard variant cycling.

Render these panels on one shared horizontal domain: sleep stages, SpO2, respiration, heart rate, HRV, stress, and Body Battery. JavaScript must split each series at `null` values before creating SVG paths; one `null` can never be bridged. The shared cursor reads original observation/unit/source, and the axis toggle changes labels between original wall-clock and elapsed seconds only when elapsed time is derivable.

Comparison mode uses a semantic metric table plus aligned small multiples. History is newest first, supports date/tag filter submission, focused Night selection, and comparison checkboxes. Inspector owns note/tags, endpoint coverage, provenance, last successful import time, and the limitation text.

Keep all user-facing labels short and neutral, for example: `Historie`, `Nächte`, `Vergleich`, `Analyse`, `Uhrzeit`, `Seit Schlafbeginn`, `Notiz`, `Tags`, `Speichern`, `Datenlage`, `Daten`, `Abgerufen, keine Daten`, `Fehler`, and `Keine Daten verfügbar`.

- [ ] **Step 4: Run automated UI tests and browser QA with synthetic data**

Run: `uv run python -m unittest discover -s tests -p "test_dashboard.py" -v`

Expected: all dashboard tests pass.

Run: `uv run python -c "from pathlib import Path; import runpy; runpy.run_path('tests/test_dashboard.py')['seed_browser_qa'](Path('data/qa'))"`

Expected: exit 0, with synthetic ignored QA data only under `data/qa`.

Run: `uv run python -m src.dashboard --derived-db data/qa/derived.sqlite3 --annotation-db data/qa/annotations.sqlite3 --raw-root data/qa/raw`

Use browser automation to inspect desktop `1440x900`, tablet `900x1000`, and mobile `390x844`. Verify keyboard-only history/form use, visible focus, no horizontal page overflow, three-to-one-region responsive flow, reduced-motion behavior, missing panel labels, source tooltips, and that the synthetic `None` Sample renders a visible chart gap. Save no screenshot in the repository.

Run: `uv run python -m unittest discover -s tests -v`

Expected: full suite passes after browser fixes.

- [ ] **Step 5: Commit Variant C**

```text
git add src/dashboard.py src/dashboard.css src/dashboard.js tests/test_dashboard.py
git commit -m "feat: implement variant C sleep workbench"
```

- [ ] **Review gate 8: UI/accessibility review**

Have a fresh reviewer compare the running synthetic dashboard with Variant C and the approved spec. Require explicit checks for equal-weight signals, semantic structure, keyboard focus, responsive behavior, chart gaps, local-only assets, neutral German copy, and no medical interpretation. Resolve findings before Task 9.

### Task 9: Document, verify, and perform private structural acceptance

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: completed CLI/web behavior and the ignored private run through an execution-time environment variable.
- Produces: durable operating/backup/security guidance, fresh full verification evidence, and a final whole-branch review; no production code change unless verification exposes a defect.

- [ ] **Step 1: Write documentation assertions before editing README**

Add a focused `ReadmeContractTests` class to the most relevant existing test file, asserting README documents these exact commands/terms:

```text
uv run python -m src.explore --days 7
uv run python -m src.derive data/raw/<run-id>
uv run python -m src.derive data/raw --rebuild
uv run python -m src.dashboard
127.0.0.1
data/user/annotations.sqlite3
```

Also assert it states that Raw Responses are authoritative/immutable, the Derived Store is rebuildable, the Annotation Store requires backup, LAN binding is explicit and trusted-private-LAN only, internet exposure requires authentication/TLS, the dashboard has no Fetch action/credentials, reports are value-free, and the UI is observational/non-diagnostic.

- [ ] **Step 2: Run the README contract to verify red**

Run: `uv run python -m unittest discover -s tests -p "test_phase0.py" -v`

Expected: FAIL because the dashboard/derive operating guidance is absent.

- [ ] **Step 3: Update README with minimal operating guidance**

Replace the statement that the project has no dashboard. Add concise sections for:

- fetch and import order;
- retrying one run and rebuilding all runs;
- default local dashboard and explicit trusted-LAN invocation;
- Annotation Store backup/restore responsibility;
- Raw/Derived/Annotation ownership;
- value-free reports and value-free logs;
- no Fetch button, credentials, external assets, medical thresholds, diagnosis, or treatment guidance.

Do not include a private path, run ID, measurement, note, identifier, token path content, or screenshot.

- [ ] **Step 4: Run fresh repository verification**

Run: `uv sync --locked`

Expected: exit 0 with the existing lockfile unchanged.

Run: `uv run python -m unittest discover -s tests -v`

Expected: every test passes with zero failures/errors/skips.

Run: `uv run python -m compileall -q src tests`

Expected: exit 0 and no output.

Run: `uv run python -m src.explore --help`

Expected: exit 0; fetching options remain available.

Run: `uv run python -m src.derive --help`

Expected: exit 0; retry/rebuild options are present.

Run: `uv run python -m src.dashboard --help`

Expected: exit 0; loopback is the documented default and LAN options are explicit.

Run: `git diff --check`

Expected: exit 0 and no whitespace errors.

Run: `git status --short`

Expected before the documentation commit: only `README.md` and its documentation test are modified.

- [ ] **Step 5: Perform private acceptance without exposing private content**

Set `SLEEPLIKEAFEENIX_PRIVATE_RAW_ROOT` locally to the earlier ignored raw root. Do not print the variable value. Run:

```text
uv run python -m src.derive "$env:SLEEPLIKEAFEENIX_PRIVATE_RAW_ROOT" --rebuild
uv run python -m src.dashboard
```

Accept only value-free output: number of imported runs, Fetch Result state counts, Night count, metric/series name counts, report path, and server URL. Verify in the browser that history/detail/comparison/coverage render and annotations can be created/updated, then remove the acceptance annotation if it was not wanted. Do not paste values, dates, run IDs, notes, tags, identifiers, paths, payloads, or screenshots into task/review messages.

If a new Night is already available, run one deliberate local `uv run python -m src.explore --days 1` fetch; do not retry automatically after HTTP 429 or an authentication gate. Verify only that incremental import makes a newer Logical Night selectable while prior history and Annotations remain available. This optional check must not block completion when no new Night exists.

- [ ] **Step 6: Commit documentation**

```text
git add README.md tests/test_phase0.py
git commit -m "docs: document local sleep dashboard operation"
```

- [ ] **Review gate 9: Whole-branch review**

Have a fresh reviewer compare every commit and final tree with `docs/superpowers/specs/2026-09-26-sleep-dashboard-design.md`, `CONTEXT.md`, and this plan. Require separate Standards and Spec findings, then rerun all verification after fixes. Confirm `git ls-files data reports` returns no private/generated files and `git status --short` is clean.

## Execution Stop

After Review gate 9 passes, stop. Do not merge, create a pull request, publish private artifacts, or add deployment/authentication/scheduling work. Those are separate decisions.
