import json
from datetime import UTC, date, datetime
from pathlib import Path
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

    def walk(path: str, value: Any, *, descend: bool = True) -> None:
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
        if any(word in path.casefold() for word in RELEVANT_WORDS):
            relevant_paths.add(path)

        if _is_scalar(value):
            timestamp = classify_timestamp(path, value, requested_date)
            if timestamp is not None:
                timestamps.append({"path": path, "value": value, **timestamp})
            return
        if not descend:
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
                walk(sample_path, item, descend=False)
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


_ANSWER_GROUPS = (
    ("Schlafgrenzen", "boundaries"),
    ("Schlafphasen", "phases"),
    ("Respiration", "respiration"),
    ("SpO2", "spo2"),
    ("Bewegung/Unruhe", "movement"),
    ("Herzfrequenz", "heart_rate"),
    ("Stress", "stress"),
    ("HRV", "hrv"),
    ("Body Battery", "body_battery"),
)


def _matches_answer_group(path: str, group: str) -> bool:
    lowered = path.casefold()
    if group == "boundaries":
        return "sleep" in lowered and any(
            word in lowered
            for word in ("start", "end", "begin", "stop", "bed", "wake")
        )
    if group == "phases":
        return any(word in lowered for word in ("stage", "phase", "deep", "light", "rem"))
    if group == "respiration":
        return any(word in lowered for word in ("respiration", "breath"))
    if group == "spo2":
        return any(word in lowered for word in ("spo2", "oxygen", "saturation"))
    if group == "movement":
        return any(word in lowered for word in ("movement", "restless", "motion"))
    if group == "heart_rate":
        return any(word in lowered for word in ("heartrate", "heart_rate", "heart rate", "pulse"))
    if group == "stress":
        return "stress" in lowered
    if group == "hrv":
        return any(word in lowered for word in ("hrv", "variability"))
    return any(word in lowered for word in ("bodybattery", "body_battery", "body battery"))


def _format_number(value: int | float) -> str:
    return f"{value:g}" if isinstance(value, float) else str(value)


def _format_original(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _timestamp_evidence(representation: str) -> str:
    return {
        "iso-offset": "ISO-Wert enthält einen numerischen Offset",
        "explicit-utc-field": "Feldpfad nennt GMT oder UTC",
        "epoch-ms-candidate": "numerischer Kandidat für Unix-Epoche in Millisekunden nahe am angeforderten Datum",
        "epoch-s-candidate": "numerischer Kandidat für Unix-Epoche in Sekunden nahe am angeforderten Datum",
        "naive-local": "naiver lokaler Wert ohne auflösbare Zeitzone",
    }.get(representation, "keine weitere Zeitzonen-Evidenz")


def render_report(
    raw_dir: Path,
    *,
    run_id: str,
    dates: list[str],
    failures: dict[str, dict[str, str]],
    metadata: dict[str, str],
) -> str:
    raw_files = sorted(
        raw_dir.glob("*/*.json"), key=lambda path: path.as_posix()
    )
    analyzed_files: list[tuple[Path, str, dict[str, Any]]] = []
    for path in raw_files:
        cdate = path.parent.name
        payload = json.loads(path.read_text(encoding="utf-8"))
        analyzed_files.append(
            (
                path,
                path.relative_to(raw_dir).as_posix(),
                analyze_payload(payload, date.fromisoformat(cdate)),
            )
        )

    lines = ["# Garmin-Schlafdaten: Exploration", "", "## Lauf", "", f"- Lauf-ID: `{run_id}`"]
    lines.append(
        f"- Angeforderte Daten: {', '.join(f'`{cdate}`' for cdate in dates) or 'keine'}"
    )
    for key, value in sorted(metadata.items()):
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Abrufstatus", ""])
    files_by_date: dict[str, list[str]] = {}
    for _, relative, _ in analyzed_files:
        cdate, endpoint_json = relative.split("/", 1)
        files_by_date.setdefault(cdate, []).append(endpoint_json.removesuffix(".json"))
    status_dates = sorted(set(dates) | set(files_by_date) | set(failures))
    for cdate in status_dates:
        successes = sorted(files_by_date.get(cdate, []))
        date_failures = failures.get(cdate, {})
        successful_text = ", ".join(f"`{endpoint}`" for endpoint in successes) or "keine"
        failed_text = ", ".join(
            f"`{endpoint}` ({message})"
            for endpoint, message in sorted(date_failures.items())
        ) or "keine"
        lines.append(
            f"- `{cdate}` — erfolgreich: {successful_text}; fehlgeschlagen: {failed_text}"
        )

    lines.extend(["", "## Rohdateien", ""])
    if analyzed_files:
        lines.extend(f"- `{relative}`" for _, relative, _ in analyzed_files)
    else:
        lines.append("keine Rohdateien beobachtet")

    lines.extend(["", "## Gefundene Strukturen", ""])
    if analyzed_files:
        for _, relative, analysis in analyzed_files:
            lines.extend([f"### `{relative}`", ""])
            for path, observation in analysis["paths"].items():
                details = (
                    f"Typen: {', '.join(observation['types'])}; "
                    f"Vorkommen: {observation['count']}"
                )
                if observation["nulls"]:
                    details += f"; null: {observation['nulls']}"
                if observation["empties"]:
                    details += f"; leer: {observation['empties']}"
                lines.append(f"- `{path}` — {details}")
    else:
        lines.append("keine Strukturen beobachtet")

    lines.extend(["", "## Zeitreihen und Sampling-Intervalle", ""])
    series_found = False
    for _, relative, analysis in analyzed_files:
        for series in analysis["series"]:
            series_found = True
            intervals = series["intervals"]
            interval_text = (
                f"Minimum: {_format_number(intervals['min_seconds'])}, "
                f"Median: {_format_number(intervals['median_seconds'])}, "
                f"Maximum: {_format_number(intervals['max_seconds'])}"
                if "median_seconds" in intervals
                else "keine zwei eindeutigen Zeitstempel für positive Intervalle"
            )
            lines.append(
                f"- `{relative}` `{series['path']}` — "
                f"Zeitstempelpfad: `{series['timestamp_path']}`; "
                f"Samples: {series['samples']}; Intervalle in Sekunden: {interval_text}; "
                f"Duplikate: {intervals['duplicates']}; "
                f"außer der Reihenfolge: {intervals['out_of_order']}"
            )
    if not series_found:
        lines.append("keine Zeitreihen beobachtet")

    lines.extend(["", "## Zeitstempel und Zeitzonenhinweise", ""])
    timestamps_found = False
    representations: set[str] = set()
    for _, relative, analysis in analyzed_files:
        for timestamp in analysis["timestamps"]:
            timestamps_found = True
            representation = timestamp["representation"]
            representations.add(representation)
            lines.append(
                f"- `{relative}` `{timestamp['path']}` — "
                f"Originalwert: `{_format_original(timestamp['value'])}`; "
                f"Darstellung: `{representation}`; "
                f"Zeitzonen-Evidenz: {_timestamp_evidence(representation)}."
            )
    if representations:
        lines.append(
            f"- Beobachtete Darstellungsnamen: {', '.join(f'`{name}`' for name in sorted(representations))}"
        )
    if not timestamps_found:
        lines.append("keine Zeitstempel beobachtet")

    lines.extend(["", "## Für die Schlafanalyse relevante Felder", ""])
    relevant_found = False
    for _, relative, analysis in analyzed_files:
        for path in analysis["relevant_paths"]:
            relevant_found = True
            lines.append(f"- `{relative}` `{path}`")
    if not relevant_found:
        lines.append("keine passenden Felder beobachtet")

    lines.extend(["", "## Antworten aus den beobachteten Daten", ""])
    observed_paths = [
        (relative, path)
        for _, relative, analysis in analyzed_files
        for path in analysis["paths"]
    ]
    for label, group in _ANSWER_GROUPS:
        lines.extend([f"### {label}", ""])
        matches = sorted(
            (relative, path)
            for relative, path in observed_paths
            if _matches_answer_group(path, group)
        )
        if matches:
            lines.append("Beobachtete Pfade:")
            lines.extend(f"- `{relative}` `{path}`" for relative, path in matches)
        else:
            lines.append("keine passenden Felder beobachtet")
        lines.append("")

    lines.extend(
        [
            "## Empfehlung für spätere UTC-Normalisierung",
            "",
            "Für jeden später normalisierten Zeitstempel vier getrennte Felder beibehalten:",
            "- `Originalwert`",
            "- `Zeitzonen-Evidenz`",
            "- `Umrechnungsregel`",
            "- `Kanonischer UTC-Wert`",
            "",
            "Naive lokale Zeitstempel bleiben in Phase 0 ungeklärt; es wird keine Zeitzone geraten und keine Umrechnung angewendet.",
            "",
            "## Einschränkungen",
            "",
            "- Diese Ausführung ist eine lokale Struktur-Exploration ohne medizinische Interpretation, Diagnose oder Bewertung.",
            "- Zeitstempel werden beobachtet und klassifiziert, aber nicht als historische Ortszeit normalisiert.",
            "- Garmin-API-Antworten können instabil sein; einzelne Endpoint-Fehler werden separat ausgewiesen.",
            "- Beobachtete Felder hängen von Gerät, Konto, Region und verfügbaren Garmin-Daten ab.",
        ]
    )
    return "\n".join(lines) + "\n"
