# Garmin Sleep Exploration

This context describes locally fetched Garmin wellness data and the derived records used for later sleep analysis. Raw responses remain authoritative; derived records exist to make observed data compact and queryable.

## Language

**Raw Response**:
The immutable JSON returned by one Garmin endpoint for one requested date in one run.
_Avoid_: Source row, normalized response

**Fetch Result**:
The outcome of requesting one endpoint for one date: Data, Fetched No Data, or Error. A successful request does not imply that a usable observation exists.
_Avoid_: Measurement, Night

**Usable Fetch Result**:
A successful Fetch Result containing an allowlisted scalar or series that the dashboard can present. Usability is endpoint-specific and excludes identity-only payloads.
_Avoid_: Non-empty response, successful fetch

**Fetched No Data**:
A successful Fetch Result without a dashboard-usable scalar or series. It includes null responses and non-empty placeholder objects.
_Avoid_: Missing data, failed fetch, Empty Sleep Response

**Night**:
A sleep response with non-null start, end, and sleep duration fields. A Night may still lack optional metrics or time series.
_Avoid_: Sleep file, successful sleep request

**Night Date**:
The requested Garmin calendar date used to identify the same Night across repeated fetches. It does not assert whether Garmin labels the Night by bedtime or wake date.
_Avoid_: Bedtime date, wake date

**Logical Night**:
The dashboard view for one Night Date, assembled from the latest Usable Fetch Result for each endpoint. It owns the date's Annotation and retains provenance for every selected source.
_Avoid_: Run, merged response

**Metric**:
A named scalar wellness observation associated with a date or Night and traced to its Raw Response path.
_Avoid_: Column, property

**Sample**:
One ordered item from a timestamped Garmin series, retaining its source path, original timestamp evidence, and source payload.
_Avoid_: Metric, event

**Derived Store**:
A rebuildable index of runs, Fetch Results, Nights, Metrics, and raw-source paths. It is not a replacement for Raw Responses and does not own Annotations.
_Avoid_: Database of record, archive

**Annotation**:
A user-authored note and set of tags attached to a Night Date. It survives repeated fetches and Derived Store rebuilds.
_Avoid_: Garmin insight, metric

**Annotation Store**:
The durable local store for Annotations. Unlike the Derived Store, it cannot be reconstructed from Raw Responses and therefore requires backup.
_Avoid_: Derived data, cache
