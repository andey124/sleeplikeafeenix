# Garmin Sleep Exploration

This context describes locally fetched Garmin wellness data and the derived records used for later sleep analysis. Raw responses remain authoritative; derived records exist to make observed data compact and queryable.

## Language

**Raw Response**:
The immutable JSON returned by one Garmin endpoint for one requested date in one run.
_Avoid_: Source row, normalized response

**Fetch Result**:
The outcome of requesting one endpoint for one date: data, empty, or error. A successful request does not imply that a usable measurement exists.
_Avoid_: Measurement, night

**Night**:
A sleep response with non-null start, end, and sleep duration fields. A Night may still lack optional metrics or time series.
_Avoid_: Sleep file, successful sleep request

**Empty Sleep Response**:
A successful sleep response without the fields required for a Night. It records endpoint availability but does not become a null-filled Night.
_Avoid_: Missing night, zero sleep

**Metric**:
A named scalar wellness observation associated with a date or Night and traced to its Raw Response path.
_Avoid_: Column, property

**Sample**:
One ordered item from a timestamped Garmin series, retaining its source path, original timestamp evidence, and source payload.
_Avoid_: Metric, event

**Derived Store**:
A rebuildable SQLite representation of Raw Responses for querying and compact reporting. It is not a replacement for Raw Responses.
_Avoid_: Database of record, archive
