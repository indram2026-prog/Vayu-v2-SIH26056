# Responsible data collection policy

Vayu collects public airfare data from airline and travel sites. This is a prototype, and this note states plainly what we do and what we do not claim.

## Our position

- **robots.txt is respected.** It is a published, machine-readable instruction from the site owner, and the problem statement names it explicitly. A URL that robots.txt disallows for our user agent is not fetched.
- **Terms of service are acknowledged as a limitation.** Most large travel sites restrict automated access in their terms. A scraper cannot be fully ToS-clean, and we do not claim it is. Production use would move to licensed data, official APIs or data-sharing agreements with the airlines and OTAs.
- **No circumvention of access controls.** We do not solve or defeat CAPTCHAs, use logins or accounts, or use proxy networks to evade blocks. If a site blocks automated access, we drop that source rather than escalate.

## Practices

1. **Check before you fetch.** `etl-python/scraper/robots_guard.py` implements the RFC 9309 matching rules (user-agent groups, `*` and `$` wildcards, longest match, Allow wins ties).
2. **Fail closed.** If robots.txt cannot be read (5xx, 429, network error), access is treated as not confirmed. A missing robots.txt (404) means no restriction was published.
3. **Review before adding a source.** Candidate sources are tracked in `ota_candidates.py` with their status. A blocked or unchecked source cannot be promoted to a runnable target.
4. **Low volume.** One request at a time, a delay between requests, bounded retries, a modest number of routes per day. Honour any `Crawl-delay`.
5. **Prefer allowed channels.** Airline pages and endpoints that robots.txt allows, then official APIs and published statistics (for example DGCA data), over anything restricted.
6. **Record decisions.** Each source's status and the date it was checked are kept in the repo.

## Source status

| Source | Status | Notes |
|---|---|---|
| Ixigo | Not scraped | robots.txt disallows `/flights/search`, `/search/result/`, `/flights/review`, `/api/` for all bots (checked 2026-10-04 from a search-result excerpt; re-verify directly). |
| EaseMyTrip | robots.txt checked | Read directly on 2026-10-04 (evidence in `docs/evidence/`). Disallows `/flight-search/listing*`, `/cheap_flights/`, `/cheap-flights/` on the main host; the `flight.` host has no rule on search paths. The real fare request paths still need to be captured and re-checked before building. |
| Cleartrip | Pending | robots.txt not yet read for fare paths. |
| MakeMyTrip | Not pursued | Blocks automated browsers. |
| Google Flights | Used in the scheduled run | Its terms restrict automated access; this is a known prototype limitation. Its robots.txt rules for the Flights paths should be verified, and the source replaced for production. |

## Check a source

    cd etl-python
    python -m scraper.robots_guard https://<host> <fare-path> [<fare-path> ...]

It prints ALLOWED or DISALLOWED for each path and saves the fetched robots.txt as evidence.
