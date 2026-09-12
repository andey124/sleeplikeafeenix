import json
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

from garminconnect import Garmin, GarminConnectAuthenticationError

from src.garmin_client import ENDPOINTS, authenticate, fetch_date
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
