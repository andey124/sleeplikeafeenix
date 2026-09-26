# Sleep Dashboard and Lean Derived Store Design

## Status

Approved in conversation on 2026-09-26. This design supersedes
`2026-09-23-derived-sleep-store-design.md`.

The selected interface is prototype variant C: a history rail, central analysis
workbench, and annotation/data inspector. The prototype is retained separately
on branch `codex/sleep-dashboard-prototype` at commit `0e4cf24` and is not
production code.

## Goal

Build a local web application for reviewing and comparing recorded Garmin Nights,
with sleep structure, SpO2, respiration, HRV, heart rate, stress, and Body Battery
given equal prominence. Preserve immutable Raw Responses as the source of truth,
make repeated fetches and missing coverage explicit, and allow durable notes and
tags such as contextual observations about alcohol, training, illness, or late
meals.

The application is observational. It does not detect breathing pauses, calculate
apnea events or risk scores, apply medical thresholds, diagnose a condition, or
recommend treatment. Garmin Pulse Ox data is recreational rather than diagnostic;
concerns about sleep apnea require clinical evaluation and appropriate sleep
testing.

Safety references:

- [Garmin Pulse Ox guidance](https://support.garmin.com/nb-NO/?faq=SK2Y9a9aBp5D6n4sXmPBG7)
- [American Academy of Sleep Medicine position on home sleep apnea testing](https://aasm.org/advocacy/position-statements/clinical-use-of-a-home-sleep-apnea-test-an-updated-american-academy-of-sleep-medicine-position-statement/)

## User outcome

The application succeeds when the user can:

1. see the latest recorded Nights and older history;
2. compare several Nights across both sleep structure and physiological signals;
3. inspect one Night on synchronized time axes without hidden interpolation;
4. distinguish Data, Fetched No Data, and Error Fetch Results;
5. add notes and tags that survive refetches and rebuilds; and
6. refresh data with the existing CLI while the dashboard remains a separate
   process with no access to Garmin credentials.

## Evidence and constraints

The private 30-day acceptance dataset contains three Nights and sparse endpoint
coverage. It is sufficient to validate the real Garmin shapes but remains ignored
by Git and must never be copied into fixtures, messages, screenshots, or commits.
Synthetic fixtures cover committed tests.

Raw Responses remain immutable and exclusive. A failed endpoint must not prevent
sibling responses from being preserved. Original timestamps and their timezone
evidence remain available; naive local timestamps are not silently assigned
`Europe/Berlin` or another timezone.

The project continues to use UV and Python 3.12 or newer. Version 1 adds no runtime
dependency: SQLite, HTTP serving, HTML escaping, URL/form parsing, CSRF-token
generation, and JSON handling all use the Python standard library. The browser
uses native HTML, CSS, JavaScript, and SVG with no CDN or external asset request.

## Scope

In scope:

- immutable run manifests beside future Raw Responses;
- a lean, rebuildable Derived Store;
- a separate durable Annotation Store;
- compact value-free run reports;
- a local web application based on prototype variant C;
- latest-usable selection across repeated fetches;
- historical Night selection and date/tag filtering;
- Night comparison and synchronized detail charts;
- explicit local-only and trusted-LAN runtime modes.

Out of scope:

- periodic scheduling or a background daemon;
- a Fetch button in the web application;
- homelab packaging, reverse-proxy configuration, or internet exposure;
- application authentication for a trusted-LAN deployment;
- medical interpretation, thresholds, alerts, or event detection;
- storing every time-series Sample in SQLite;
- cloud storage, multi-user annotations, or synchronization;
- deleting or replacing Raw Responses.

## Domain language

`CONTEXT.md` defines the canonical terms. In particular:

- a Fetch Result is Data, Fetched No Data, or Error;
- a Night requires non-null sleep start, end, and duration fields;
- a Night Date correlates repeated fetches without claiming bedtime/wake-date
  semantics;
- a Logical Night selects the latest Usable Fetch Result per endpoint for one
  Night Date; and
- an Annotation is user-authored and is not derived data.

## Architecture

Three commands remain separate processes:

```text
Garmin -> src.explore -> immutable Raw Responses + run manifest
                         -> shared import_run() -> Derived Store + compact report

existing raw run -> src.derive -> shared import_run() -> Derived Store + compact report

browser <-> src.dashboard -> Derived Store + Raw Responses + Annotation Store
```

`src.explore` may call the importer only after every successful Raw Response and
the immutable run manifest have been safely written. Import failure does not alter
Raw Responses. `src.derive` offers the same import path without Garmin access, so
an import can be retried or the Derived Store can be rebuilt.

`src.dashboard` never imports `src.garmin_client`, reads token paths, or performs a
network request. It reads derived metadata and selected Raw Responses and writes
only Annotations.

### Deep module interface

`src/sleep_store.py` hides schemas, endpoint-specific usability classification,
latest-usable selection, raw-shape extraction, and transactions behind four
operations:

```python
import_run(derived_database, raw_run_dir, manifest=None) -> ImportSummary
list_nights(derived_database, annotation_database, filters) -> list[NightSummary]
load_night_detail(derived_database, raw_root, night_date) -> NightDetail
save_annotation(derived_database, annotation_database, night_date, note, tags) -> Annotation
```

The exact dataclass fields are fixed by the implementation plan, but callers do
not query tables or interpret Garmin JSON shapes themselves. Tests exercise the
same interface used by both CLIs and the web adapter.

No repository interface, adapter hierarchy, factory, or dependency-injection
container is introduced. SQLite and the local filesystem are the only concrete
implementations.

## Immutable run manifest

Future runs add `data/raw/<run-id>/manifest.json` after endpoint fetching finishes.
The manifest is exclusively created and contains:

- run ID and UTC creation time;
- requested inclusive date range;
- Python and `garminconnect` versions;
- expected endpoint names from the verified endpoint registry; and
- each date/endpoint Fetch Result state plus a sanitized error description when
  applicable.

The manifest contains no credentials, token material, personal identifiers, or
measurement values. Endpoint JSON files remain unchanged. Existing complete runs
without a manifest can be imported by inferring requested dates from date
directories and expected endpoints from the registry; a missing expected file is
an Error with unavailable detail because the original CLI attempted every
registered endpoint, while the unavailable error text is not reconstructed.

## Fetch Result classification

Classification is value-aware and endpoint-specific:

- **Data**: the response contains at least one allowlisted dashboard scalar or
  series for that endpoint;
- **Fetched No Data**: Garmin returned successfully, but the response is null,
  empty, identity-only, or a non-empty placeholder without usable values; and
- **Error**: the endpoint call failed and therefore produced no endpoint JSON.

For `sleep`, Data additionally requires a Night: non-null
`dailySleepDTO.sleepStartTimestampGMT`, `sleepEndTimestampGMT`, and
`sleepTimeSeconds`. A placeholder sleep object becomes Fetched No Data and never a
null-filled Night.

Identity fields, profile fields, free-form Garmin insights, and unknown scalars do
not make a Fetch Result usable and are not copied into the Derived Store.

## Persistence

### Raw Responses

Original time series and scalar payloads remain only at:

```text
data/raw/<run-id>/<date>/<endpoint>.json
```

They are authoritative, immutable, and ignored by Git. Night detail reads the
selected source files on demand. The dashboard never rewrites them and does not
duplicate time-series Samples into SQLite.

### Derived Store

`data/derived/sleep.sqlite3` is rebuildable and ignored by Git. It contains:

#### `runs`

- `run_id TEXT PRIMARY KEY`
- `requested_from TEXT NOT NULL`
- `requested_to TEXT NOT NULL`
- `created_at_utc TEXT NOT NULL`
- `python_version TEXT`
- `garminconnect_version TEXT`

#### `fetches`

- `run_id TEXT NOT NULL`
- `date TEXT NOT NULL`
- `endpoint TEXT NOT NULL`
- `state TEXT NOT NULL CHECK (state IN ('data', 'fetched_no_data', 'error'))`
- `raw_path TEXT`
- `error TEXT`
- primary key: `(run_id, date, endpoint)`

`raw_path` is relative to the configured raw root. It exists only for successful
responses. `error` exists only for Error Fetch Results.

#### `nights`

One row per captured Night version:

- `run_id TEXT NOT NULL`
- `night_date TEXT NOT NULL`
- original and canonical sleep start/end values;
- timestamp evidence and conversion rule;
- total and stage durations; and
- primary key: `(run_id, night_date)`.

Always-null fields, identity values, and Garmin prose are excluded.

#### `metrics`

Allowlisted comparison scalars use date-scoped rows rather than sparse columns:

- `run_id TEXT NOT NULL`
- `date TEXT NOT NULL`
- `scope TEXT NOT NULL CHECK (scope IN ('day', 'night'))`
- `metric TEXT NOT NULL`
- exactly one numeric or text value;
- `unit TEXT`;
- `source_endpoint TEXT NOT NULL`;
- `source_path TEXT NOT NULL`; and
- primary key across run, date, metric, endpoint, and path.

Metrics are extracted from every Data Fetch Result, whether or not that run also
contains a Night for the date. This permits a Logical Night to combine an older
Night with a newer usable SpO2, respiration, HRV, stress, or Body Battery result.

The initial allowlist covers sleep score and durations, SpO2, respiration, resting
heart rate, HRV, stress, Body Battery, and movement/restlessness summaries that
were observed in the private acceptance data. Unknown values remain in Raw
Responses until a dashboard requirement justifies adding them.

### Annotation Store

`data/user/annotations.sqlite3` is durable, ignored by Git, and not deleted or
recreated by derivation. It contains one annotation per Night Date:

- `night_date TEXT PRIMARY KEY`
- `note TEXT NOT NULL`
- `tags_json TEXT NOT NULL`
- `updated_at_utc TEXT NOT NULL`

Tags are trimmed, non-empty, case-insensitively deduplicated, and retain their
first entered display spelling. The application documents this database as the
only generated file requiring backup.

## Latest-usable selection

The default dashboard resolves each date/endpoint independently to its newest Data
Fetch Result by run creation time. Newer Fetched No Data and Error results remain
visible in provenance and coverage history but do not hide an older Usable Fetch
Result.

This may assemble a Logical Night from endpoint responses captured in different
runs. Every summary and chart retains its endpoint, run ID, requested date, source
path, and timestamp evidence so the combination is explicit rather than presented
as one Garmin response.

All captured Night Dates remain selectable. Repeated versions are retained for
provenance but version-comparison UI is not part of version 1.

## Timestamp and chart policy

Canonical UTC is created only from explicit GMT/UTC fields, ISO offsets, or
date-near Unix epochs under the existing conservative rules. Original timestamp,
timezone evidence, conversion rule, and canonical UTC remain distinct. Naive
local timestamps stay unresolved.

Night detail displays stacked panels on one shared horizontal domain:

1. sleep stages;
2. SpO2;
3. respiration;
4. heart rate and HRV where available;
5. stress; and
6. Body Battery.

Separate panels avoid misleading dual-axis overlays. Missing Samples remain gaps;
the application never interpolates them. A shared cursor and tooltip expose the
original observation, unit, and source. The user can switch between original
wall-clock labels and elapsed time since the Night's recorded start.

The application does not draw medical reference lines, highlight suspected
events, or label a value as normal or abnormal.

## User interface

The selected variant C has three regions:

### History rail

- lists all Logical Nights newest first;
- shows date, total sleep, compact SpO2 and respiration summaries, and tags;
- filters by date range and tag;
- selects one focused Night; and
- allows several Nights to be selected for comparison.

The initial comparison selection is the latest three Nights when available.

### Analysis workbench

Detail mode shows the selected Night's equal-weight summary metrics and synchronized
signal panels. Comparison mode replaces the detail with a metric matrix and aligned
small multiples for the selected Nights. No single Garmin score acts as the page's
primary judgment.

### Inspector

- edits the focused Night's note and tags;
- shows endpoint coverage and provenance;
- labels Fetched No Data and Error distinctly; and
- repeats the non-diagnostic limitation without marketing or alarmist copy.

The interface uses short German labels, keyboard-visible focus, semantic tables and
forms, responsive layouts, and reduced-motion support. The visual system follows
the approved prototype: a light instrument-panel surface, restrained blue for
SpO2, copper for respiration, violet for sleep structure, local system typography,
and no decorative imagery.

## Web runtime and security

The default command binds only to loopback:

```text
uv run python -m src.dashboard
```

The server uses `127.0.0.1` by default. Binding to a home-LAN interface requires an
explicit host option. A trusted-LAN deployment may run without application
authentication or TLS under these assumptions:

- the host is reachable only from the user's private home LAN;
- no router port forwarding exposes it;
- no public tunnel or internet-facing reverse proxy exposes it; and
- access by other devices or guests on that LAN is accepted.

Authentication and TLS become required before any exposure beyond that boundary.
Homelab deployment mechanics remain future work.

Even on loopback or a trusted LAN, the web adapter:

- accepts only configured local/LAN Host headers;
- uses a per-process CSRF token for annotation writes;
- limits note length, tag count, and tag length;
- escapes all raw, derived, and user-authored text;
- uses parameterized SQLite statements;
- serves no external scripts, fonts, images, analytics, or requests; and
- never logs measurement values, notes, tags, or raw payloads.

## Compact report

The importer replaces the existing value-heavy exploration dump with one compact,
value-free report per run. It contains:

- run metadata and requested range;
- endpoint counts by Data, Fetched No Data, and Error;
- raw file and derived row counts;
- Night coverage;
- Metric names with date coverage and units, without values;
- available series names with date coverage, without Samples;
- timestamp-evidence counts; and
- limitations, including the non-diagnostic boundary.

Each endpoint, Metric, or series appears at most once per section. Report size
grows with schema variety, not with every Sample.

## Error handling and data safety

- Raw Response and manifest writes complete before import starts.
- Importing one run is one SQLite transaction. Failure preserves the prior Derived
  Store state and all Raw Responses.
- Re-importing one run replaces only that run's derived rows and is idempotent.
- Malformed JSON names the affected file without printing its content.
- One malformed detail source produces an unavailable chart panel rather than
  crashing unrelated history or annotations.
- Annotation writes are transactional and never participate in derivation.
- The UI displays the last successful import time so stale state is visible.
- Neither CLI nor web logs contain credentials or personal measurements.

## Verification

Standard-library `unittest` with synthetic fixtures covers:

- schema creation and foreign-key enforcement;
- run-manifest serialization without measurements or secrets;
- endpoint-specific Data versus Fetched No Data classification;
- placeholder sleep responses creating no Night;
- transactional and idempotent run replacement;
- latest-usable selection when newer results are empty or errors;
- Logical Nights assembled from multiple source runs with provenance;
- Night summary extraction and raw time-series loading;
- preservation of series order, gaps, original timestamps, and timezone evidence;
- Annotation create/update, tag normalization, and survival across Derived Store
  rebuilds;
- compact reports containing coverage but no values;
- loopback default, Host validation, CSRF validation, escaping, and input limits;
- dashboard history, detail, comparison, and annotation routes; and
- existing Phase-0 behavior and endpoint-failure isolation.

Browser verification checks variant-C information hierarchy, keyboard navigation,
responsive layout, and chart-gap rendering with synthetic data.

The private acceptance run verifies structural counts and successful rendering
without printing values. A later new Night verifies that a repeated incremental
fetch becomes the latest Logical Night while prior history and Annotations remain
available.

## Implementation boundary

This document approves writing a separate implementation plan. It does not approve
production implementation yet. The implementation plan must preserve test-first
development, UV, Git, independent review gates, and the no-push/no-PR rule unless
the user explicitly requests those external actions.
