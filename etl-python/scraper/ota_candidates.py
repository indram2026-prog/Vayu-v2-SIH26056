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
        "status": "pending_robots_check",
        "checked": None,
        "source": "https://www.easemytrip.com/robots.txt",
        "evidence": [],
        "decision": "No scraping until robots.txt and terms are read and the fare paths are confirmed allowed.",
    },
    "cleartrip": {
        "status": "pending_robots_check",
        "checked": None,
        "source": "https://www.cleartrip.com/robots.txt",
        "evidence": [],
        "decision": "Same as easemytrip: check first.",
    },
}


def is_runnable(name: str) -> bool:
    """A candidate may only be promoted to a real target once nothing blocks it."""
    entry = OTA_CANDIDATES.get(name)
    return bool(entry) and entry["status"] == "allowed_verified"
