from datetime import UTC, date, datetime
from statistics import median
from typing import Any


TIME_WORDS = ("time", "date", "gmt", "utc")
TIMESTAMP_FIELD_WORDS = TIME_WORDS + ("start", "end", "local")
RELEVANT_WORDS = (
    "sleep",
    "stage",
    "movement",
    "restless",
    "spo2",
    "respiration",
    "heartrate",
    "heart_rate",
    "stress",
    "hrv",
    "bodybattery",
    "body_battery",
)


def classify_timestamp(
    path: str, value: Any, requested_date: date
) -> dict[str, Any] | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        divisor = (
            1000
            if abs(value) >= 100_000_000_000
            else 1
            if abs(value) >= 1_000_000_000
            else None
        )
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
    if not isinstance(value, str) or not any(
        word in path.casefold() for word in TIMESTAMP_FIELD_WORDS
    ):
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
        return {
            "representation": "explicit-utc-field",
            "instant": parsed.replace(tzinfo=UTC),
        }
    return {"representation": "naive-local", "instant": None}


def summarize_intervals(instants: list[datetime]) -> dict[str, int | float]:
    duplicates = sum(right == left for left, right in zip(instants, instants[1:]))
    out_of_order = sum(right < left for left, right in zip(instants, instants[1:]))
    result: dict[str, int | float] = {
        "samples": len(instants),
        "duplicates": duplicates,
        "out_of_order": out_of_order,
    }
    unique = sorted(set(instants))
    if len(unique) < 2:
        return result
    gaps = [
        (right - left).total_seconds()
        for left, right in zip(unique, unique[1:])
    ]
    result.update(
        {
            "min_seconds": min(gaps),
            "median_seconds": median(gaps),
            "max_seconds": max(gaps),
        }
    )
    return result


def _is_scalar(value: Any) -> bool:
    return not isinstance(value, (dict, list, tuple))


def _is_empty(value: Any) -> bool:
    return value is None or (
        isinstance(value, (str, list, tuple, dict)) and not value
    )


def _series_for_list(
    path: str, value: list[Any] | tuple[Any, ...], requested_date: date
) -> tuple[str, list[datetime]] | None:
    non_empty = [item for item in value if not _is_empty(item)]
    if not non_empty:
        return None

    if all(
        isinstance(item, (list, tuple))
        and len(item) >= 2
        and _is_scalar(item[0])
        and classify_timestamp(f"{path}[][0]", item[0], requested_date) is not None
        for item in non_empty
    ):
        instants = []
        for item in non_empty:
            timestamp = classify_timestamp(f"{path}[][0]", item[0], requested_date)
            if timestamp is not None and timestamp["instant"] is not None:
                instants.append(timestamp["instant"])
        return "[0]", instants

    if not all(isinstance(item, dict) for item in non_empty):
        return None
    keys = sorted({key for item in non_empty for key in item}, key=str)
    counts = {key: 0 for key in keys}
    for key in keys:
        for item in non_empty:
            if key not in item or not _is_scalar(item[key]):
                continue
            timestamp = classify_timestamp(
                f"{path}[].{key}", item[key], requested_date
            )
            if timestamp is not None:
                counts[key] += 1
    if not counts:
        return None
    selected_key = max(keys, key=counts.__getitem__)
    if counts[selected_key] == 0:
        return None
    instants = []
    for item in non_empty:
        if selected_key not in item or not _is_scalar(item[selected_key]):
            continue
        timestamp = classify_timestamp(
            f"{path}[].{selected_key}", item[selected_key], requested_date
        )
        if timestamp is not None and timestamp["instant"] is not None:
            instants.append(timestamp["instant"])
    return str(selected_key), instants


def analyze_payload(payload: Any, requested_date: date) -> dict[str, Any]:
    observations: dict[str, dict[str, Any]] = {}
    timestamps: list[dict[str, Any]] = []
    series: list[dict[str, Any]] = []
    relevant_paths: set[str] = set()

    def walk(path: str, value: Any) -> None:
        observation = observations.setdefault(
            path,
            {"types": set(), "count": 0, "nulls": 0, "empties": 0},
        )
        observation["types"].add(type(value).__name__)
        observation["count"] += 1
        if value is None:
            observation["nulls"] += 1
        elif _is_empty(value):
            observation["empties"] += 1

        if _is_scalar(value):
            timestamp = classify_timestamp(path, value, requested_date)
            if timestamp is not None:
                timestamps.append({"path": path, "value": value, **timestamp})
            if any(word in path.casefold() for word in RELEVANT_WORDS):
                relevant_paths.add(path)
            return

        if isinstance(value, dict):
            for key, child in value.items():
                walk(f"{path}.{key}", child)
            return

        detected = _series_for_list(path, value, requested_date)
        if detected is not None:
            timestamp_path, instants = detected
            series.append(
                {
                    "path": path,
                    "timestamp_path": timestamp_path,
                    "samples": len(value),
                    "intervals": summarize_intervals(instants),
                }
            )

        for item in value:
            if detected is not None and isinstance(item, (list, tuple)):
                sample_path = f"{path}[]"
                walk(sample_path, item)
                for index, child in enumerate(item):
                    walk(f"{sample_path}[{index}]", child)
            else:
                walk(f"{path}[]", item)

    walk("$", payload)
    path_result = {
        path: {
            "types": sorted(observation["types"]),
            "count": observation["count"],
            "nulls": observation["nulls"],
            "empties": observation["empties"],
        }
        for path, observation in sorted(observations.items())
    }
    return {
        "paths": path_result,
        "timestamps": timestamps,
        "series": sorted(series, key=lambda item: item["path"]),
        "relevant_paths": sorted(relevant_paths),
    }
