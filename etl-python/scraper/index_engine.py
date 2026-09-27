"""
Stage 3 of the index pipeline: turn today's CLEAN RouteObservations (the
`clean` list from anomaly_filter.py) into one Laspeyres-type weighted index
number, plus a per-route detail row for the dashboard table.

Core design decision, per explicit product requirement (not a default I
picked): the index number is computed ONLY from routes that were actually
scraped and passed the anomaly filter THIS run. A route with no fresh data
today is shown in the dashboard's route table (falling back to its last
known price, or the placeholder base_fare from shared/routes.json if it has
never been scraped at all) tagged source="sample" — but it is EXCLUDED from
the index sum, and the basket weights of the routes that ARE included are
renormalized so they still sum to 1.0 among themselves. This keeps the
headline number an honest reflection of real-time data, at the cost of the
covered basket's composition shifting slightly run to run — that tradeoff
is made visible via `coverage_weight_pct` on every result, not hidden.

    index_value = 100 * Σ(weight_i * price_relative_i) / Σ(weight_i)
                  for i in routes with real scraped data today

    price_relative_i = today_price_i / base_price_i

`base_price_i` is the FIXED base-period price from shared/routes.json's
`base_fare` field (a placeholder until a real base-period survey exists —
see CHANGES.md) — this is what makes it a Laspeyres-type index (fixed base
prices AND fixed base weights, only current-period prices vary), as
opposed to a chained/Paasche index that would re-base every period.

No dependency on scrapling/network/Supabase — pure stdlib.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .normalize import RouteObservation


@dataclass
class RouteBasketEntry:
    route_id: str
    weight: float
    base_price: float
    origin_name: str = ""
    destination_name: str = ""


@dataclass
class RouteIndexDetail:
    route_id: str
    weight: float                 # ORIGINAL basket weight (not renormalized)
                                    # — the renormalized weight used in the
                                    # index sum is a run-level detail, not a
                                    # per-route one worth storing twice.
    base_price: float
    latest_price: Optional[float]
    price_relative: Optional[float]
    source: str                    # "scraped" | "sample"
    airlines: list[str] = field(default_factory=list)
    origin_name: str = ""
    destination_name: str = ""

    def to_dict(self) -> dict:
        return {
            "route_id": self.route_id,
            "weight": self.weight,
            "base_price": self.base_price,
            "latest_price": self.latest_price,
            "price_relative": self.price_relative,
            "source": self.source,
            "airlines": self.airlines,
            "origin_name": self.origin_name,
            "destination_name": self.destination_name,
        }


@dataclass
class IndexResult:
    observation_date: str
    base_date: str
    index_value: float
    routes_used: int
    routes_total: int
    coverage_weight_pct: float     # renormalization denominator, i.e. what
                                     # fraction of the FULL basket's weight
                                     # the index was actually computed from
    route_detail: list[RouteIndexDetail]


def compute_index(
    basket: list[RouteBasketEntry],
    clean_observations: list[RouteObservation],
    *,
    observation_date: str,
    base_date: str,
    last_known_prices: Optional[dict[str, float]] = None,
) -> IndexResult:
    """
    basket: the full 325-route weighted basket (shared/routes.json).
    clean_observations: today's anomaly-filter-passed observations —
        ONLY these count toward index_value.
    last_known_prices: route_id -> most recent price EVER observed for that
        route (from Supabase), used purely for DISPLAY fallback on routes
        with no fresh data today. None/missing means "never scraped" — that
        route falls back to its own base_price for display, clearly the
        least informative option, which is why it's the last resort.
    """
    last_known_prices = last_known_prices or {}
    obs_by_route = {o.route_id: o for o in clean_observations}

    weighted_sum = 0.0
    weight_denominator = 0.0
    total_basket_weight = sum(b.weight for b in basket) or 1.0
    route_detail: list[RouteIndexDetail] = []

    for entry in basket:
        obs = obs_by_route.get(entry.route_id)
        if obs is not None and entry.base_price > 0:
            price_relative = obs.representative_price / entry.base_price
            weighted_sum += entry.weight * price_relative
            weight_denominator += entry.weight
            route_detail.append(
                RouteIndexDetail(
                    route_id=entry.route_id,
                    weight=entry.weight,
                    base_price=entry.base_price,
                    latest_price=obs.representative_price,
                    price_relative=price_relative,
                    source="scraped",
                    airlines=obs.airlines,
                    origin_name=entry.origin_name,
                    destination_name=entry.destination_name,
                )
            )
        else:
            # No fresh, trusted data for this route today. Fall back to the
            # most recent price ever seen (if any), else the base_fare
            # placeholder — for DISPLAY only, never added into
            # weighted_sum/weight_denominator above.
            fallback_price = last_known_prices.get(entry.route_id)
            display_price = fallback_price if fallback_price is not None else entry.base_price
            display_relative = (
                display_price / entry.base_price if entry.base_price > 0 else None
            )
            route_detail.append(
                RouteIndexDetail(
                    route_id=entry.route_id,
                    weight=entry.weight,
                    base_price=entry.base_price,
                    latest_price=display_price,
                    price_relative=display_relative,
                    source="sample",
                    airlines=[],
                    origin_name=entry.origin_name,
                    destination_name=entry.destination_name,
                )
            )

    index_value = 100.0 * (weighted_sum / weight_denominator) if weight_denominator > 0 else 100.0
    coverage_weight_pct = (weight_denominator / total_basket_weight) * 100.0

    return IndexResult(
        observation_date=observation_date,
        base_date=base_date,
        index_value=index_value,
        routes_used=len(obs_by_route.keys() & {b.route_id for b in basket}),
        routes_total=len(basket),
        coverage_weight_pct=coverage_weight_pct,
        route_detail=route_detail,
    )
