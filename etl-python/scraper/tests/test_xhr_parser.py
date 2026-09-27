"""
Run with:  python3 -m unittest scraper.tests.test_xhr_parser -v
(from etl-python/, or add etl-python/ to PYTHONPATH)

Deliberately pure stdlib (unittest + json), so this actually runs and
passes in an environment with no network and no `scrapling` installed —
verified in the sandbox that built this, not just asserted to work.
"""

from __future__ import annotations

import json
import os
import unittest

from ..xhr_parser import extract_fares_from_xhr, _coerce_fare
from ..models import FareRecord, FareRecordError

_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample_xhr_payload.json")


class TestCoerceFare(unittest.TestCase):
    def test_plain_number(self):
        self.assertEqual(_coerce_fare(6289), 6289.0)
        self.assertEqual(_coerce_fare(6289.5), 6289.5)

    def test_currency_formatted_string(self):
        self.assertEqual(_coerce_fare("₹7,540"), 7540.0)

    def test_junk_string_returns_none(self):
        self.assertIsNone(_coerce_fare("Sold out"))

    def test_wrong_type_returns_none(self):
        self.assertIsNone(_coerce_fare([1, 2, 3]))
        self.assertIsNone(_coerce_fare(None))


class TestExtractFaresFromXhr(unittest.TestCase):
    def setUp(self):
        with open(_FIXTURE, encoding="utf-8") as f:
            self.payload = json.load(f)

    def _extract(self):
        return extract_fares_from_xhr(
            self.payload,
            route_id="DEL-BOM",
            origin="DEL",
            destination="BOM",
            travel_date="2026-10-17",
            source="makemytrip",
        )

    def test_finds_the_two_valid_fares_and_no_more(self):
        records = self._extract()
        # 5 flight entries in the fixture, but: IndiGo appears twice
        # (dedup -> 1), Vistara's only numeric field is a baggage weight
        # mislabeled 'amount' (rejected, out of sane band), SpiceJet's
        # fare is ₹45 (rejected, out of sane band). Net: 2 valid records.
        self.assertEqual(len(records), 2)

    def test_dedup_collapses_the_duplicate_indigo_entry(self):
        records = self._extract()
        indigo = [r for r in records if r.airline == "IndiGo"]
        self.assertEqual(len(indigo), 1)
        self.assertEqual(indigo[0].fare, 6289.0)

    def test_currency_string_fare_is_parsed_correctly(self):
        records = self._extract()
        air_india = [r for r in records if r.airline == "Air India"]
        self.assertEqual(len(air_india), 1)
        self.assertEqual(air_india[0].fare, 7540.0)

    def test_out_of_band_fares_are_rejected_not_included(self):
        records = self._extract()
        airlines = {r.airline for r in records}
        self.assertNotIn("Vistara", airlines)   # 15 (baggage kg, mislabeled)
        self.assertNotIn("SpiceJet", airlines)   # 45 (nowhere near a real fare)

    def test_every_returned_record_is_a_valid_farerecord(self):
        records = self._extract()
        for r in records:
            self.assertIsInstance(r, FareRecord)
            self.assertEqual(r.method, "xhr_capture")
            self.assertEqual(r.route_id, "DEL-BOM")

    def test_empty_payload_returns_empty_list(self):
        self.assertEqual(extract_fares_from_xhr(
            {}, route_id="DEL-BOM", origin="DEL", destination="BOM",
            travel_date="2026-10-17", source="makemytrip",
        ), [])


if __name__ == "__main__":
    unittest.main()
