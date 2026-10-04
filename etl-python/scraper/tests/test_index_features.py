import csv
import math
import os
import tempfile
import unittest

from scraper.backtest import compare, load_dgca_csv, load_index_csv, monthly_mean
from scraper.chained_index import chain_index
from scraper.dgca_weights import apply_dgca_weights, load_traffic
from scraper.fare_components import FareBreakdown
from scraper.lead_time import STANDARD_WINDOWS, lead_days, lead_time_curve, log_slope_per_day, nearest_window


class TestChainedIndex(unittest.TestCase):
    W = {"A": 0.5, "B": 0.3, "C": 0.2}

    def test_flat_prices_with_changing_coverage_stay_at_100(self):
        # The old engine would jump here because the covered basket changes.
        days = {
            "2026-10-01": {"A": 5000, "B": 9000, "C": 3000},
            "2026-10-02": {"A": 5000},                      # only the cheap-ish route scraped
            "2026-10-03": {"B": 9000, "C": 3000},           # a different subset next day
            "2026-10-04": {"A": 5000, "B": 9000, "C": 3000},
        }
        pts = chain_index(days, self.W)
        for p in pts:
            self.assertAlmostEqual(p.index_value, 100.0, places=6)

    def test_uniform_rise_chains_correctly(self):
        days = {"2026-10-01": {"A": 100, "B": 200}, "2026-10-02": {"A": 110, "B": 220}, "2026-10-03": {"A": 121, "B": 242}}
        pts = chain_index(days, {"A": 1, "B": 1})
        self.assertAlmostEqual(pts[-1].index_value, 121.0, places=6)

    def test_weighted_geometric_link(self):
        days = {"d1": None}
        days = {"2026-10-01": {"A": 100, "B": 100}, "2026-10-02": {"A": 200, "B": 100}}
        pts = chain_index(days, {"A": 3, "B": 1})
        self.assertAlmostEqual(pts[1].link, math.exp(3 * math.log(2) / 4), places=9)

    def test_no_overlap_carries_forward(self):
        days = {"2026-10-01": {"A": 100}, "2026-10-02": {"B": 500}}
        pts = chain_index(days, {"A": 1, "B": 1})
        self.assertEqual(pts[1].note, "no_overlap")
        self.assertEqual(pts[1].index_value, 100.0)

    def test_low_coverage_flagged_not_trusted(self):
        days = {"2026-10-01": {"A": 100, "B": 100}, "2026-10-02": {"A": 150}}
        pts = chain_index(days, {"A": 1, "B": 9}, min_matched_weight_pct=50)
        self.assertEqual(pts[1].note, "low_coverage")
        self.assertEqual(pts[1].index_value, 100.0)

    def test_gap_between_dates_is_flagged(self):
        days = {"2026-10-01": {"A": 100}, "2026-10-05": {"A": 110}}
        pts = chain_index(days, {"A": 1})
        self.assertEqual(pts[1].note, "gap")

    def test_ignores_non_positive_prices(self):
        days = {"2026-10-01": {"A": 100, "B": 0}, "2026-10-02": {"A": 100, "B": 50}}
        pts = chain_index(days, {"A": 1, "B": 1})
        self.assertEqual(pts[1].matched_items, 1)


class TestLeadTime(unittest.TestCase):
    def test_lead_days(self):
        self.assertEqual(lead_days("2026-10-01T08:00:00+00:00", "2026-10-22"), 21)

    def test_nearest_window(self):
        self.assertEqual(nearest_window(7), 7)
        self.assertEqual(nearest_window(29), 30)
        self.assertIsNone(nearest_window(22))

    def test_curve_relative_to_reference(self):
        q = [("R1", 30, 1000), ("R1", 7, 1500), ("R1", 45, 900),
             ("R2", 30, 2000), ("R2", 7, 3200), ("R2", 45, 1800)]
        c = lead_time_curve(q)
        self.assertAlmostEqual(c[30]["ratio"], 1.0)
        self.assertAlmostEqual(c[7]["ratio"], 1.55)
        self.assertAlmostEqual(c[45]["ratio"], 0.9)
        self.assertEqual(c[7]["n_routes"], 2)

    def test_route_missing_reference_is_excluded(self):
        c = lead_time_curve([("R1", 7, 1500), ("R2", 30, 1000), ("R2", 7, 2000)])
        self.assertEqual(c[7]["n_routes"], 1)

    def test_slope_negative_when_early_booking_is_cheaper(self):
        c = lead_time_curve([("R", 1, 2000), ("R", 7, 1700), ("R", 15, 1400), ("R", 30, 1000), ("R", 45, 900)])
        self.assertLess(log_slope_per_day(c), 0)

    def test_slope_needs_two_windows(self):
        self.assertIsNone(log_slope_per_day({30: {"ratio": 1.0, "n_routes": 1}}))
        self.assertEqual(STANDARD_WINDOWS, (1, 7, 15, 30, 45))


class TestFareBreakdown(unittest.TestCase):
    def test_complete_breakdown_sums(self):
        f = FareBreakdown(total=6000, base_fare=4500, taxes=900, user_development_fee=300, convenience_fee=300)
        self.assertTrue(f.is_complete())
        self.assertEqual(f.price_for("ex_convenience"), 5700)
        self.assertEqual(f.price_for("base"), 4500)

    def test_partial_breakdown_allowed(self):
        f = FareBreakdown(total=6000, base_fare=4500)
        self.assertFalse(f.is_complete())
        self.assertIsNone(f.price_for("ex_convenience"))

    def test_inconsistent_total_rejected(self):
        with self.assertRaises(ValueError):
            FareBreakdown(total=6000, base_fare=4500, taxes=900, user_development_fee=300, convenience_fee=100)

    def test_components_exceeding_total_rejected(self):
        with self.assertRaises(ValueError):
            FareBreakdown(total=1000, base_fare=900, taxes=300)

    def test_negative_rejected(self):
        with self.assertRaises(ValueError):
            FareBreakdown(total=1000, base_fare=1100, taxes=-100)


class TestDgcaWeights(unittest.TestCase):
    ROUTES = [
        {"route_id": "DEL-BOM", "origin": "DEL", "destination": "BOM", "weight": 0.5},
        {"route_id": "BLR-HYD", "origin": "BLR", "destination": "HYD", "weight": 0.3},
        {"route_id": "AMD-BBI", "origin": "AMD", "destination": "BBI", "weight": 0.2},
    ]

    def _csv(self, rows):
        fh = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="", encoding="utf-8")
        w = csv.writer(fh)
        w.writerow(["origin", "destination", "passengers"])
        w.writerows(rows)
        fh.close()
        self.addCleanup(os.unlink, fh.name)
        return fh.name

    def test_directions_combined_and_weights_sum_to_one(self):
        path = self._csv([["DEL", "BOM", "300"], ["BOM", "DEL", "100"], ["BLR", "HYD", "100"]])
        routes, summary = apply_dgca_weights(self.ROUTES, load_traffic(path))
        by = {r["route_id"]: r for r in routes}
        self.assertAlmostEqual(sum(r["weight"] for r in routes), 1.0)
        self.assertAlmostEqual(by["DEL-BOM"]["weight"] / by["BLR-HYD"]["weight"], 4.0)
        self.assertEqual(by["DEL-BOM"]["weight_source"], "dgca")
        self.assertEqual(by["AMD-BBI"]["weight_source"], "gravity")
        self.assertAlmostEqual(by["AMD-BBI"]["weight"], 0.2)
        self.assertEqual(summary["routes_with_dgca"], 2)

    def test_input_routes_not_mutated(self):
        path = self._csv([["DEL", "BOM", "10"]])
        apply_dgca_weights(self.ROUTES, load_traffic(path))
        self.assertEqual(self.ROUTES[0]["weight"], 0.5)

    def test_bad_rows_skipped(self):
        path = self._csv([["DEL", "DEL", "10"], ["DEL", "BOM", "abc"], ["DEL", "BOM", "-5"], ["BLR", "HYD", "7"]])
        self.assertEqual(len(load_traffic(path)), 1)

    def test_no_matches_keeps_gravity(self):
        path = self._csv([["XXX", "YYY", "10"]])
        routes, summary = apply_dgca_weights(self.ROUTES, load_traffic(path))
        self.assertEqual(summary["routes_with_dgca"], 0)
        self.assertAlmostEqual(sum(r["weight"] for r in routes), 1.0)


class TestBacktest(unittest.TestCase):
    def test_monthly_mean(self):
        self.assertEqual(monthly_mean({"2026-09-01": 100, "2026-09-02": 110, "2026-10-01": 120}), {"2026-09": 105.0, "2026-10": 120.0})

    def test_perfect_agreement(self):
        idx = {"2026-08-15": 100.0, "2026-09-15": 110.0, "2026-10-15": 121.0}
        dgca = {"2026-08": 5000.0, "2026-09": 5500.0, "2026-10": 6050.0}
        r = compare(idx, dgca)
        self.assertEqual(r["status"], "ok")
        self.assertAlmostEqual(r["mean_abs_error_pts"], 0.0, places=6)
        self.assertAlmostEqual(r["pearson_r"], 1.0, places=6)
        self.assertEqual(r["direction_agreement"], "2/2")

    def test_single_month_reports_honestly(self):
        r = compare({"2026-10-01": 100.0}, {"2026-10": 5000.0})
        self.assertEqual(r["status"], "single_month_only")
        self.assertNotIn("pearson_r", r)

    def test_no_shared_months(self):
        self.assertEqual(compare({"2026-10-01": 100.0}, {"2026-08": 5000.0})["status"], "no_shared_months")

    def test_thirty_day_flag(self):
        idx = {f"2026-09-{d:02d}": 100.0 for d in range(1, 31)}
        self.assertTrue(compare(idx, {})["meets_30_day_requirement"])
        self.assertFalse(compare({"2026-09-01": 1.0}, {})["meets_30_day_requirement"])

    def test_csv_loaders(self):
        with tempfile.TemporaryDirectory() as d:
            ip, dp = os.path.join(d, "i.csv"), os.path.join(d, "g.csv")
            with open(ip, "w", encoding="utf-8") as fh:
                fh.write("date,index_value\n2026-10-01,100.5\n")
            with open(dp, "w", encoding="utf-8") as fh:
                fh.write('month,avg_fare\n2026-10,"5,432"\n')
            self.assertEqual(load_index_csv(ip), {"2026-10-01": 100.5})
            self.assertEqual(load_dgca_csv(dp), {"2026-10": 5432.0})


if __name__ == "__main__":
    unittest.main()
