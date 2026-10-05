"""
Runs the matched-model chained index alongside the existing index, once per
pipeline run, and stores it in `daily_index_chained` (see
migrations/001_fare_components.sql).

Safety contract: this must NEVER break the main pipeline. `try_update_chained`
catches every exception (missing table, network, bad data) and only prints a
warning. The existing daily_index / route_daily_detail path is untouched.

How a day is chained:
  - today's items   = routes whose source == "scraped" in today's result
                      (carried-forward "sample" prices are not observations)
  - previous items  = the scraped prices of the most recent EARLIER date
  - previous level  = that date's row in daily_index_chained, else 100
                      (the chained series starts the first day it has a
                      previous day to compare with)
Re-running the same date recomputes from the same previous day, so it is
idempotent.
"""

from __future__ import annotations

import csv
from typing import Callable, Optional

from .chained_index import ChainPoint, chain_index
from .supabase_writer import SupabaseError, _request

Requester = Callable[..., object]


def _previous_scraped(url: str, key: str, today: str, request: Requester) -> "tuple[Optional[str], dict[str, float]]":
    rows = request(
        url, key, "GET", "route_daily_detail",
        params=f"?select=route_id,route_price,observation_date&source=eq.scraped&observation_date=lt.{today}"
               "&order=observation_date.desc&limit=2000",
    ) or []
    rows = [r for r in rows if r.get("route_price")]
    if not rows:
        return None, {}
    prev_date = rows[0]["observation_date"]
    return prev_date, {r["route_id"]: float(r["route_price"]) for r in rows if r["observation_date"] == prev_date}


def _level_on(url: str, key: str, day: str, request: Requester) -> float:
    rows = request(url, key, "GET", "daily_index_chained", params=f"?select=index_value&observation_date=eq.{day}") or []
    return float(rows[0]["index_value"]) if rows else 100.0


def compute_today(url: str, key: str, result, request: Requester = _request) -> Optional[ChainPoint]:
    today = result.observation_date
    prices = {d.route_id: float(d.latest_price) for d in result.route_detail if d.source == "scraped" and d.latest_price}
    weights = {d.route_id: float(d.weight) for d in result.route_detail}
    if not prices:
        return None
    prev_date, prev_prices = _previous_scraped(url, key, today, request)
    if prev_date is None:
        return ChainPoint(today, 100.0, 1.0, len(prices), 100.0, "base")
    level = _level_on(url, key, prev_date, request)
    points = chain_index({prev_date: prev_prices, today: prices}, weights, base_value=level)
    return points[-1]


def try_update_chained(url: str, key: str, result, request: Requester = _request) -> Optional[ChainPoint]:
    try:
        point = compute_today(url, key, result, request)
        if point is None:
            print("Chained index: no scraped routes this run, skipped.")
            return None
        request(
            url, key, "POST", "daily_index_chained",
            params="?on_conflict=observation_date",
            body=[{
                "observation_date": point.date,
                "index_value": point.index_value,
                "link": point.link,
                "matched_items": point.matched_items,
                "matched_weight_pct": point.matched_weight_pct,
                "note": point.note,
            }],
            prefer="resolution=merge-duplicates",
        )
        print(f"Chained index for {point.date}: {point.index_value:.2f} "
              f"({point.matched_items} matched routes, {point.matched_weight_pct:.1f}% of weight{', ' + point.note if point.note else ''})")
        return point
    except (SupabaseError, Exception) as exc:  # noqa: BLE001 - never break the main pipeline
        print(f"Chained index skipped (main index unaffected): {exc}")
        return None


def export_index_csv(url: str, key: str, path: str, table: str = "daily_index_chained", request: Requester = _request) -> int:
    """Write date,index_value rows for scraper.backtest."""
    rows = request(url, key, "GET", table, params="?select=observation_date,index_value&order=observation_date.asc") or []
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "index_value"])
        for r in rows:
            w.writerow([r["observation_date"], r["index_value"]])
    return len(rows)


if __name__ == "__main__":
    import os
    import sys

    if len(sys.argv) < 3 or sys.argv[1] != "export":
        print("usage: python -m scraper.chained_runner export <out.csv> [daily_index_chained|daily_index]")
        raise SystemExit(2)
    u, k = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not (u and k):
        print("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set", file=sys.stderr)
        raise SystemExit(1)
    n = export_index_csv(u, k, sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "daily_index_chained")
    print(f"wrote {n} rows to {sys.argv[2]}")
