import unittest

from ..models import FareRecord
from ..normalize import normalize_records


def _fr(route_id, airline, fare, source="google_flights"):
    return FareRecord(
        route_id=route_id, origin=route_id.split("-")[0], destination=route_id.split("-")[1],
        airline=airline, fare=fare, fare_type="displayed", travel_date="2026-10-18",
        source=source, method="xhr_capture",
    )


class TestNormalize(unittest.TestCase):
    def test_groups_by_route_and_takes_median(self):
        records = [
            _fr("DEL-BOM", "IndiGo", 8700),
            _fr("DEL-BOM", "Akasa Air", 8600),
            _fr("DEL-BOM", "Air India", 16100),
            _fr("BLR-HYD", "IndiGo", 4200),
        ]
        obs = normalize_records(records)
        by_route = {o.route_id: o for o in obs}
        self.assertEqual(set(by_route), {"DEL-BOM", "BLR-HYD"})
        delbom = by_route["DEL-BOM"]
        self.assertEqual(delbom.representative_price, 8700)  # median of [8600,8700,16100]
        self.assertEqual(delbom.cheapest_price, 8600)
        self.assertEqual(delbom.most_expensive_price, 16100)
        self.assertEqual(delbom.raw_record_count, 3)
        self.assertEqual(delbom.airlines, ["Air India", "Akasa Air", "IndiGo"])
        self.assertEqual(delbom.sources, ["google_flights"])

    def test_multiple_sources_recorded(self):
        records = [_fr("DEL-BOM", "IndiGo", 8700, source="google_flights"),
                   _fr("DEL-BOM", "IndiGo", 8750, source="indigo")]
        obs = normalize_records(records)
        self.assertEqual(obs[0].sources, ["google_flights", "indigo"])

    def test_empty_input(self):
        self.assertEqual(normalize_records([]), [])


if __name__ == "__main__":
    unittest.main()
