"""
Run with: python3 -m unittest scraper.tests.test_google_flights_batchexecute -v

Like test_indigo_fare_radar.py and test_airindia_air_bounds.py,
real_google_flights_batchexecute_2026-09-27.json is the ACTUAL response
Google Flights' GetShoppingResults endpoint returned for a real DEL-BOM /
2026-10-18 search, captured on your machine on 2026-09-27 and pasted back
to me — not a fixture I made up. This is the file that used to report
`fares_found=0` before this parser existed; the fares were always in
there, the generic key-name heuristic just had no idea what shape to look
for in Google's batchexecute framing.
"""

from __future__ import annotations

import json
import os
import unittest

from ..xhr_parser import extract_google_flights_batchexecute

_FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "real_google_flights_batchexecute_2026-09-27.json"
)


class TestGoogleFlightsBatchexecute(unittest.TestCase):
    def setUp(self):
        with open(_FIXTURE, encoding="utf-8") as f:
            self.payload = json.load(f)

    def test_extracts_real_fares_not_zero(self):
        records = extract_google_flights_batchexecute(self.payload)
        # The live run this fixture came from reported fares_found=0 with
        # the old generic parser; this is the regression this test guards.
        self.assertGreater(len(records), 0)

    def test_dedups_flights_repeated_across_frames(self):
        # The real payload restates several of the same flights across
        # six separate "wrb.fr" frames (confirmed by eye: SG802, AI2963,
        # 6E675 etc. each appear more than once in the raw file). Without
        # dedup this would wildly overcount.
        records = extract_google_flights_batchexecute(self.payload)
        signatures = [(r.airline, r.raw_ref, r.travel_date) for r in records]
        self.assertEqual(len(signatures), len(set(signatures)))

    def test_route_is_del_bom(self):
        records = extract_google_flights_batchexecute(self.payload)
        self.assertTrue(all(r.route_id == "DEL-BOM" for r in records))
        self.assertTrue(all(r.origin == "DEL" and r.destination == "BOM" for r in records))

    def test_travel_date_matches_the_real_search(self):
        records = extract_google_flights_batchexecute(self.payload)
        self.assertTrue(all(r.travel_date == "2026-10-18" for r in records))

    def test_fares_are_in_the_real_sane_band_not_raw_x10(self):
        # The raw ints in the payload (e.g. 86974, 122000, 161000) are
        # 10x too large for FareRecord's own sanity band and would have
        # been rejected outright were they not divided by 10 first.
        records = extract_google_flights_batchexecute(self.payload)
        for r in records:
            self.assertTrue(1000.0 <= r.fare <= 100000.0, f"{r.airline} fare {r.fare} outside sane band")

    def test_finds_all_five_real_airlines(self):
        records = extract_google_flights_batchexecute(self.payload)
        airlines = {r.airline for r in records}
        self.assertEqual(
            airlines,
            {"SpiceJet", "Akasa Air", "Air India", "IndiGo", "Air India Express"},
        )

    def test_confidence_is_verified_not_unverified(self):
        records = extract_google_flights_batchexecute(self.payload)
        self.assertTrue(all(r.confidence == "verified" for r in records))

    def test_connection_itinerary_reports_outer_route_not_the_layover(self):
        # IX1165|IX1027 connects DEL -> LKO -> BOM; the real payload's own
        # outer origin/destination fields already say DEL/BOM, and this
        # must not get reported as DEL-LKO.
        records = extract_google_flights_batchexecute(self.payload)
        connecting = [r for r in records if "IX1165" in r.raw_ref]
        self.assertEqual(len(connecting), 1)
        self.assertEqual(connecting[0].route_id, "DEL-BOM")

    def test_missing_or_malformed_payload_returns_empty_not_a_crash(self):
        self.assertEqual(extract_google_flights_batchexecute({}), [])
        self.assertEqual(extract_google_flights_batchexecute([]), [])
        self.assertEqual(extract_google_flights_batchexecute([["wrb.fr", None, "not json"]]), [])
        self.assertEqual(extract_google_flights_batchexecute(None), [])


if __name__ == "__main__":
    unittest.main()
