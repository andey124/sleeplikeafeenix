import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

from garminconnect import Garmin, GarminConnectAuthenticationError

from src.garmin_client import ENDPOINTS, authenticate, fetch_date
from src.explore import build_parser, main, new_run_id, resolve_dates, write_raw
from src.analysis import (
    analyze_payload,
    classify_timestamp,
    render_report,
    summarize_intervals,
)


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

    def test_pair_series_walks_each_sample_once_at_indexed_paths(self):
        samples = [
            [1789167600000, 60],
            [1789167660000, 61],
            [1789167720000, 62],
        ]
        result = analyze_payload(
            {"heartRateValues": samples}, date(2026, 9, 12)
        )
        self.assertNotIn("$.heartRateValues[][]", result["paths"])
        self.assertEqual(
            result["paths"]["$.heartRateValues[][0]"]["count"], len(samples)
        )
        self.assertEqual(
            result["paths"]["$.heartRateValues[][1]"]["count"], len(samples)
        )
        pair_timestamps = [
            item
            for item in result["timestamps"]
            if item["path"].startswith("$.heartRateValues")
        ]
        self.assertEqual(len(pair_timestamps), len(samples))
        self.assertTrue(
            all(item["path"] == "$.heartRateValues[][0]" for item in pair_timestamps)
        )

    def test_object_timestamp_series_reports_interval_statistics(self):
        result = analyze_payload(
            {
                "heartRateSamples": [
                    {"timestampGMT": "2026-09-12 00:00:00", "value": 60},
                    {"timestampGMT": "2026-09-12 00:01:00", "value": 61},
                    {"timestampGMT": "2026-09-12 00:02:00", "value": 62},
                ]
            },
            date(2026, 9, 12),
        )
        series = next(
            item for item in result["series"] if item["path"] == "$.heartRateSamples"
        )
        self.assertEqual(series["timestamp_path"], "timestampGMT")
        self.assertEqual(series["intervals"]["median_seconds"], 60.0)

    def test_relevant_paths_include_observed_containers(self):
        result = analyze_payload(
            {
                "heartRateValues": [[1789167600000, 60]],
                "dailySleepDTO": {"deepSleepSeconds": 3600},
            },
            date(2026, 9, 12),
        )
        self.assertIn("$.heartRateValues", result["relevant_paths"])
        self.assertIn("$.dailySleepDTO", result["relevant_paths"])


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

    def test_default_range_uses_seven_dates(self):
        self.assertEqual(
            resolve_dates(days=None, start=None, end=None, today=date(2026, 9, 12)),
            [
                "2026-09-06",
                "2026-09-07",
                "2026-09-08",
                "2026-09-09",
                "2026-09-10",
                "2026-09-11",
                "2026-09-12",
            ],
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

    def test_run_id_rejects_naive_datetime(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            new_run_id(datetime(2026, 9, 12, 10, 11, 12, 345678))

    def test_raw_payload_is_preserved_and_never_overwritten(self):
        payload = {"values": [[1726099200000, None], [1726099260000, 97]]}
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            target = write_raw(run_dir, "2026-09-12", "spo2", payload)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), payload)
            with self.assertRaises(FileExistsError):
                write_raw(run_dir, "2026-09-12", "spo2", {"changed": True})


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

    def test_empty_endpoint_error_keeps_sibling_calls_isolated(self):
        calls = []

        class FakeGarmin:
            def __getattr__(self, method_name):
                def call(*args):
                    calls.append((method_name, args))
                    if method_name == "get_spo2_data":
                        raise RuntimeError()
                    return {"method": method_name, "args": list(args)}

                return call

        payloads, errors = fetch_date(FakeGarmin(), "2026-09-12")
        self.assertTrue(errors["spo2"].endswith("no details"))
        self.assertEqual(len(calls), len(ENDPOINTS))
        self.assertIn("sleep", payloads)
        self.assertIn("stats", payloads)


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

    def test_report_shows_aggregate_scalars_list_lengths_and_unit_hints(self):
        with tempfile.TemporaryDirectory() as temporary:
            raw_dir = Path(temporary) / "raw"
            write_raw(
                raw_dir,
                "2026-09-12",
                "sleep",
                {
                    "dailySleepDTO": {
                        "sleepScore": 84,
                        "sleepTimeSeconds": 28800,
                        "sleepTimeMinutes": 480,
                        "measurementMilliseconds": 60000,
                        "completionPercent": 95,
                        "completionPercentage": 95,
                        "restingHeartRateBpm": 52,
                        "unit": "seconds",
                        "heartRateValues": [
                            [1789167600000, 60],
                            [1789167660000, 61],
                        ],
                        "sleepSamples": [
                            {
                                "timestampGMT": "2026-09-12 00:00:00",
                                "value": 123,
                            }
                        ],
                    }
                },
            )
            report = render_report(
                raw_dir,
                run_id="20260912T120000000000Z",
                dates=["2026-09-12"],
                failures={},
                metadata={"python": "3.14.3", "garminconnect": "0.3.13"},
            )
        aggregate = report.split(
            "### Aggregierte Skalarwerte außerhalb von Array-Samples", 1
        )[1].split("### Listenlängen", 1)[0]
        self.assertIn("$.dailySleepDTO.sleepScore", aggregate)
        self.assertIn("Skalarwert: `84`", aggregate)
        self.assertNotIn("$.dailySleepDTO.heartRateValues[][1]", aggregate)
        self.assertNotIn("$.dailySleepDTO.sleepSamples[].value", aggregate)
        self.assertIn("$.dailySleepDTO.heartRateValues", report)
        self.assertIn("Länge: 2", report)
        for field in (
            "unit",
            "Seconds",
            "Minutes",
            "Milliseconds",
            "Percent",
            "Percentage",
            "Bpm",
        ):
            self.assertIn(field, report)

    def test_report_is_deterministic_and_keeps_empty_answer_groups_explicit(self):
        with tempfile.TemporaryDirectory() as temporary:
            raw_dir = Path(temporary) / "raw"
            write_raw(raw_dir, "2026-09-12", "z_endpoint", {"value": 1})
            write_raw(raw_dir, "2026-09-12", "a_endpoint", {"value": 2})
            arguments = {
                "run_id": "20260912T120000000000Z",
                "dates": ["2026-09-12"],
                "failures": {},
                "metadata": {},
            }
            first = render_report(raw_dir, **arguments)
            second = render_report(raw_dir, **arguments)
        inventory = first.split("## Rohdateien", 1)[1].split(
            "## Gefundene Strukturen", 1
        )[0]
        self.assertLess(inventory.index("a_endpoint.json"), inventory.index("z_endpoint.json"))
        self.assertEqual(first, second)
        self.assertGreaterEqual(
            first.count("keine passenden Felder beobachtet"), 9
        )

class CliTests(unittest.TestCase):
    def test_parser_accepts_days_and_inclusive_range(self):
        self.assertEqual(build_parser().parse_args(["--days", "7"]).days, 7)
        parsed = build_parser().parse_args(
            ["--from", "2026-09-01", "--to", "2026-09-07"]
        )
        self.assertEqual(parsed.start, date(2026, 9, 1))
        self.assertEqual(parsed.end, date(2026, 9, 7))

    def test_parser_rejects_invalid_date_and_missing_range_companion(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                build_parser().parse_args(["--from", "not-a-date", "--to", "2026-09-07"])
            with self.assertRaises(SystemExit):
                main(["--from", "2026-09-01"])

    @patch("src.explore.authenticate", side_effect=RuntimeError("login failed"))
    def test_authentication_failure_creates_no_data_or_reports(self, auth):
        with tempfile.TemporaryDirectory() as temporary:
            previous = Path.cwd()
            try:
                os.chdir(temporary)
                with self.assertRaisesRegex(RuntimeError, "login failed"):
                    main(["--days", "1"])
                self.assertFalse(Path("data").exists())
                self.assertFalse(Path("reports").exists())
            finally:
                os.chdir(previous)

    @patch("src.explore.authenticate")
    @patch("src.explore.fetch_date")
    @patch("src.explore.new_run_id", return_value="20260912T120000000000Z")
    def test_main_writes_successes_and_report_while_retaining_failures(
        self, run_id, fetch, auth
    ):
        auth.return_value = object()
        fetch.return_value = (
            {"sleep": {"dailySleepDTO": {}}},
            {"spo2": "unavailable"},
        )
        with tempfile.TemporaryDirectory() as temporary:
            previous = Path.cwd()
            try:
                os.chdir(temporary)
                stdout = io.StringIO()
                stderr = io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = main(
                        ["--from", "2026-09-12", "--to", "2026-09-12", "--tokenstore", "tokens"]
                    )
                raw = Path("data/raw/20260912T120000000000Z")
                reports = list(
                    Path("reports/20260912T120000000000Z").glob("*.md")
                )
                self.assertEqual(exit_code, 0)
                self.assertEqual(len(list(raw.rglob("sleep.json"))), 1)
                self.assertEqual(len(reports), 1)
                self.assertIn("spo2", reports[0].read_text(encoding="utf-8"))
                self.assertIn(str(raw), stdout.getvalue())
                self.assertIn(str(reports[0]), stdout.getvalue())
                self.assertIn("Fehler 2026-09-12/spo2: unavailable", stderr.getvalue())
            finally:
                os.chdir(previous)

    @patch("src.explore.authenticate")
    @patch("src.explore.fetch_date")
    @patch("src.explore.new_run_id", return_value="20260912T120000000000Z")
    def test_main_never_overwrites_existing_report(
        self, run_id, fetch, auth
    ):
        auth.return_value = object()
        fetch.return_value = ({"sleep": {"value": 1}}, {})
        with tempfile.TemporaryDirectory() as temporary:
            previous = Path.cwd()
            try:
                os.chdir(temporary)
                report_path = Path("reports/20260912T120000000000Z/exploration.md")
                report_path.parent.mkdir(parents=True)
                report_path.write_text("existing\n", encoding="utf-8")
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    with self.assertRaises(FileExistsError):
                        main(["--days", "1"])
                self.assertEqual(report_path.read_text(encoding="utf-8"), "existing\n")
            finally:
                os.chdir(previous)
