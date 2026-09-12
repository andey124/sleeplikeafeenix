import json
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path

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

    def test_raw_payload_is_preserved_and_never_overwritten(self):
        payload = {"values": [[1726099200000, None], [1726099260000, 97]]}
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            target = write_raw(run_dir, "2026-09-12", "spo2", payload)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), payload)
            with self.assertRaises(FileExistsError):
                write_raw(run_dir, "2026-09-12", "spo2", {"changed": True})
