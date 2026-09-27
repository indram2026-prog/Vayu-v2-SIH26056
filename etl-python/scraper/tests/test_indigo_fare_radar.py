"""
Run with: python3 -m unittest scraper.tests.test_indigo_fare_radar -v

Unlike sample_xhr_payload.json (a fixture I made up to test the generic
heuristic parser), real_indigo_fare_radar_2026-09-27.json is the ACTUAL
response IndiGo's live fare-radar endpoint returned, captured on your
machine on 2026-09-27 and pasted back to me. This is the one test in this
project that verifies behavior against ground truth rather than an
educated guess.
"""

from __future__ import annotations

import json
import os
import unittest

from ..xhr_parser import extract_indigo_fare_radar

_FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "real_indigo_fare_radar_2026-09-27.json"
)


class TestIndigoFareRadar(unittest.TestCase):
    def setUp(self):
        with open(_FIXTURE, encoding="utf-8") as f:
            self.payload = json.load(f)

    def test_extracts_all_six_destinations(self):
        records = extract_indigo_fare_radar(self.payload)
        self.assertEqual(len(records), 6)

    def test_route_ids_are_built_from_real_origin_and_iata(self):
        records = extract_indigo_fare_radar(self.payload)
        route_ids = {r.route_id for r in records}
        self.assertEqual(
            route_ids,
            {"DEL-JAI", "DEL-BOM", "DEL-GOI", "DEL-HYD", "DEL-BLR", "DEL-MAA"},
        )

    def test_uses_the_travel_date_indigo_reported_not_a_guessed_one(self):
        records = extract_indigo_fare_radar(self.payload)
        # Confirmed real behavior: IndiGo's response reported 2026-09-28
        # even though a completely different date (2026-10-18) was in the
        # request URL — the endpoint appears to ignore that parameter.
        for r in records:
            self.assertEqual(r.travel_date, "2026-09-28")

    def test_fares_match_the_real_captured_values(self):
        records = {r.destination: r.fare for r in extract_indigo_fare_radar(self.payload)}
        self.assertEqual(records["BOM"], 6147.0)
        self.assertEqual(records["JAI"], 3589.0)
        self.assertEqual(records["MAA"], 9682.0)

    def test_airline_is_stamped_as_indigo(self):
        records = extract_indigo_fare_radar(self.payload)
        self.assertTrue(all(r.airline == "IndiGo" for r in records))

    def test_confidence_is_verified_not_unverified(self):
        records = extract_indigo_fare_radar(self.payload)
        self.assertTrue(all(r.confidence == "verified" for r in records))

    def test_missing_fields_returns_empty_not_a_crash(self):
        self.assertEqual(extract_indigo_fare_radar({}), [])
        self.assertEqual(extract_indigo_fare_radar({"origin": "DEL"}), [])


if __name__ == "__main__":
    unittest.main()
