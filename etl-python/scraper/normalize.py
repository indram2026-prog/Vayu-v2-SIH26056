"""
Stage 1 of the index pipeline: turn a pile of raw FareRecords (possibly from
several targets — google_flights primarily, indigo/air_india as
cross-checks) into ONE representative price per route for the run's travel
date.

Deliberately separate from anomaly_filter.py and index_engine.py (even
though all three are small) so each stage answers exactly one question and
can be unit-tested and reasoned about alone:

    normalize.py       "what did we actually observe, per route?"
    anomaly_filter.py   "which of those observations do we trust?"
    index_engine.py      "what does the trusted subset say the index is?"

No dependency on `scrapling`, network, or Supabase — pure stdlib, same
testability policy as models.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Iterable

from .models import FareRecord


@dataclass
class RouteObservation:
    route_id: str
    travel_date: str
    representative_price: float   # median of every raw fare seen for this
                                   # route today — see _representative() below
                                   # for why median, not min or mean.
    cheapest_price: float
    most_expensive_price: float
    raw_record_count: int
    airlines: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)  # scraper target names
                                                          # that contributed,
                                                          # e.g. ["google_flights"]

    def to_dict(self) -> dict:
        return {
            "route_id": self.route_id,
            "travel_date": self.travel_date,
            "representative_price": self.representative_price,
            "cheapest_price": self.cheapest_price,
            "most_expensive_price": self.most_expensive_price,
            "raw_record_count": self.raw_record_count,
            "airlines": self.airlines,
            "sources": self.sources,
        }


def _representative(fares: list[float]) -> float:
    # Median, not min or mean:
    #   - min would make the index track the single cheapest saver fare on
    #     each route, which is easy to game/noisy (one promo fare on one
    #     airline shouldn't move a route's whole reading) and isn't what a
    #     traveler actually pays on average.
    #   - mean is pulled around by the long right tail every route has (a
    #     handful of premium/flexible fares priced 2-3x economy-saver).
    #   - median is the standard "typical fare" choice for exactly this
    #     reason, and is what CPI-style index construction conventionally
    #     uses for a representative price within an elementary aggregate.
    return float(median(fares))


def normalize_records(records: Iterable[FareRecord]) -> list[RouteObservation]:
    """Group raw FareRecords by route_id and collapse each group into one
    RouteObservation. Records for different travel_dates that happen to
    share a route_id are still grouped together (one pipeline run always
    targets a single travel_date in practice — see run_pipeline.py — so
    this is a non-issue in normal use, but if it ever isn't, the LAST
    record's travel_date wins for the group's travel_date field, which is
    at least deterministic and visible rather than silently averaging two
    different dates together).
    """
    by_route: dict[str, list[FareRecord]] = {}
    for r in records:
        by_route.setdefault(r.route_id, []).append(r)

    observations: list[RouteObservation] = []
    for route_id, group in by_route.items():
        fares = [r.fare for r in group]
        airlines = sorted({r.airline for r in group if r.airline})
        sources = sorted({r.source for r in group if r.source})
        observations.append(
            RouteObservation(
                route_id=route_id,
                travel_date=group[-1].travel_date,
                representative_price=_representative(fares),
                cheapest_price=min(fares),
                most_expensive_price=max(fares),
                raw_record_count=len(group),
                airlines=airlines,
                sources=sources,
            )
        )
    return observations
