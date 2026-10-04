# Ethical scraping and compliance policy

SIH26056 requires that collection from airline sites and OTAs stays compliant with each source's robots.txt and terms of service. This is how Vayu applies that.

## Rules

1. **Check before you fetch.** `etl-python/scraper/robots_guard.py` implements the RFC 9309 matching rules (user-agent groups, `*` and `$` wildcards, longest-match, Allow wins ties). A URL that robots.txt disallows for our user agent is not fetched.
2. **Fail closed.** If a site's robots.txt cannot be read (5xx, 429, network error) access is treated as not confirmed. A missing robots.txt (404) means no restriction was published.
3. **A source is added only after review.** Candidate OTAs are tracked in `ota_candidates.py` with their status. None can be promoted to a runnable target while blocked or unchecked.
4. **Be gentle.** One request at a time, a delay between requests, bounded retries, a modest daily volume. Honour any `Crawl-delay`.
5. **Identify ourselves.** Use a stable, descriptive user agent for sources that permit access.
6. **Prefer allowed channels.** Airline pages and endpoints that robots.txt allows, official APIs, and published statistics (for example DGCA) over anything restricted.
7. **Record decisions.** Each source's outcome and the date checked are kept in the repo, so the choices are auditable.

## Source status

| Source | Status | Notes |
|---|---|---|
| Ixigo | Not scraped | robots.txt disallows `/flights/search`, `/search/result/`, `/flights/review`, `/api/` for all bots (checked 2026-10-04 from a search-result excerpt; re-verify directly). |
| EaseMyTrip | Pending | robots.txt not yet read for fare paths. |
| Cleartrip | Pending | robots.txt not yet read for fare paths. |
| MakeMyTrip | Not pursued | Actively blocks automated browsers. |
| Google Flights | Needs review | Google's Terms of Service prohibit automated access in violation of machine-readable instructions such as robots.txt. Review before relying on it as a primary source. |

## Check a source

    cd etl-python
    python -m scraper.robots_guard https://<host> <fare-path> [<fare-path> ...]

It prints ALLOWED or DISALLOWED for each path and saves the fetched robots.txt as evidence.
