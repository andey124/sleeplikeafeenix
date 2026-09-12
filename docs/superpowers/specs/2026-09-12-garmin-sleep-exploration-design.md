# Garmin Sleep Exploration Phase 0 Design

## Goal

Build a small local Python CLI that authenticates with Garmin Connect, downloads several nights of available wellness data without changing field values, stores each run without overwriting earlier data, and writes a human-readable structural and timestamp report. The project performs data exploration only; it provides no dashboard, database, diagnosis, thresholds, or medical interpretation.

## Verified environment and library surface

- Use UV for the environment, dependency locking, and command execution.
- The local interpreter is Python 3.14.3. The project supports Python 3.12 or newer and will be tested locally on 3.14.
- Pin `garminconnect` to the inspected release 0.3.13 and commit `uv.lock`.
- Include `curl_cffi`, which the upstream installation instructions recommend for resilient authentication.
- The inspected `Garmin` class provides these relevant methods:
  - `get_sleep_data(cdate)`
  - `get_spo2_data(cdate)`
  - `get_respiration_data(cdate)`
  - `get_heart_rates(cdate)`
  - `get_all_day_stress(cdate)`
  - `get_hrv_data(cdate)`
  - `get_body_battery(startdate, enddate=None)`
  - `get_body_battery_events(cdate)`
  - `get_stats(cdate)`

No endpoint name may be added without verifying it against the installed class.

## Authentication

The default tokenstore is `~/.garminconnect`, overridable with `--tokenstore` or `GARMINTOKENS`. The CLI first calls `Garmin().login(tokenstore)` so valid current-format tokens require no credentials.

The existing local tokenstore contains legacy Garth files named `oauth1_token.json` and `oauth2_token.json`. A direct test with `garminconnect` 0.3.13 confirmed that this version does not load those files because it expects `garmin_tokens.json`. If token-only login fails because no current token is available, the CLI prompts interactively for email, password with `getpass`, and MFA when required. It then calls `login(tokenstore)`, allowing the library to create `garmin_tokens.json` beside the legacy files. Plaintext credentials are never written by this project.

Authentication failure stops the run before any data directory is created. Endpoint failures after successful authentication do not stop other endpoints.

## CLI and date semantics

Supported commands:

```text
uv run python -m src.explore --days 7
uv run python -m src.explore --from 2026-09-01 --to 2026-09-07
```

`--days N` includes today and the preceding `N - 1` calendar dates. `--from` and `--to` are inclusive and must be supplied together. The CLI passes each ISO date to Garmin without claiming whether Garmin labels a night by bedtime or wake date; actual sleep start and end fields in the response remain authoritative.

## Fetching and raw storage

For each date, the CLI calls the verified endpoint registry independently:

| File name | Installed method | Arguments |
| --- | --- | --- |
| `sleep.json` | `get_sleep_data` | date |
| `spo2.json` | `get_spo2_data` | date |
| `respiration.json` | `get_respiration_data` | date |
| `heart_rate.json` | `get_heart_rates` | date |
| `stress.json` | `get_all_day_stress` | date |
| `hrv.json` | `get_hrv_data` | date |
| `body_battery.json` | `get_body_battery` | date, date |
| `body_battery_events.json` | `get_body_battery_events` | date |
| `stats.json` | `get_stats` | date |

Each execution receives a UTC run ID with microsecond precision:

```text
data/raw/<run-id>/<date>/<endpoint>.json
reports/<run-id>/exploration.md
```

Files are opened with exclusive-create semantics. The library's returned JSON-compatible object is serialized only for storage: no field is renamed, removed, converted, sorted, or normalized. `None` responses are stored as JSON `null`, proving that the endpoint responded. Failed calls create no raw response file and are listed in the report and console log.

`data/`, `reports/`, `.venv/`, `.env*`, project-local token paths, and known Garmin token filenames are ignored by Git. Source, tests, documentation, `pyproject.toml`, and `uv.lock` remain public-safe.

## Structural analysis

The analyzer consumes the just-written raw files rather than in-memory responses, so the report describes exactly what was stored. It recursively records:

- JSON paths, observed container/scalar types, list lengths, and null or empty values;
- timestamp-like scalar fields and timestamp-bearing arrays;
- list-of-pair series such as `[timestamp, value]` and list-of-object series with explicit time fields;
- start/end intervals;
- original order, duplicate timestamps, and out-of-order samples;
- minimum, median, and maximum positive interval between chronologically adjacent parseable samples;
- aggregate scalar fields and field paths relevant to sleep, stage, movement/restlessness, SpO2, respiration, heart rate, stress, HRV, and Body Battery;
- explicit unit fields and unit-like suffixes as field-name evidence, never as medical interpretation.

The report may include personal values because both raw data and reports are local and ignored. Committed tests use synthetic fixtures only.

## Timestamp policy

The analyzer preserves every original timestamp and reports its representation separately:

- an ISO timestamp with `Z` or a numeric offset is timezone-aware;
- a field explicitly named GMT or UTC is classified accordingly;
- numeric values that match Unix seconds or milliseconds and resolve near the requested date are reported as evidence-backed epoch candidates;
- naive strings and fields explicitly named `Local` remain timezone-unresolved;
- paired local/GMT fields may expose an observed offset, but that offset is not silently applied to other timestamps.

Phase 0 does not create canonical timestamps. The report recommends that a later normalized record retain the original timestamp, original timezone evidence, conversion rule, and canonical UTC value. Device travel and daylight-saving transitions are reasons not to assume `Europe/Berlin` for every historical local timestamp. Seconds or minutes are sufficient for the intended future matching.

## Report

The Markdown report contains:

1. run ID, requested date range, Python version, and installed `garminconnect` version;
2. successful and failed endpoint calls per date;
3. raw file inventory;
4. per-endpoint structural paths and aggregate fields;
5. detected time series and interval statistics;
6. timestamp representations and timezone evidence;
7. direct answers, based only on observed fields, about sleep boundaries, phases, SpO2, respiration, movement/restlessness, HRV, stress, and Body Battery;
8. limitations and the future UTC-normalization recommendation.

## Code shape

Keep the implementation to the minimum useful files:

```text
README.md
pyproject.toml
uv.lock
src/__init__.py
src/garmin_client.py
src/analysis.py
src/explore.py
tests/test_phase0.py
```

`garmin_client.py` owns authentication and the explicit endpoint registry. `explore.py` owns argument validation, date iteration, exclusive raw writes, logging, and orchestration. `analysis.py` owns JSON inspection and Markdown generation. One standard-library `unittest` file protects the non-network behavior. No Dockerfile is added in Phase 0.

## Verification and live run

Development follows red-green-refactor for date selection, non-overwriting storage, endpoint failure isolation, timestamp classification, series interval analysis, and report generation. Final verification runs the full standard-library test suite and CLI help through UV.

After those checks, run the CLI against the real tokenstore. Because only legacy Garth tokens currently exist, the first current-library run requires credentials and possibly MFA in a user-controlled terminal; credentials must never be sent through chat. A successful login creates the reusable current token, then the same command fetches real Garmin data and produces the local report.
