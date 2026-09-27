"""
The one shape every scraped fare gets normalized into, regardless of which
site or capture method produced it (XHR JSON capture vs. HTML/CSS fallback).
Downstream (normalize.py / anomaly_filter.py / index_engine.py from the
earlier session — not present in this upload) should only ever need to know
this one schema, never a per-site quirk.

This file has NO dependency on the `scrapling` package on purpose — it is
pure stdlib, so it can be unit-tested in any Python 3.9+ environment,
including this sandbox with no network and no scrapling installed.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Optional


class FareRecordError(ValueError):
    """Raised when a scraped record fails basic sanity checks before it's
    allowed into the output file. Better to drop-and-log a bad record here
    than let a garbage fare (₹0, ₹50, ₹9,999,999) silently pollute the index
    upstream — that's exactly the kind of anomaly anomaly_filter.py exists
    to catch, but catching it at the source is cheaper than catching it
    three stages later."""


@dataclass
class FareRecord:
    route_id: str          # e.g. "DEL-BOM" — must match shared/routes.json
    origin: str             # IATA code, e.g. "DEL"
    destination: str        # IATA code, e.g. "BOM"
    airline: str             # e.g. "IndiGo", "Air India" — "" if unknown
    fare: float              # fare in INR, all-in if the site shows all-in
    fare_type: str            # "displayed" | "all_in" | "base_only" — be
                              # honest about which one you actually captured
    travel_date: str          # ISO date "YYYY-MM-DD" the fare applies to
    source: str               # target name, e.g. "makemytrip", "indigo"
    method: str                # "xhr_capture" | "html_fallback"
    scraped_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    currency: str = "INR"
    confidence: str = "unverified"  # "unverified" until run against a real
                                      # page at least once and eyeballed
    raw_ref: Optional[str] = None    # short breadcrumb (e.g. XHR URL path)
                                      # for debugging, never the full payload

    def __post_init__(self) -> None:
        if not self.route_id or "-" not in self.route_id:
            raise FareRecordError(f"bad route_id: {self.route_id!r}")
        if self.fare is None or self.fare <= 0:
            raise FareRecordError(f"non-positive fare for {self.route_id}: {self.fare!r}")
        # Real India domestic fares: sanity band, not a hard business rule.
        # Anything outside this is almost certainly a parsing bug (grabbed a
        # baggage-fee number, a strikethrough "original" price, or a seat
        # count instead of a fare) rather than a real fare — reject at the
        # source instead of passing it to anomaly_filter.py to catch later.
        if not (1000.0 <= self.fare <= 100000.0):
            raise FareRecordError(
                f"fare {self.fare} for {self.route_id} outside sane band "
                f"(₹1,000–₹1,00,000) — likely a parsing bug, not a real fare"
            )
        if self.fare_type not in ("displayed", "all_in", "base_only"):
            raise FareRecordError(f"bad fare_type: {self.fare_type!r}")
        if self.method not in ("xhr_capture", "html_fallback"):
            raise FareRecordError(f"bad method: {self.method!r}")

    def to_dict(self) -> dict:
        return asdict(self)
