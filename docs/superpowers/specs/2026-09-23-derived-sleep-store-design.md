# Derived Sleep Store and Compact Report Design

## Goal

Create a rebuildable SQLite store from locally preserved Garmin Raw Responses and replace the per-file exploration dump with a compact, value-free report. The store must distinguish successful but empty sleep responses from actual Nights, preserve provenance and timestamp evidence, and introduce no new runtime dependency.

## Observed evidence

The 30-day run `20260923T195316920567Z` produced 270 Raw Responses covering nine endpoints. The Raw Responses occupy about 2.2 MB, while the generated Markdown report occupies about 11 MB and exceeds 83,000 lines because it repeats paths, scalar values, timestamps, and list lengths for every date.

A value-aware inspection found three Nights. The other 27 sleep responses contain the expected object shape but have null core sleep fields. The following `dailySleepDTO` fields were null in every response and provide no useful derived columns:

- `autoSleepStartTimestampGMT`
- `autoSleepEndTimestampGMT`
- `sleepQualityTypePK`
- `sleepResultTypePK`

Observed time-series coverage was uneven: Body Battery on 30 dates; respiration and stress on 15; heart rate and SpO2 on nine; sleep and HRV on three; and Body Battery events on none. Successful HTTP responses must therefore remain distinct from usable records.

The user's observation that sleep may be classified only when the watch is worn more than two hours before bedtime is a hypothesis. This project does not currently receive wear-state evidence sufficient to encode or verify that rule. Empty Sleep Responses remain unexplained rather than being attributed to watch timing.

## Scope

In scope:

- derive a local SQLite store from one or more immutable raw runs;
- record Fetch Result state and provenance;
- store only actual Nights in the Night relation;
- retain selected scalar Metrics and timestamped Samples without empty columns;
- regenerate a compact report without personal measurement values;
- import the existing 30-day run and process future runs automatically;
- keep the database, Raw Responses, and reports ignored by Git.

Out of scope:

- medical interpretation, thresholds, diagnoses, or a sleep-quality judgment;
- inferring why Garmin returned an Empty Sleep Response;
- replacing or deleting Raw Responses;
- a dashboard, server, cloud database, or synchronization service;
- treating the derived schema as a complete Garmin schema;
- committing personal data, identifiers, tokens, or reports.

## Architecture

Raw Responses remain the source of truth. A new deep module in `src/storage.py` owns schema creation, run replacement, extraction, timestamp conversion, and summary queries behind a small interface:

```python
save_run(
    database: Path,
    *,
    run_id: str,
    dates: list[str],
    raw_dir: Path,
    failures: dict[str, dict[str, str]],
    metadata: dict[str, str],
) -> None

load_run_summary(database: Path, run_id: str) -> dict[str, Any]
```

`save_run` uses one SQLite transaction. Importing an existing `run_id` deletes and replaces only that run and its dependent rows, making rebuilds idempotent without merging partially updated state. Foreign keys are enabled and child relations use cascading deletes.

The database lives at `data/derived/sleep.sqlite3`. `src.explore` writes Raw Responses first, then calls `save_run`, then renders the report from `load_run_summary`. Authentication failure still occurs before any run output. Endpoint failures still leave sibling endpoints intact.

A small rebuild command in `src/derive.py` imports an existing raw run without Garmin access:

```text
uv run python -m src.derive --run-id 20260923T195316920567Z
```

The command infers requested dates from raw date directories and expected endpoints from the existing endpoint registry. Missing files are recorded as errors with an unavailable-detail marker unless a caller supplies original failure details. It writes the same derived database and compact report as a live run.

## SQLite model

### `runs`

One row per immutable raw run:

- `run_id TEXT PRIMARY KEY`
- `requested_from TEXT NOT NULL`
- `requested_to TEXT NOT NULL`
- `created_at_utc TEXT NOT NULL`
- `python_version TEXT`
- `garminconnect_version TEXT`

### `fetches`

One row per requested date and endpoint:

- `run_id TEXT NOT NULL`
- `date TEXT NOT NULL`
- `endpoint TEXT NOT NULL`
- `state TEXT NOT NULL CHECK (state IN ('data', 'empty', 'error'))`
- `raw_path TEXT`
- `error TEXT`
- primary key: `(run_id, date, endpoint)`

`error` is populated only for failures. `raw_path` is relative to the repository. Empty top-level JSON values are `empty`. A sleep payload that lacks a Night is also `empty`, even when Garmin returned a non-empty placeholder object.

### `nights`

One row only when `dailySleepDTO.sleepStartTimestampGMT`, `sleepEndTimestampGMT`, and `sleepTimeSeconds` are all non-null:

- `run_id TEXT NOT NULL`
- `date TEXT NOT NULL`
- `start_original INTEGER NOT NULL`
- `end_original INTEGER NOT NULL`
- `start_utc TEXT NOT NULL`
- `end_utc TEXT NOT NULL`
- `timezone_evidence TEXT NOT NULL`
- `conversion_rule TEXT NOT NULL`
- `sleep_time_seconds INTEGER NOT NULL`
- `deep_sleep_seconds INTEGER`
- `light_sleep_seconds INTEGER`
- `rem_sleep_seconds INTEGER`
- `awake_sleep_seconds INTEGER`
- `unmeasurable_sleep_seconds INTEGER`
- `nap_time_seconds INTEGER`
- primary key: `(run_id, date)`

Always-null fields are absent. Optional fields remain nullable only when they have been observed with data in at least one Night.

### `metrics`

Optional scalar observations use rows rather than sparse columns:

- `run_id TEXT NOT NULL`
- `date TEXT NOT NULL`
- `scope TEXT NOT NULL CHECK (scope IN ('day', 'night'))`
- `metric TEXT NOT NULL`
- `numeric_value REAL`
- `text_value TEXT`
- `unit TEXT`
- `source_endpoint TEXT NOT NULL`
- `source_path TEXT NOT NULL`
- primary key: `(run_id, date, scope, metric, source_endpoint, source_path)`

Only allowlisted wellness Metrics are extracted: sleep score, SpO2, respiration, heart rate, stress, HRV, Body Battery, sleep movement/restlessness, and documented duration fields. Account identifiers, profile identifiers, age group, free-form insights, and unknown scalars remain only in Raw Responses.

### `samples`

Timestamped series retain ordering and source payload without requiring a wide schema for every Garmin shape:

- `run_id TEXT NOT NULL`
- `date TEXT NOT NULL`
- `source_endpoint TEXT NOT NULL`
- `series_path TEXT NOT NULL`
- `sample_index INTEGER NOT NULL`
- `timestamp_original TEXT`
- `timestamp_utc TEXT`
- `timezone_evidence TEXT NOT NULL`
- `payload_json TEXT NOT NULL`
- primary key: `(run_id, date, source_endpoint, series_path, sample_index)`

`payload_json` contains only that source sample, serialized deterministically. It preserves pair and object samples without inventing one schema per series. SQLite JSON queries can extract known values later. Empty series create no rows.

## Timestamp policy

Canonical UTC is written only when the Raw Response supplies explicit GMT/UTC evidence, an ISO offset, or a date-near Unix epoch value under the existing timestamp rules. The store retains the original timestamp representation, the evidence label, and the conversion rule. Naive local timestamps remain unresolved and have `timestamp_utc = NULL`.

Sleep boundaries use the explicit GMT fields and Unix-millisecond conversion. Local companion fields remain available in Raw Responses rather than being silently assigned a timezone.

## Compact report

The report is a summary of the selected run in the Derived Store, not a serialization of every observation. It contains:

1. run metadata and requested range;
2. endpoint counts by `data`, `empty`, and `error`;
3. raw file counts and derived row counts;
4. Night coverage, including successful sleep requests without a Night;
5. available Metric names with date coverage and units, but no values;
6. series paths with date coverage, sample counts, and interval summaries;
7. timestamp-evidence counts;
8. limitations, including the unverified watch-wear hypothesis.

The report omits:

- scalar measurement values;
- repeated per-date path listings;
- individual timestamp values;
- paths that are null or empty for the entire run;
- Empty Sleep Responses represented as Night rows;
- raw identifiers and profile fields.

Each endpoint/path appears at most once per report section. Report size should grow with schema variety, not linearly with every sample.

## Error handling and data safety

- SQLite writes occur only after Raw Responses have been safely written.
- The complete run import is transactional; failure leaves the previous version of that run intact.
- Malformed JSON aborts derivation for the run and reports the exact file path without altering Raw Responses.
- Unknown fields remain in Raw Responses and do not silently become Metrics.
- Raw files, the derived database, reports, and token paths remain ignored by Git.
- No command logs token contents or personal measurement values.

## Verification

Synthetic standard-library tests cover:

- schema creation and enabled foreign keys;
- idempotent replacement of one run without affecting another;
- a placeholder sleep payload creates an empty Fetch Result and no Night;
- a valid sleep payload creates one Night with explicit UTC evidence;
- always-null and identity fields create neither columns nor Metrics;
- allowlisted scalar Metrics retain source endpoint/path and units;
- pair and object Samples retain order, original timestamp evidence, and payload JSON;
- naive timestamps remain unresolved;
- the compact report contains coverage counts and no personal scalar values;
- one endpoint failure remains isolated;
- generated database and reports remain ignored.

After tests, the existing 30-day raw run is rebuilt locally. Verification checks that it yields three Nights, preserves all 270 Fetch Results, produces no Body Battery event Samples, and creates a materially smaller report without printing measurements.
