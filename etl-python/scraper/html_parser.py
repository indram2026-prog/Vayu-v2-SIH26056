"""
Fallback path: parse rendered HTML with Scrapling's adaptive `Selector`
when a target has no working `capture_xhr` match (site changed its API,
or serves data server-side rendered rather than via a JSON call).

DEPENDS ON `scrapling` — cannot be unit-tested in this sandbox (no network
here, `pip download scrapling` failed with a real "no matching
distribution" error). This file has been reviewed for syntax and import
correctness (`python3 -m py_compile`) but never executed against a real
Selector object. Test it on your own machine per the guide before trusting
it — that is the honest status, not a hedge.

The `auto_save=True` / `adaptive=True` pattern below is Scrapling's core
pitch: the first successful run remembers *where* it found the price
element (tag, attributes, position, neighboring text), so if the site's
class names change on a later run, `adaptive=True` finds the same element
by shape instead of failing outright.
"""

from __future__ import annotations

from .models import FareRecord, FareRecordError
from .targets import ScrapeTarget
from .xhr_parser import _coerce_fare  # reuse the same fare-string cleanup


def _count_cards(page, target: ScrapeTarget) -> int:
    """Diagnostic helper: how many elements matched the flight-card
    selector, regardless of whether a fare could be extracted from them.
    Distinguishes two very different failure modes in the run report:
    'selector matched 0 elements' (wrong selector, or page didn't render
    real content) vs. 'selector matched N elements but none had a
    parseable fare' (right area of the page, wrong sub-selector)."""
    try:
        return len(page.css(target.css_selectors["flight_card"]))
    except Exception:  # noqa: BLE001 — diagnostics must never crash the run
        return 0


def extract_fares_from_html(
    page,  # a scrapling.fetchers.Response (has .css / .status / .body)
    target: ScrapeTarget,
    *,
    route_id: str,
    origin: str,
    destination: str,
    travel_date: str,
) -> list[FareRecord]:
    records: list[FareRecord] = []

    cards = page.css(target.css_selectors["flight_card"], auto_save=True)
    if not cards:
        # First attempt with the plain selector found nothing — the page
        # may have been auto_save'd on a previous run under a different
        # DOM shape. Retry with adaptive=True before giving up.
        cards = page.css(target.css_selectors["flight_card"], adaptive=True)

    for card in cards:
        fare_nodes = card.css(target.css_selectors["fare"] + "::text")
        if not fare_nodes:
            continue
        fare = _coerce_fare(fare_nodes[0])
        if fare is None:
            continue

        airline = target.css_selectors.get("airline_name")
        if airline and isinstance(airline, str) and not airline.isupper():
            # It's a CSS selector, not a hardcoded name (e.g. "IndiGo").
            airline_nodes = card.css(airline + "::text")
            airline = airline_nodes[0] if airline_nodes else ""
        elif not airline:
            airline = ""

        try:
            records.append(
                FareRecord(
                    route_id=route_id,
                    origin=origin,
                    destination=destination,
                    airline=airline,
                    fare=fare,
                    fare_type="displayed",
                    travel_date=travel_date,
                    source=target.name,
                    method="html_fallback",
                    confidence="unverified",
                    raw_ref=f"html:{target.name}",
                )
            )
        except FareRecordError:
            continue

    return records
