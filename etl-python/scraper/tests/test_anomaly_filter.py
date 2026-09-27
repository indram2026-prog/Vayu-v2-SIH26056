import unittest

from ..anomaly_filter import filter_anomalies
from ..normalize import RouteObservation


def _obs(route_id, price):
    return RouteObservation(
        route_id=route_id, travel_date="2026-10-18", representative_price=price,
        cheapest_price=price, most_expensive_price=price, raw_record_count=1,
        airlines=["IndiGo"], sources=["google_flights"],
    )


class TestAnomalyFilter(unittest.TestCase):
    def test_day_over_day_spike_dropped(self):
        obs = [_obs("DEL-BOM", 8700), _obs("BLR-HYD", 4200)]
        result = filter_anomalies(
            obs,
            route_distance_km={"DEL-BOM": 1150, "BLR-HYD": 500},
            previous_prices={"DEL-BOM": 8500, "BLR-HYD": 500},  # BLR-HYD: 500->4200 = +740%
        )
        clean_ids = {o.route_id for o in result.clean}
        self.assertIn("DEL-BOM", clean_ids)
        self.assertNotIn("BLR-HYD", clean_ids)
        self.assertEqual(result.flags[0].reason, "day_over_day")

    def test_no_previous_price_passes_through(self):
        obs = [_obs("DEL-BOM", 8700)]
        result = filter_anomalies(obs, route_distance_km={"DEL-BOM": 1150})
        self.assertEqual(len(result.clean), 1)
        self.assertEqual(len(result.dropped), 0)

    def test_cross_sectional_outlier_dropped(self):
        # 6 routes, similar price/km, one wildly off (10x) -> should get
        # flagged even with no previous-day history at all.
        normal = [
            ("A-B", 5000, 1000), ("C-D", 5200, 1000), ("E-F", 4800, 1000),
            ("G-H", 5100, 1000), ("I-J", 4900, 1000),
        ]
        obs = [_obs(rid, price) for rid, price, _ in normal]
        obs.append(_obs("X-Y", 50000))  # price/km = 50 vs ~5 for everyone else
        distances = {rid: dist for rid, _, dist in normal}
        distances["X-Y"] = 1000
        result = filter_anomalies(obs, route_distance_km=distances, min_routes_for_cross_check=5)
        clean_ids = {o.route_id for o in result.clean}
        self.assertNotIn("X-Y", clean_ids)
        self.assertEqual(len(result.clean), 5)

    def test_too_few_routes_skips_cross_sectional(self):
        obs = [_obs("A-B", 5000), _obs("X-Y", 50000)]
        result = filter_anomalies(obs, route_distance_km={"A-B": 1000, "X-Y": 1000}, min_routes_for_cross_check=5)
        # Only 2 routes < min_routes_for_cross_check=5 -> no cross-sectional check fires
        self.assertEqual(len(result.clean), 2)


if __name__ == "__main__":
    unittest.main()
