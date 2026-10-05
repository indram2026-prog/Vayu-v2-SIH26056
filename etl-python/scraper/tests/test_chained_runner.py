import os
import tempfile
import unittest
from types import SimpleNamespace

from scraper.chained_runner import compute_today, export_index_csv, try_update_chained


def detail(rid, price, w, source="scraped"):
    return SimpleNamespace(route_id=rid, latest_price=price, weight=w, source=source)


def result(day, rows):
    return SimpleNamespace(observation_date=day, route_detail=rows)


class FakeDB:
    """Minimal stand-in for the PostgREST requester."""

    def __init__(self, detail_rows=None, chained=None, fail=False):
        self.detail_rows = detail_rows or []
        self.chained = chained or {}
        self.fail = fail
        self.posts = []

    def __call__(self, url, key, method, path, *, params="", body=None, prefer=""):
        if self.fail:
            raise RuntimeError("relation daily_index_chained does not exist")
        if method == "GET" and path == "route_daily_detail":
            day = params.split("observation_date=lt.")[1].split("&")[0]
            rows = [r for r in self.detail_rows if r["observation_date"] < day and r["source"] == "scraped"]
            return sorted(rows, key=lambda r: r["observation_date"], reverse=True)
        if method == "GET" and path == "daily_index_chained":
            if "observation_date=eq." in params:
                day = params.split("observation_date=eq.")[1]
                return [{"index_value": self.chained[day]}] if day in self.chained else []
            return [{"observation_date": d, "index_value": v} for d, v in sorted(self.chained.items())]
        if method == "POST":
            self.posts.append((path, body))
            return None
        raise AssertionError((method, path))


def prev_rows(day, prices):
    return [{"route_id": r, "route_price": p, "observation_date": day, "source": "scraped"} for r, p in prices.items()]


class TestChainedRunner(unittest.TestCase):
    def test_first_ever_run_is_base(self):
        db = FakeDB()
        p = compute_today("u", "k", result("2026-10-05", [detail("A", 5000, 0.6), detail("B", 3000, 0.4)]), db)
        self.assertEqual((p.index_value, p.note), (100.0, "base"))

    def test_chains_from_previous_day_level(self):
        db = FakeDB(prev_rows("2026-10-04", {"A": 5000, "B": 3000}), {"2026-10-04": 104.0})
        p = compute_today("u", "k", result("2026-10-05", [detail("A", 5500, 0.5), detail("B", 3300, 0.5)]), db)
        self.assertAlmostEqual(p.index_value, 104.0 * 1.10, places=6)

    def test_missing_chained_history_starts_at_100(self):
        db = FakeDB(prev_rows("2026-10-04", {"A": 100}))
        p = compute_today("u", "k", result("2026-10-05", [detail("A", 110, 1.0)]), db)
        self.assertAlmostEqual(p.index_value, 110.0, places=6)

    def test_sample_rows_are_not_observations(self):
        db = FakeDB(prev_rows("2026-10-04", {"A": 100, "B": 100}), {"2026-10-04": 100.0})
        p = compute_today("u", "k", result("2026-10-05", [detail("A", 120, 0.5), detail("B", 999, 0.5, "sample")]), db)
        self.assertEqual(p.matched_items, 1)
        self.assertAlmostEqual(p.index_value, 120.0, places=6)

    def test_nothing_scraped_returns_none(self):
        self.assertIsNone(compute_today("u", "k", result("2026-10-05", [detail("A", 1, 1, "sample")]), FakeDB()))

    def test_try_update_writes_one_row(self):
        db = FakeDB(prev_rows("2026-10-04", {"A": 100}), {"2026-10-04": 100.0})
        try_update_chained("u", "k", result("2026-10-05", [detail("A", 105, 1.0)]), db)
        self.assertEqual(len(db.posts), 1)
        path, body = db.posts[0]
        self.assertEqual(path, "daily_index_chained")
        self.assertEqual(body[0]["observation_date"], "2026-10-05")

    def test_rerun_same_day_is_idempotent(self):
        db = FakeDB(prev_rows("2026-10-04", {"A": 100}), {"2026-10-04": 100.0})
        r = result("2026-10-05", [detail("A", 105, 1.0)])
        a = try_update_chained("u", "k", r, db)
        db.chained["2026-10-05"] = a.index_value        # first run's row now exists
        b = try_update_chained("u", "k", r, db)
        self.assertAlmostEqual(a.index_value, b.index_value, places=9)

    def test_failure_never_raises(self):
        self.assertIsNone(try_update_chained("u", "k", result("2026-10-05", [detail("A", 1, 1)]), FakeDB(fail=True)))

    def test_export_csv(self):
        db = FakeDB(chained={"2026-10-04": 100.0, "2026-10-05": 101.5})
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "o.csv")
            self.assertEqual(export_index_csv("u", "k", path, request=db), 2)
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(fh.read().splitlines(), ["date,index_value", "2026-10-04,100.0", "2026-10-05,101.5"])


if __name__ == "__main__":
    unittest.main()
