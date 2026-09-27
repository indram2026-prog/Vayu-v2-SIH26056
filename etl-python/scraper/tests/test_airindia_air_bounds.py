"""
Run with: python3 -m unittest scraper.tests.test_airindia_air_bounds -v

real_airindia_air_bounds_2026-09-27.json is a TRIMMED version of the actual
response Air India's live `air-bounds` search endpoint returned, captured on
your machine on 2026-09-27 and pasted back to me — same ground-truth status
as real_indigo_fare_radar_2026-09-27.json, not an invented fixture. Trimmed
from the real 26,000+ line response down to 2 flights (kept every
dictionary entry those 2 flights actually reference) purely to keep this
file small; every field present is copied verbatim from the real payload,
nothing invented.

What's deliberately kept in this trim, and why each one earns its place:
- Flight SEG-AI2951-DELBOM-...: lands at Mumbai's real "BOM" airport code,
  has 3 of its real 8 fare families kept (economy/premium-economy/business)
  — proves one flight legitimately yields multiple fare records, not one.
- Flight SEG-AI9780-DELNMI-...: lands at "NMI" (Navi Mumbai International),
  a DIFFERENT real IATA code for the same city — proves the parser
  resolves both back to route_id "DEL-BOM" via dictionaries.location's
  cityCode field, not two separate routes.
"""

from __future__ import annotations

import json
import os
import unittest

from ..xhr_parser import extract_air_india_air_bounds

_FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "real_airindia_air_bounds_2026-09-27.json"
)


class TestAirIndiaAirBounds(unittest.TestCase):
    def setUp(self):
        with open(_FIXTURE, encoding="utf-8") as f:
            self.payload = json.load(f)

    def _extract(self):
        return extract_air_india_air_bounds(self.payload)

    def test_extracts_one_record_per_fare_family_not_one_per_flight(self):
        # 2 flights kept: AI2951 (3 fare families kept) + AI9780 (3 fare
        # families kept) = 6 real, independently bookable fares.
        records = self._extract()
        self.assertEqual(len(records), 6)

    def test_navi_mumbai_airport_resolves_to_the_bom_route_not_a_phantom_route(self):
        records = self._extract()
        route_ids = {r.route_id for r in records}
        # Both flights (one landing at BOM, one at NMI) must collapse to
        # the same route_id — matches shared/routes.json's basket, which
        # has no "DEL-NMI" entry at all.
        self.assertEqual(route_ids, {"DEL-BOM"})

    def test_fares_match_the_real_captured_values(self):
        records = self._extract()
        by_family = {r.raw_ref.rsplit(":", 1)[-1]: r.fare for r in records}
        self.assertEqual(by_family["YHININ"], 6822.0)   # economy, AI2951
        self.assertEqual(by_family["PFININ"], 11218.0)  # premium economy, AI2951
        self.assertEqual(by_family["CFININ"], 61944.0)  # business, AI2951
        self.assertEqual(by_family["YXININ"], 7239.0)   # economy, AI9780
        self.assertEqual(by_family["YFININ"], 8499.0)   # economy, AI9780

    def test_travel_date_comes_from_the_flight_dictionary(self):
        records = self._extract()
        self.assertTrue(all(r.travel_date == "2026-10-15" for r in records))

    def test_airline_is_resolved_from_the_airline_dictionary(self):
        records = self._extract()
        self.assertTrue(all(r.airline == "Air India" for r in records))

    def test_fare_type_is_all_in_not_displayed(self):
        # The captured "total" already includes taxes (base + totalTaxes),
        # so this must be honestly stamped "all_in", not "displayed".
        records = self._extract()
        self.assertTrue(all(r.fare_type == "all_in" for r in records))

    def test_confidence_is_verified(self):
        records = self._extract()
        self.assertTrue(all(r.confidence == "verified" for r in records))

    def test_missing_fields_returns_empty_not_a_crash(self):
        self.assertEqual(extract_air_india_air_bounds({}), [])
        self.assertEqual(extract_air_india_air_bounds({"responsePayload": []}), [])
        self.assertEqual(
            extract_air_india_air_bounds({"responsePayload": [{}], "dictionaries": {}}), []
        )


if __name__ == "__main__":
    unittest.main()
