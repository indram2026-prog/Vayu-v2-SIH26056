"""Run with: python3 -m unittest scraper.tests.test_models -v"""

from __future__ import annotations

import unittest

from ..models import FareRecord, FareRecordError


def _make(**overrides):
    base = dict(
        route_id="DEL-BOM",
        origin="DEL",
        destination="BOM",
        airline="IndiGo",
        fare=6289.0,
        fare_type="displayed",
        travel_date="2026-10-17",
        source="makemytrip",
        method="xhr_capture",
    )
    base.update(overrides)
    return FareRecord(**base)


class TestFareRecordValidation(unittest.TestCase):
    def test_valid_record_constructs_cleanly(self):
        r = _make()
        self.assertEqual(r.fare, 6289.0)
        self.assertEqual(r.confidence, "unverified")  # default

    def test_rejects_bad_route_id(self):
        with self.assertRaises(FareRecordError):
            _make(route_id="DELBOM")

    def test_rejects_zero_or_negative_fare(self):
        with self.assertRaises(FareRecordError):
            _make(fare=0)
        with self.assertRaises(FareRecordError):
            _make(fare=-100)

    def test_rejects_fare_outside_sane_band(self):
        with self.assertRaises(FareRecordError):
            _make(fare=50)  # far too low for a real domestic fare
        with self.assertRaises(FareRecordError):
            _make(fare=250000)  # far too high

    def test_rejects_bad_fare_type(self):
        with self.assertRaises(FareRecordError):
            _make(fare_type="promotional")

    def test_rejects_bad_method(self):
        with self.assertRaises(FareRecordError):
            _make(method="telepathy")

    def test_to_dict_round_trips_all_fields(self):
        r = _make()
        d = r.to_dict()
        self.assertEqual(d["route_id"], "DEL-BOM")
        self.assertEqual(d["fare"], 6289.0)
        self.assertIn("scraped_at", d)


if __name__ == "__main__":
    unittest.main()
