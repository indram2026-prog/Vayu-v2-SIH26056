import unittest

from ..index_engine import RouteBasketEntry, compute_index
from ..normalize import RouteObservation


def _obs(route_id, price):
    return RouteObservation(
        route_id=route_id, travel_date="2026-10-18", representative_price=price,
        cheapest_price=price, most_expensive_price=price, raw_record_count=1,
        airlines=["IndiGo"], sources=["google_flights"],
    )


class TestIndexEngine(unittest.TestCase):
    def test_full_coverage_matches_simple_weighted_average(self):
        basket = [
            RouteBasketEntry("A-B", weight=0.6, base_price=10000),
            RouteBasketEntry("C-D", weight=0.4, base_price=5000),
        ]
        # A-B price unchanged (relative 1.0), C-D up 10% (relative 1.1)
        obs = [_obs("A-B", 10000), _obs("C-D", 5500)]
        result = compute_index(basket, obs, observation_date="2026-09-27", base_date="2026-09-13")
        expected = 100.0 * (0.6 * 1.0 + 0.4 * 1.1)
        self.assertAlmostEqual(result.index_value, expected, places=6)
        self.assertEqual(result.routes_used, 2)
        self.assertAlmostEqual(result.coverage_weight_pct, 100.0, places=6)

    def test_partial_coverage_renormalizes_and_excludes_missing_from_index(self):
        basket = [
            RouteBasketEntry("A-B", weight=0.5, base_price=10000),
            RouteBasketEntry("C-D", weight=0.3, base_price=5000),
            RouteBasketEntry("E-F", weight=0.2, base_price=8000),
        ]
        # Only A-B scraped today (relative 1.2); C-D and E-F have no fresh data.
        obs = [_obs("A-B", 12000)]
        result = compute_index(basket, obs, observation_date="2026-09-27", base_date="2026-09-13")
        # index computed from A-B alone, renormalized weight = 1.0
        self.assertAlmostEqual(result.index_value, 120.0, places=6)
        self.assertEqual(result.routes_used, 1)
        self.assertAlmostEqual(result.coverage_weight_pct, 50.0, places=6)
        # C-D and E-F still appear in route_detail, tagged "sample"
        detail_by_route = {d.route_id: d for d in result.route_detail}
        self.assertEqual(detail_by_route["A-B"].source, "scraped")
        self.assertEqual(detail_by_route["C-D"].source, "sample")
        self.assertEqual(detail_by_route["C-D"].latest_price, 5000)  # falls back to base_price
        self.assertEqual(detail_by_route["E-F"].source, "sample")

    def test_sample_fallback_uses_last_known_price_when_available(self):
        basket = [RouteBasketEntry("A-B", weight=1.0, base_price=10000)]
        result = compute_index(
            basket, [], observation_date="2026-09-27", base_date="2026-09-13",
            last_known_prices={"A-B": 10500},
        )
        detail = result.route_detail[0]
        self.assertEqual(detail.source, "sample")
        self.assertEqual(detail.latest_price, 10500)  # last known, not base_price
        self.assertEqual(result.index_value, 100.0)   # nothing scraped -> stays at 100

    def test_zero_coverage_holds_index_at_100(self):
        basket = [RouteBasketEntry("A-B", weight=1.0, base_price=10000)]
        result = compute_index(basket, [], observation_date="2026-09-27", base_date="2026-09-13")
        self.assertEqual(result.index_value, 100.0)
        self.assertEqual(result.coverage_weight_pct, 0.0)


if __name__ == "__main__":
    unittest.main()
