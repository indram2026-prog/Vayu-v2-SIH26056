"""
Matched-model chained price index (pure stdlib).

Problem with the current engine (index_engine.compute_index): each day only the
routes scraped that day count, with weights renormalised. When coverage changes
from one day to the next, the index moves because the BASKET changed, not
because prices changed.

This module fixes that the way statistical offices do: compare like with like.
For each pair of consecutive observation dates, only items priced on BOTH dates
(the "matched" set) contribute to the day-over-day link, and the links are
chained into a running index.

    link_t  = exp( sum_i w_i * ln(p_i,t / p_i,t-1) / sum_i w_i )   over matched i
    I_t     = I_(t-1) * link_t,   I_base = 100

The weighted geometric mean (Jevons-type) is the elementary-aggregate formula
used for CPI. An "item" is whatever the caller keys on: a route ("DEL-BOM") or a
route at one lead window ("DEL-BOM|T+7"), so lead-time windows chain separately
instead of being mixed.

Additive module: nothing in the existing pipeline imports it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Mapping, Optional


@dataclass(frozen=True)
class ChainPoint:
    date: str
    index_value: float
    link: float                 # day-over-day relative (1.0 = unchanged)
    matched_items: int
    matched_weight_pct: float   # share of total basket weight that was matched
    note: str = ""              # "", "base", "no_overlap", "gap"


def chain_index(
    daily_prices: Mapping[str, Mapping[str, float]],
    weights: Mapping[str, float],
    *,
    base_value: float = 100.0,
    min_matched_weight_pct: float = 0.0,
) -> "list[ChainPoint]":
    """daily_prices: {iso_date: {item_key: price}}; weights: {item_key: weight}.

    Dates with no data are simply absent. Items missing from `weights` get
    weight 1.0. If a day has no item in common with the previous observed day,
    the index is carried forward unchanged and the point is flagged
    "no_overlap". If matched weight is below `min_matched_weight_pct`, the day
    is also carried forward and flagged "low_coverage" rather than trusted.
    """
    total_weight = sum(weights.values()) or 0.0
    points: "list[ChainPoint]" = []
    prev_date: Optional[str] = None
    prev_prices: Mapping[str, float] = {}
    level = base_value

    for d in sorted(daily_prices):
        prices = {k: v for k, v in daily_prices[d].items() if v and v > 0}
        if prev_date is None:
            points.append(ChainPoint(d, level, 1.0, len(prices), 100.0, "base"))
            prev_date, prev_prices = d, prices
            continue

        matched = [k for k in prices if k in prev_prices]
        w_matched = sum(weights.get(k, 1.0) for k in matched)
        denom = total_weight if total_weight > 0 else (sum(weights.get(k, 1.0) for k in prices) or 1.0)
        pct = 100.0 * w_matched / denom if denom else 0.0

        gap = (date.fromisoformat(d) - date.fromisoformat(prev_date)).days
        if not matched:
            points.append(ChainPoint(d, level, 1.0, 0, 0.0, "no_overlap"))
        elif pct < min_matched_weight_pct:
            points.append(ChainPoint(d, level, 1.0, len(matched), pct, "low_coverage"))
        else:
            num = sum(weights.get(k, 1.0) * math.log(prices[k] / prev_prices[k]) for k in matched)
            link = math.exp(num / w_matched)
            level *= link
            points.append(ChainPoint(d, level, link, len(matched), pct, "gap" if gap > 1 else ""))
        prev_date, prev_prices = d, prices
    return points
