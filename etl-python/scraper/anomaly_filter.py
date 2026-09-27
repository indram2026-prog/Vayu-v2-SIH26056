"""
Stage 2 of the index pipeline: decide which of today's RouteObservations
(from normalize.py) are trustworthy enough to feed into index_engine.py.

Two independent checks, either one can flag-and-drop a route:

1. Day-over-day: today's representative_price vs. the last KNOWN GOOD price
   for that route (from Supabase's route_daily_detail, passed in as
   `previous_prices`). A jump bigger than `max_day_over_day_change` (default
   150%, i.e. more than 2.5x or less than 0.4x the previous price) is far
   more likely to be a parsing bug (grabbed a business-fare number, a
   multi-city itinerary total, a currency mix-up) than a genuine overnight
   fare move.

2. Cross-sectional: today's price-per-km for a route vs. every OTHER
   route's price-per-km observed in this same run, using Median Absolute
   Deviation (MAD) rather than mean/stdev because a run with only a
   handful of routes (e.g. a quick top-20 refresh) shouldn't have its
   whole distribution skewed by one bad point the way a stdev-based
   z-score would be. Skipped entirely when fewer than
   `min_routes_for_cross_check` routes were observed this run — not
   enough points for a robust "typical" to compare against.

Both checks are OFF (never fire) for a route with no prior price AND too
few peers this run — a brand new route on a very small run is neither
accepted nor rejected on evidence it doesn't have; it just passes through
unfiltered, exactly as a first observation should.

No dependency on scrapling/network — pure stdlib.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Optional

from .normalize import RouteObservation


@dataclass
class AnomalyFlag:
    route_id: str
    reason: str          # "day_over_day" | "cross_sectional"
    detail: str           # human-readable specifics, for the run report


@dataclass
class FilterResult:
    clean: list[RouteObservation]
    dropped: list[RouteObservation]
    flags: list[AnomalyFlag]


def _mad_z_scores(values: dict[str, float]) -> dict[str, float]:
    """Robust z-score per key: (x - median) / (1.4826 * MAD). The 1.4826
    constant makes MAD a consistent estimator of standard deviation for
    normally-distributed data — the standard scaling factor, not a made-up
    number."""
    if len(values) < 2:
        return {k: 0.0 for k in values}
    vals = list(values.values())
    m = median(vals)
    abs_devs = [abs(v - m) for v in vals]
    mad = median(abs_devs)
    if mad == 0:
        # Every value identical (or near enough) — nothing is an outlier
        # relative to the others.
        return {k: 0.0 for k in values}
    scale = 1.4826 * mad
    return {k: (v - m) / scale for k, v in values.items()}


def filter_anomalies(
    observations: list[RouteObservation],
    *,
    route_distance_km: dict[str, float],
    previous_prices: Optional[dict[str, float]] = None,
    max_day_over_day_change: float = 1.5,   # ±150%
    cross_sectional_z_threshold: float = 4.0,
    min_routes_for_cross_check: int = 5,
) -> FilterResult:
    previous_prices = previous_prices or {}
    flags: list[AnomalyFlag] = []
    dropped_ids: set[str] = set()

    # --- Check 1: day-over-day ---
    for obs in observations:
        prev = previous_prices.get(obs.route_id)
        if prev is None or prev <= 0:
            continue
        pct_change = (obs.representative_price - prev) / prev
        if abs(pct_change) > max_day_over_day_change:
            flags.append(
                AnomalyFlag(
                    route_id=obs.route_id,
                    reason="day_over_day",
                    detail=(
                        f"₹{prev:.0f} -> ₹{obs.representative_price:.0f} "
                        f"({pct_change * 100:+.0f}%), exceeds "
                        f"±{max_day_over_day_change * 100:.0f}% threshold"
                    ),
                )
            )
            dropped_ids.add(obs.route_id)

    # --- Check 2: cross-sectional price-per-km ---
    survivors = [o for o in observations if o.route_id not in dropped_ids]
    if len(survivors) >= min_routes_for_cross_check:
        per_km: dict[str, float] = {}
        for obs in survivors:
            dist = route_distance_km.get(obs.route_id)
            if dist and dist > 0:
                per_km[obs.route_id] = obs.representative_price / dist
        z_scores = _mad_z_scores(per_km)
        for route_id, z in z_scores.items():
            if abs(z) > cross_sectional_z_threshold:
                flags.append(
                    AnomalyFlag(
                        route_id=route_id,
                        reason="cross_sectional",
                        detail=(
                            f"price/km robust z-score {z:+.1f}, exceeds "
                            f"±{cross_sectional_z_threshold:.1f} vs. this "
                            f"run's other {len(per_km) - 1} routes"
                        ),
                    )
                )
                dropped_ids.add(route_id)

    clean = [o for o in observations if o.route_id not in dropped_ids]
    dropped = [o for o in observations if o.route_id in dropped_ids]
    return FilterResult(clean=clean, dropped=dropped, flags=flags)
