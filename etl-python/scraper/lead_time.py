"""
Lead-time (advance-purchase) analysis, pure stdlib.

Each fare quote knows the date it was observed and the date of travel, so its
lead time in days is derivable without changing the scraper. This module
buckets quotes into the standard windows (T+1, 7, 15, 30, 45) and builds the
lead-time curve: how the typical fare moves with advance-purchase days.

To remove route-mix effects, each route's price at a window is expressed
relative to THAT route's own price at a reference window (default T+30); the
curve is the median of those ratios across routes.
"""

from __future__ import annotations

import math
from datetime import date
from statistics import median
from typing import Iterable, Optional, Sequence

STANDARD_WINDOWS = (1, 7, 15, 30, 45)


def lead_days(observed_on: str, travel_date: str) -> int:
    """Whole days between observation date and travel date (ISO strings, date part used)."""
    return (date.fromisoformat(travel_date[:10]) - date.fromisoformat(observed_on[:10])).days


def nearest_window(days: int, windows: Sequence[int] = STANDARD_WINDOWS, tolerance: int = 3) -> Optional[int]:
    """Closest standard window within `tolerance` days, else None."""
    best = min(windows, key=lambda w: abs(w - days))
    return best if abs(best - days) <= tolerance else None


def lead_time_curve(
    quotes: Iterable["tuple[str, int, float]"],
    *,
    reference_window: int = 30,
    windows: Sequence[int] = STANDARD_WINDOWS,
    tolerance: int = 3,
) -> "dict[int, dict]":
    """quotes: (route_id, lead_days, price). Returns {window: {"ratio", "n_routes"}}.

    ratio is the median across routes of price(window) / price(reference_window)
    for that route. Only routes observed at both windows contribute.
    """
    per_route: "dict[str, dict[int, list[float]]]" = {}
    for route_id, days, price in quotes:
        w = nearest_window(days, windows, tolerance)
        if w is None or price <= 0:
            continue
        per_route.setdefault(route_id, {}).setdefault(w, []).append(price)

    med = {r: {w: median(ps) for w, ps in ws.items()} for r, ws in per_route.items()}
    out: "dict[int, dict]" = {}
    for w in windows:
        ratios = [m[w] / m[reference_window] for m in med.values() if w in m and reference_window in m]
        if ratios:
            out[w] = {"ratio": float(median(ratios)), "n_routes": len(ratios)}
    return out


def log_slope_per_day(curve: "dict[int, dict]") -> Optional[float]:
    """Least-squares slope of ln(ratio) on lead days: approx % fare change per extra day of advance booking.

    Negative means booking earlier is cheaper. Needs at least two windows.
    """
    pts = [(w, math.log(v["ratio"])) for w, v in curve.items() if v["ratio"] > 0]
    if len(pts) < 2:
        return None
    n = len(pts)
    mx = sum(x for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    if sxx == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in pts) / sxx
