"""
Orchestrates one scrape pass across a set of routes for one target site,
using Scrapling's StealthyFetcher.

DEPENDS ON `scrapling` + a real Playwright browser install — neither is
available in this sandbox (no network egress; confirmed via a real failed
`pip download scrapling`, not assumed). This file is reviewed for syntax
and logic but has NEVER been run against a live site. Run it on your own
machine first, per the guide, before showing it to anyone as "live
scraping" — same honesty split this whole project has kept throughout.

Design choices, and why:

- One request per route, sequential, with a mandatory delay between
  requests (`--delay`, default 4s) and capped concurrency of 1 by default.
  This is a CPI-index data collector, not a competitive-load scraper —
  going gently is both more polite and less likely to trip anti-bot
  defenses than parallel hammering.
- Exponential backoff retries (default 3 attempts: 2s, 4s, 8s) per route,
  independent per route, so one route failing doesn't abort the whole run.
- capture_xhr first, HTML/CSS fallback only if no XHR matched anything —
  matches targets.py's documented preference order.
- Every route's outcome (success / xhr-empty / html-fallback-empty /
  fetch-error) is logged to the run's quality report, not just silently
  dropped, so a bad run is visible immediately instead of showing up as a
  mysteriously thin index three stages downstream.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from .models import FareRecord
from .targets import TARGETS, ScrapeTarget, build_search_url
from .xhr_parser import (
    extract_air_india_air_bounds,
    extract_fares_from_xhr,
    extract_google_flights_batchexecute,
    extract_indigo_fare_radar,
)


# Several internal Google RPC endpoints (GetShoppingResults among them —
# confirmed by google_flights's first real run, 2026-09-27: three XHRs hit
# that exact endpoint, every one crashed the same way) prefix an
# otherwise-valid JSON body with a `)]}'`-style anti-JSON-hijacking guard
# line before the real payload. It's a documented convention across
# multiple Google APIs (Gmail's old feed API, various Closure/GWT-RPC
# endpoints), not something specific to Flights. A plain `json.loads` on
# that raw text fails on the very first byte — exactly the error this run
# hit: "JSONDecodeError: unexpected character, expected a JSON value: line
# 1 column 1 (char 0)" — and it fails OUTSIDE the try/except that saves
# debug files, which is why no debug_google_flights_*.json ever got
# written despite the XHR genuinely being captured three times.
def _strip_xssi_prefix(raw_text: str) -> str:
    """Strip a leading `)]}'`-style XSSI guard line, if present.

    Deliberately doesn't hardcode the exact guard characters (they vary
    slightly across Google APIs — `)]}'`, `)]}',`, etc.) — anything that
    starts with `)]}` is treated as a one-line guard and everything after
    its first newline is the real payload. Text with no such prefix is
    returned unchanged.
    """
    text = raw_text.lstrip("\ufeff")  # tolerate a stray BOM too
    stripped = text.lstrip()
    if stripped.startswith(")]}"):
        idx = stripped.find("\n")
        return stripped[idx + 1 :] if idx != -1 else stripped
    return text


# Third real run (2026-09-27): no crash, raw text WAS retrieved, and
# stripping the `)]}'` guard got us from "unexpected character... char 0"
# to a more specific "Extra data: line 3 column 1 (char 7)" — a
# json.loads that parses SOME small valid value and then trips on
# whatever follows it. First theory: an explicit `<byte-length>\n`
# header before each JSON chunk (Google's classic streaming-RPC framing).
#
# Fourth real run: that theory's own implementation, tested against this
# exact run, came back with "0 usable chunks" — real evidence the theory
# was wrong (or at least not byte-exact), not just an implementation bug
# to patch further. Rather than guess a THIRD specific framing byte-for-
# byte (repeated guard lines between chunks? a length count that isn't a
# raw byte count? something else?), this replaces the byte-slicing
# approach entirely with a general JSON-stream scanner: it uses Python's
# own JSON grammar (via `JSONDecoder.raw_decode`) to greedily pull out
# every well-formed top-level JSON value from the text, and treats
# anything between values it can't parse as JSON — a repeated `)]}'`
# guard line, a bare length header, blank lines — as separator noise to
# skip past rather than a fatal error. This works whether the real
# framing turns out to be length-prefixed, guard-per-chunk, or something
# not yet seen, because it never assumes a specific byte count; it just
# asks "is this valid JSON starting here?" and moves on when it isn't.
def _extract_json_values_from_stream(text: str) -> list:
    """Greedily extract every top-level JSON value from `text`, in the
    order they appear, tolerating non-JSON separator noise in between
    (guard lines, length headers, blank lines).

    A bare top-level JSON integer (the shape a length-header line would
    take) is treated as noise and dropped rather than returned — it's a
    framing artifact, not payload, whichever theory turns out to be
    right. Every dict/list value found IS returned. Stops (without
    raising) the moment nothing at the current position parses as JSON
    at all, keeping whatever real values were already found.
    """
    decoder = json.JSONDecoder()
    values: list = []
    idx = 0
    n = len(text)
    while idx < n:
        while idx < n and text[idx] in " \t\r\n":
            idx += 1
        if idx >= n:
            break
        if text[idx : idx + 3] == ")]}":
            # A repeated XSSI-style guard line, wherever it shows up —
            # skip past its end-of-line and keep scanning.
            newline_idx = text.find("\n", idx)
            idx = newline_idx + 1 if newline_idx != -1 else n
            continue
        try:
            value, end = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            break  # can't make progress from here — keep what we already have
        if not isinstance(value, int):
            values.append(value)
        idx = end
    return values


# Second real run (2026-09-27, after the XSSI fix above): the crash is
# gone, but `.text()` still handed back nothing — no exception surfaced,
# no XSSI-strip attempted (the log's error had no "after XSSI-guard
# strip" suffix), meaning raw_text came back empty/None. Rather than
# guess a specific reason (a live candidate: Playwright discards a
# response's buffered body once its page/frame has navigated away or the
# browser context is closing, which "browserinfo" firing right after
# "GetShoppingResults" makes plausible) — the same guessing this project
# has repeatedly burned time on — this now tries several plausible
# attribute names AND, if every one comes back empty, records exactly
# which attributes exist on the real entry object. That's real evidence
# for the next fix instead of a fourth blind guess.
_RAW_TEXT_CANDIDATE_ATTRS = ("text", "body_text", "content", "body", "raw", "data", "response_text")


def _extract_raw_text(entry) -> tuple[Optional[str], list[str]]:
    """Try each plausible attribute name in turn for a captured XHR
    entry's raw response body as text (or bytes, decoded). Returns
    (raw_text, attempts) — `attempts` logs what happened with every
    attribute tried, even on success, so the debug file always shows
    which one actually worked (or why none did)."""
    attempts: list[str] = []
    for attr_name in _RAW_TEXT_CANDIDATE_ATTRS:
        attr = getattr(entry, attr_name, None)
        if attr is None:
            attempts.append(f"{attr_name}: not present")
            continue
        try:
            value = attr() if callable(attr) else attr
        except Exception as exc:  # noqa: BLE001 — this IS the diagnostic; keep going to the next candidate
            attempts.append(f"{attr_name}(): raised {type(exc).__name__}: {exc}")
            continue
        if isinstance(value, bytes):
            try:
                value = value.decode("utf-8", errors="replace")
            except Exception as exc:  # noqa: BLE001
                attempts.append(f"{attr_name}: bytes but couldn't decode ({exc})")
                continue
        if isinstance(value, str) and value:
            attempts.append(f"{attr_name}: OK, {len(value)} chars")
            return value, attempts
        attempts.append(f"{attr_name}: present but empty/unusable (type={type(value).__name__})")
    return None, attempts


def _parse_captured_xhr(entry) -> tuple[Optional[object], Optional[str], Optional[str]]:
    """Best-effort parse of one Scrapling/Playwright captured-XHR entry.

    Returns (payload, raw_text, error):
    - payload: the parsed JSON (a dict, OR a list of chunk values if the
      response turned out to be Google's length-prefixed chunk stream —
      see `_extract_json_values_from_stream`), or None if nothing
      parsed.
    - raw_text: the raw response body as text, whenever available — this
      is what gets saved to disk even when parsing fails.
    - error: on total failure to even get raw text, this is a full
      diagnostic dump (every attribute name tried, plus real
      introspection of the entry object) instead of a one-line guess —
      that dump IS the raw.txt file's content in that case, so the next
      run answers "what does this object actually look like" for good.

    Tries the entry's own `.json()` first (unchanged fast path for every
    target that already works — air_india, indigo, the generic HTML/XHR
    heuristic). Also still accepts a plain dict passed directly as
    `entry` (what this project's own unit-test fakes do).
    """
    if isinstance(entry, dict):
        # Existing unit-test fakes hand the payload dict itself as
        # `entry`, with no `.json`/`.text` attributes at all.
        return entry, None, None

    json_attr = getattr(entry, "json", None)
    first_error: Optional[str] = None
    if callable(json_attr):
        try:
            return json_attr(), None, None
        except Exception as exc:  # noqa: BLE001 — fall through to the raw-text fallback below
            first_error = f".json() raised {type(exc).__name__}: {exc}"
    elif isinstance(json_attr, dict):
        return json_attr, None, None
    else:
        first_error = ".json attribute missing or not usable"

    raw_text, attempts = _extract_raw_text(entry)
    if raw_text:
        stripped = _strip_xssi_prefix(raw_text)
        try:
            return json.loads(stripped), raw_text, None
        except Exception as exc:  # noqa: BLE001 — try the JSON-stream scan before giving up
            single_doc_error = f"{type(exc).__name__}: {exc}"
        values = _extract_json_values_from_stream(stripped)
        if values:
            return values, raw_text, None
        return (
            None,
            raw_text,
            f"{first_error}; after XSSI-guard strip: {single_doc_error}; "
            "also tried JSON-value-stream scanning, got 0 usable values",
        )

    # Total failure: neither .json() nor any raw-text candidate produced
    # anything. Dump real introspection rather than a fifth guess.
    known_attrs = [a for a in dir(entry) if not a.startswith("_")]
    diag = (
        f"{first_error}\n"
        "raw-text extraction attempts:\n  " + "\n  ".join(attempts) + "\n"
        f"type(entry) = {type(entry)!r}\n"
        f"dir(entry) (public attributes) = {known_attrs}\n"
    )
    return None, None, diag




@dataclass
class RouteOutcome:
    route_id: str
    status: str  # "ok" | "xhr_empty_used_html" | "empty" | "fetch_error"
    record_count: int
    error: Optional[str] = None
    # Diagnostics — filled in even on an "empty" result, specifically so a
    # thin/empty run is debuggable from the report file alone instead of
    # requiring a second run with print statements added ad hoc.
    http_status: Optional[int] = None
    xhr_captured_count: int = 0
    html_cards_found: int = 0
    debug_html_path: Optional[str] = None


@dataclass
class ScrapeRunReport:
    target_name: str
    routes_attempted: int = 0
    routes_ok: int = 0
    routes_empty: int = 0
    routes_errored: int = 0
    outcomes: list[RouteOutcome] = field(default_factory=list)

    def add(self, outcome: RouteOutcome) -> None:
        self.outcomes.append(outcome)
        self.routes_attempted += 1
        if outcome.status == "fetch_error":
            self.routes_errored += 1
        elif outcome.record_count == 0:
            self.routes_empty += 1
        else:
            self.routes_ok += 1

    def to_dict(self) -> dict:
        return {
            "target": self.target_name,
            "routes_attempted": self.routes_attempted,
            "routes_ok": self.routes_ok,
            "routes_empty": self.routes_empty,
            "routes_errored": self.routes_errored,
            "outcomes": [o.__dict__ for o in self.outcomes],
        }


def _default_travel_date(days_ahead: int = 21) -> str:
    # Fares 2-4 weeks out tend to be more stable/representative than
    # tomorrow's last-minute-premium fares or six-months-out speculative
    # fares — a reasonable default for an index, adjust with --days-ahead.
    return (date.today() + timedelta(days=days_ahead)).isoformat()


def scrape_route(
    target: ScrapeTarget,
    route: dict,
    *,
    travel_date: str,
    max_retries: int = 3,
    base_backoff_seconds: float = 2.0,
) -> RouteOutcome:
    """Scrape one route against one target. Imports scrapling lazily inside
    the function (not at module top) so that importing this whole package
    for its pure-Python parts (models.py, xhr_parser.py) never requires
    scrapling to be installed — only actually running a scrape does."""
    from scrapling.fetchers import StealthyFetcher  # noqa: local import by design

    # Must be set BEFORE the first .fetch()/.css() call, at the class
    # level — this is what makes auto_save=True / adaptive=True in
    # html_parser.py actually take effect instead of being silently
    # ignored (Scrapling logs a warning and no-ops otherwise, which is
    # exactly what happened before this fix: "Argument `adaptive` will be
    # ignored because `adaptive` wasn't enabled on initialization").
    StealthyFetcher.adaptive = True

    route_id = route["route_id"]
    url = build_search_url(target, route["origin"], route["destination"], travel_date)

    # Only built for targets that actually declared one (currently just
    # air_india) — passed as a kwarg only when present so every other
    # target's StealthyFetcher.fetch() call is byte-for-byte unchanged.
    fetch_kwargs: dict = {}
    if target.page_action_factory is not None:
        fetch_kwargs["page_action"] = target.page_action_factory(route, travel_date)

    last_error: Optional[str] = None
    for attempt in range(1, max_retries + 1):
        try:
            page = StealthyFetcher.fetch(
                url,
                **fetch_kwargs,
                headless=True,
                # network_idle=True (waiting for truly zero network
                # activity) was tried first and reliably came back with an
                # empty stub response — heavy SPAs like MakeMyTrip run
                # continuous background analytics/polling requests, so
                # "network idle" may never actually be reached before
                # Scrapling's internal retry budget for page.content()
                # gives up and falls back to a near-empty placeholder.
                # A fixed settle time after load + a longer overall
                # timeout is the more reliable pattern for this kind of
                # site (confirmed against real reports of the same
                # network_idle failure mode on other heavy SPAs).
                wait=6000,
                timeout=45000,
                capture_xhr=target.xhr_pattern,
            )
            records: list[FareRecord] = []

            captured = getattr(page, "captured_xhr", None) or []
            for i, entry in enumerate(captured):
                entry_url = getattr(entry, "url", None)
                payload, raw_text, parse_error = _parse_captured_xhr(entry)
                # Save every captured XHR's raw shape to disk regardless of
                # whether we can parse it — this is what tells us the real
                # JSON structure instead of guessing a second time. Cheap
                # to always do; only matters when records come back empty.
                #
                # A parse failure now gets its OWN debug file (raw text +
                # the error), instead of the whole route silently retrying
                # and eventually reporting a bare "fetch_error" with zero
                # diagnostic files — exactly what happened to
                # google_flights's first real run: the crash used to
                # happen on the very line that computed `payload`, before
                # this try/except ever started.
                try:
                    if payload is not None:
                        xhr_debug_path = f"debug_{target.name}_{route_id}_xhr_{i}.json"
                        with open(xhr_debug_path, "w", encoding="utf-8") as f:
                            f.write(f"// captured XHR url: {entry_url!r}\n")
                            json.dump(payload, f, indent=2, default=str)
                        print(f"    [{route_id}] saved captured XHR #{i} -> {xhr_debug_path} (url={entry_url})")
                    else:
                        xhr_debug_path = f"debug_{target.name}_{route_id}_xhr_{i}.raw.txt"
                        with open(xhr_debug_path, "w", encoding="utf-8") as f:
                            f.write(f"// captured XHR url: {entry_url!r}\n")
                            f.write(f"// json parse failed: {parse_error}\n\n")
                            f.write(raw_text if raw_text is not None else "<no raw text available>")
                        print(
                            f"    [{route_id}] XHR #{i} didn't parse as JSON -> saved raw body to "
                            f"{xhr_debug_path} (url={entry_url}, error={parse_error})"
                        )
                except Exception:  # noqa: BLE001 — diagnostics must never crash the run
                    pass
                if not isinstance(payload, (dict, list)):
                    continue
                if target.name == "google_flights" and isinstance(payload, list):
                    # Try the verified batchexecute shape first (see
                    # extract_google_flights_batchexecute's docstring for
                    # the real, captured-and-cross-checked shape). Fall
                    # back to the generic heuristic only if Google Flights
                    # changes its RPC framing again.
                    gf_records = extract_google_flights_batchexecute(payload, source=target.name)
                    if gf_records:
                        records.extend(gf_records)
                        continue
                if target.name == "indigo" and isinstance(payload, dict):
                    # Try the verified fare-radar shape first; it's a
                    # confirmed real endpoint, not a guess (see
                    # extract_indigo_fare_radar's docstring). Fall back to
                    # the generic heuristic only if IndiGo changes shape.
                    indigo_records = extract_indigo_fare_radar(payload, source=target.name)
                    if indigo_records:
                        records.extend(indigo_records)
                        continue
                if target.name == "air_india" and isinstance(payload, dict):
                    # Same idea: try the verified air-bounds shape first
                    # (see extract_air_india_air_bounds's docstring), fall
                    # back to the generic heuristic only if Air India
                    # changes shape or this XHR wasn't the air-bounds call.
                    ai_records = extract_air_india_air_bounds(payload, source=target.name)
                    if ai_records:
                        records.extend(ai_records)
                        continue
                records.extend(
                    extract_fares_from_xhr(
                        payload,
                        route_id=route_id,
                        origin=route["origin"],
                        destination=route["destination"],
                        travel_date=travel_date,
                        source=target.name,
                    )
                )

            html_cards_found = 0
            status = "ok"
            if not records:
                # No XHR path found anything — fall back to CSS parsing of
                # the rendered page before declaring this route empty.
                from .html_parser import extract_fares_from_html, _count_cards

                records = extract_fares_from_html(
                    page,
                    target,
                    route_id=route_id,
                    origin=route["origin"],
                    destination=route["destination"],
                    travel_date=travel_date,
                )
                html_cards_found = _count_cards(page, target)
                status = "xhr_empty_used_html" if records else "empty"

            debug_html_path = None
            if not records:
                # Save the actual page so a human can inspect it — this is
                # the difference between "guessing why it's empty" and
                # "seeing why it's empty." Common causes visible here: a
                # bot-check/interstitial page, a cookie-consent wall
                # blocking the real content, or the page markup simply not
                # matching the guessed selectors in targets.py.
                debug_html_path = f"debug_{target.name}_{route_id}.html"
                body_bytes = page.body if isinstance(page.body, bytes) else str(page.body).encode("utf-8")
                try:
                    with open(debug_html_path, "wb") as f:
                        f.write(body_bytes)
                except Exception:  # noqa: BLE001 — best-effort diagnostic, never fatal
                    debug_html_path = None
                # Print straight to the terminal too — a 1KB stub file is
                # obvious the moment you see the byte count and a preview,
                # without needing to open a browser to find out.
                preview = body_bytes[:200].decode("utf-8", errors="replace")
                print(f"    [{route_id}] page body: {len(body_bytes)} bytes, starts with: {preview!r}")

                # A real MakeMyTrip results page is well over 100KB of
                # markup. Under 2KB means `.body` isn't the rendered page
                # for this Scrapling version — stop guessing which
                # attribute has the real content and just dump every
                # plausible one so the next run answers the question
                # directly instead of needing a fourth guess.
                if len(body_bytes) < 2000:
                    diag_path = f"debug_{target.name}_{route_id}.diag.txt"
                    try:
                        with open(diag_path, "w", encoding="utf-8") as f:
                            f.write(f"type(page) = {type(page)!r}\n")
                            f.write(
                                f"dir(page) = {[a for a in dir(page) if not a.startswith('_')]}\n\n"
                            )
                            for attr in (
                                "body", "html_content", "content", "text",
                                "page_content", "status", "url", "raw_response",
                                "history",
                            ):
                                try:
                                    value = getattr(page, attr)
                                    snippet = repr(value)[:300]
                                except Exception as attr_exc:  # noqa: BLE001
                                    snippet = f"<error accessing: {attr_exc}>"
                                f.write(f"--- page.{attr} ---\n{snippet}\n\n")
                        print(f"    [{route_id}] body looked like a stub — wrote {diag_path} for inspection")
                    except Exception:  # noqa: BLE001 — diagnostics must never crash the run
                        pass

            outcome = RouteOutcome(
                route_id=route_id,
                status=status,
                record_count=len(records),
                http_status=getattr(page, "status", None),
                xhr_captured_count=len(captured),
                html_cards_found=html_cards_found,
                debug_html_path=debug_html_path,
            )
            return outcome, records

        except Exception as exc:  # noqa: BLE001 — a scrape target is
            # inherently unreliable (network blips, bot-wall challenges,
            # timeouts); catching broadly here and retrying is the point.
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < max_retries:
                time.sleep(base_backoff_seconds * (2 ** (attempt - 1)))

    return RouteOutcome(route_id=route_id, status="fetch_error", record_count=0, error=last_error), []


def run_scrape(
    target_name: str,
    routes: list[dict],
    *,
    days_ahead: int = 21,
    delay_seconds: float = 4.0,
    max_retries: int = 3,
) -> tuple[list[FareRecord], ScrapeRunReport]:
    target = TARGETS[target_name]
    travel_date = _default_travel_date(days_ahead)
    report = ScrapeRunReport(target_name=target_name)
    all_records: list[FareRecord] = []

    for i, route in enumerate(routes):
        outcome, records = scrape_route(target, route, travel_date=travel_date, max_retries=max_retries)
        report.add(outcome)
        all_records.extend(records)
        if i < len(routes) - 1:
            time.sleep(delay_seconds)

    return all_records, report


def write_output(records: list[FareRecord], report: ScrapeRunReport, out_path: str, report_path: str) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r.to_dict()) + "\n")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2)
