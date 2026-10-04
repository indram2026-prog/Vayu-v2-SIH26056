"""
Compliance status of candidate OTA sources, kept as data, not wired into
targets.TARGETS on purpose: a source only becomes a runnable ScrapeTarget
AFTER its robots.txt (and terms) have been checked and the fare pages we need
are permitted. Re-verify with:

    python -m scraper.robots_guard https://<host> <fare-path> ...

`status` values:
    "blocked_by_robots"   - fare pages/endpoints are Disallowed for all bots; do not scrape
    "pending_robots_check" - robots.txt not yet read for the fare paths; do not scrape yet
"""

from __future__ import annotations

OTA_CANDIDATES: dict[str, dict] = {
    "ixigo": {
        "status": "blocked_by_robots",
        "checked": "2026-10-04",
        "source": "https://www.ixigo.com/robots.txt (read via a search-result excerpt; re-verify directly)",
        "evidence": [
            "Disallow: /flights/search",
            "Disallow: /search/result/",
            "Disallow: /flights/review",
            "Disallow: /api/",
        ],
        "decision": "Not scraped. The fare search pages and API paths are disallowed for User-agent: *.",
    },
    "easemytrip": {
        "status": "robots_checked_fare_path_unconfirmed",
        "checked": "2026-10-04",
        "source": "https://www.easemytrip.com/robots.txt and https://flight.easemytrip.com/robots.txt (both read directly, HTTP 200)",
        "evidence": [
            "www host: Disallow: /flight-search/listing*, /cheap_flights/, /cheap-flights/, /international_airlines/",
            "flight host: Disallow: /cheap_flights/, /cheap-flights/, /international_airlines/ (no rule on the search/listing paths)",
        ],
        "decision": (
            "Not blocked for the paths we expect, but the real search-results and fare "
            "request paths have not been captured yet. Capture them with a manual search "
            "(browser DevTools Network tab), re-run robots_guard on those exact paths, "
            "then build the target."
        ),
    },
    "cleartrip": {
        "status": "blocked_by_robots",
        "checked": "2026-10-04",
        "source": "https://www.cleartrip.com/robots.txt (read directly, HTTP 200)",
        "evidence": [
            "Disallow: /flights/search*",
            "Disallow: /api/",
            "Disallow: /flights/results/itinerary/loading*",
        ],
        "decision": "Not scraped. Flight search and API paths are disallowed for User-agent: *.",
    },
    "easemytrip_note": {
        "status": "dropped_by_team",
        "checked": "2026-10-04",
        "source": "team decision",
        "evidence": ["Date-calendar UI needs browser automation; same obstacle as Air India."],
        "decision": "Not pursued for now. robots.txt itself does not block the expected paths.",
    },
    "yatra": {
        "status": "pending_robots_check",
        "checked": None,
        "source": "https://www.yatra.com/robots.txt",
        "evidence": ["Could not be fetched from the test environment; check from a normal connection."],
        "decision": "No scraping until robots.txt is read.",
    },
}


def is_runnable(name: str) -> bool:
    """A candidate may only be promoted to a real target once nothing blocks it."""
    entry = OTA_CANDIDATES.get(name)
    return bool(entry) and entry["status"] == "allowed_verified"
