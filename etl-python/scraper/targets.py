"""
Per-site target configuration for the Scrapling-based fare scraper.

HONESTY NOTE (same policy as the rest of this project): nothing in this file
has been run against a live site. This sandbox has no network egress —
`pip download scrapling` was attempted and failed with a real "no matching
distribution" error, confirmed, not assumed. Every regex/selector below is a
best-guess starting point based on how these sites are commonly built
(Next.js/React SPAs that call a JSON search API under the hood), not a
verified fixture of the real DOM. Treat `confidence` as the honest signal:

    "guessed"   — never checked against the real site at all
    "plausible" — matches publicly documented patterns but unverified here
    "verified"  — someone ran this against the live site and confirmed it

Update `confidence` the moment you actually run this against a real site,
in either direction — up when it works, down (with a note) when it doesn't.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from .page_actions import build_air_india_page_action
from .page_actions_google_flights import build_google_flights_page_action


@dataclass
class ScrapeTarget:
    name: str
    # Where a human would go to search this route manually. {origin},
    # {destination}, {date} are filled in per-request.
    search_url_template: str
    # If set: a regex Scrapling's `capture_xhr` will match against
    # in-flight network requests while the page loads. When it matches,
    # Scrapling hands back the raw JSON body via `response.captured_xhr`
    # — this is the preferred, more robust path (site's own frontend
    # already extracted the fare into structured JSON; you're just
    # reading it instead of re-parsing rendered HTML).
    xhr_pattern: Optional[str]
    # CSS fallback selectors, used only if xhr_pattern doesn't fire (e.g.
    # site changed its API, or this target has no XHR path at all).
    css_selectors: dict
    confidence: str
    notes: str
    # Optional: (route_dict, travel_date) -> Scrapling `page_action` callable.
    # Only set for targets confirmed (or strongly suspected) to be SPAs that
    # hold search state in-browser rather than in the URL — see air_india
    # below and page_actions.py for the real DOM this was written against.
    page_action_factory: Optional[Callable[[dict, str], Callable]] = None


TARGETS: dict[str, ScrapeTarget] = {
    # GIVEN EQUAL PRIORITY to air_india below, on the user's explicit call —
    # and for a good reason, not just "why not": Google Flights is a
    # METASEARCH aggregator, not a single airline. One working response
    # here should surface fares across IndiGo, Air India, SpiceJet, Akasa,
    # Vistara, etc. all at once, whereas every other entry in this file
    # only ever yields that one airline's own fares. If this target proves
    # reliable, it becomes the PRIMARY fare source and the single-airline
    # targets below become secondary — useful mainly as an independent
    # cross-check on Google's numbers and as a fallback if Google changes
    # its internal API or starts serving CAPTCHAs at this run's volume,
    # not as something that also needs building out one airline at a time.
    # That's a real trade, not a free win, though: this target's own
    # confidence is "guessed" (nothing here has ever touched a live
    # browser — see page_actions_google_flights.py's honesty split), it
    # depends on an internal, undocumented, unversioned RPC endpoint that
    # can change without notice, and Google's bot-defenses — lighter than
    # MakeMyTrip's confirmed hard block, per the user's own research
    # (screenshot, 2026-09-27) — are not zero either. Treat "works, so
    # skip the rest" as the eventual goal to verify, not the starting
    # assumption to build on.
    "google_flights": ScrapeTarget(
        name="google_flights",
        # UNVERIFIED pattern (see module docstring): Google Flights'
        # documented "natural language" deep-link query format. If this
        # actually lands on a populated results view rather than an
        # empty, unsubmitted search box, this target may need little to
        # no further page_action work beyond consent-dismissal.
        search_url_template=(
            "https://www.google.com/travel/flights"
            "?q=Flights%20to%20{destination}%20from%20{origin}%20on%20{date}"
            "&hl=en&curr=INR"
        ),
        # Per the user's own research into Google Flights' internals
        # (screenshot, 2026-09-27): the site avoids third-party anti-bot
        # vendors and instead calls internal RPC endpoints under a
        # `FlightsFrontendUi` path rather than a REST-shaped `/search` or
        # `/fare` URL the way the single-airline sites below do — this
        # pattern is broad on purpose (the exact path segment is a tip,
        # not a captured real request) so the first real run's own
        # terminal output (which XHR URLs actually got captured, if any)
        # is what narrows it, not another guess in this file.
        xhr_pattern=r".*FlightsFrontendUi.*",
        css_selectors={
            # Deliberately NOT a hash-like generated class name (e.g.
            # ".pIav2d") — Google rotates those across releases, per the
            # same research this target is built from, so guessing one
            # would be confidently wrong rather than honestly uncertain.
            # `[role='listitem']` is a real, documented ARIA pattern for
            # Flights' result rows and more likely (not confirmed) to
            # survive a markup change than any specific class name would.
            "flight_card": "[role='listitem']",
            "airline_name": "[aria-label*='operated by'], [class*='airline']",
            "fare": "[aria-label*='INR'], [aria-label*='rupees'], [class*='price']",
        },
        confidence="guessed",
        page_action_factory=build_google_flights_page_action,
        notes=(
            "NEVER RUN against the live site — this is a genuine first "
            "attempt, added from the user's own research (a Gemini "
            "conversation screenshot, 2026-09-27) into how Google Flights' "
            "frontend differs from the single-airline sites elsewhere in "
            "this file: no Cloudflare/DataDome-style third-party vendor to "
            "get past, but a deliberately obfuscated, rotating DOM and an "
            "internal (undocumented) RPC layer to find the real shape of "
            "instead. Kept deliberately minimal for the same reason "
            "air_india's OWN first round was minimal (see targets.py's "
            "air_india entry and page_actions.py's module docstring for "
            "that whole 16-round history): guessing a full form-fill/"
            "click-through flow against an SPA with zero real DOM "
            "evidence would mean writing thirty-plus lines of selectors "
            "with no way to check any of them, all of which would need "
            "rewriting the moment real evidence arrives anyway. Next real "
            "milestone, same as every other target's actual first run: "
            "`python -m scraper.run_scraper --target google_flights "
            "--routes DEL-BOM` and send back the terminal output plus "
            "whichever debug_google_flights_*.html/.json file(s) it "
            "writes — that real evidence (does the `?q=` URL alone "
            "produce a populated results page? does any XHR actually "
            "match `FlightsFrontendUi`? does a consent screen appear?) is "
            "what the next real fix gets built from, not a second guess."
        ),
    ),
    "makemytrip": ScrapeTarget(
        name="makemytrip",
        search_url_template=(
            "https://www.makemytrip.com/flight/search"
            "?itinerary={origin}-{destination}-{date}"
            "&tripType=O&paxType=A-1_C-0_I-0&intl=false&cabinClass=E"
        ),
        xhr_pattern=r".*(search|fareCal|flight).*",
        css_selectors={
            "flight_card": ".listingCard, [class*='listing'], [class*='flightCard']",
            "airline_name": "[class*='airlineName'], [class*='airline-name']",
            "fare": "[class*='fontBold'][class*='price'], [class*='blackFont'], [class*='price']",
        },
        confidence="blocked",
        notes=(
            "CONFIRMED BLOCKED on 2026-09-27, real test, not a guess: even "
            "with StealthyFetcher's humanize=True + geoip=True enabled, "
            "MakeMyTrip served a synthetic 40-byte '<html><body><p>200-OK"
            "</p></body></html>' placeholder instead of the real page — "
            "detected the automated browser and soft-blocked it rather "
            "than erroring. The exact same browser setup fetched a real "
            "421KB page from goindigo.in seconds later, so this is "
            "MakeMyTrip-specific defense, not a broken scraper. Treat as a "
            "stretch goal, not a near-term target — would need a real "
            "residential-proxy + more advanced fingerprint-evasion setup "
            "to revisit, which is a materially bigger investment than the "
            "single-airline sites below."
        ),
    ),
    "indigo": ScrapeTarget(
        name="indigo",
        search_url_template=(
            "https://www.goindigo.in/booking/flight-select"
            "?origin={origin}&destination={destination}&departureDate={date}"
            "&adults=1&children=0&infants=0"
        ),
        xhr_pattern=r".*(availability|fare|search).*",
        css_selectors={
            "flight_card": ".flight-card, [class*='flightCard'], [class*='flight-row']",
            "airline_name": None,  # single-airline site — set to "IndiGo" directly
            "fare": "[class*='fare-amount'], [class*='fareAmount'], [class*='price']",
        },
        confidence="verified",
        notes=(
            "CONFIRMED WORKING on 2026-09-27, real test, not a guess. "
            "StealthyFetcher loading the goindigo.in search page triggers "
            "a real XHR to a DIFFERENT host — "
            "https://6ewai.goindigo.in/r10next/web/fare-radar?origin=DEL "
            "— caught by this broad xhr_pattern because the path contains "
            "'fare'. That endpoint is NOT a point-to-point search: it's a "
            "'cheapest fares from this origin' widget that fans one origin "
            "out to several destination cities in one response, and its "
            "travelDate field ('2026-09-28') did not match the "
            "departureDate the code actually requested ('2026-10-18') — "
            "it appears to ignore that parameter. Parsed by the dedicated "
            "extract_indigo_fare_radar() in xhr_parser.py, not the generic "
            "heuristic parser. See CHANGES.md for the full real captured "
            "JSON."
        ),
    ),
    "air_india": ScrapeTarget(
        name="air_india",
        # REPLACED 2026-09-27: the previous URL here 404'd for real — a
        # genuine static "Not Found" page, confirmed by a real run, not a
        # guess about a guess. This is the REAL address bar URL after a
        # real manual search (user-provided). IMPORTANT CAVEAT, don't
        # skip past this: it carries NO query parameters — origin,
        # destination, and date are nowhere in it. That's a real signal,
        # not an oversight: this is an Angular-style hash-routed SPA
        # (`#/availability/departure`) that holds search state in the
        # browser's own memory after you type into the homepage widget,
        # then routes here only once you click Search. A plain "load this
        # URL" fetch is therefore likely to land on an empty/unfilled
        # form, not real results — {origin}/{destination}/{date} below
        # are silently unused until that's confirmed either way. Loading
        # this URL directly is still worth trying first (cheap to find
        # out), but if it comes back empty, the real fix is a Scrapling
        # `page_action` that fills the homepage form and clicks Search
        # before capture_xhr runs — see the note at the bottom of this
        # entry for exactly what's needed to write that for real instead
        # of guessing CSS selectors a second time.
        search_url_template="https://www.airindia.com/in/en/ibe/booking.html#/availability/departure",
        # Confirmed real path (see notes below): the actual search results
        # come from a DIFFERENT host than airindia.com — a `cbiz-booking`
        # API on `api.airindia.com` — same cross-host pattern IndiGo's
        # fare-radar endpoint showed. Narrowed from a generic keyword
        # pattern to the exact confirmed path segment so the fetcher isn't
        # relying on a guess anymore.
        xhr_pattern=r".*cbiz-booking.*air-bounds.*",
        css_selectors={
            "flight_card": "[class*='flight-card'], [class*='flightCard'], [class*='result-row']",
            "airline_name": None,  # single-airline site — set to "Air India" directly
            "fare": "[class*='fare'], [class*='price'], [class*='amount']",
        },
        confidence="verified",
        page_action_factory=build_air_india_page_action,
        notes=(
            "THIRD LIVE ATTEMPT found the real bug the second attempt's "
            "page_action was missing, on 2026-09-27, real run, not "
            "projected: `Locator.click: Timeout 45000ms exceeded ... "
            "element is not visible` on the origin input, after 83 retries "
            "over the full 45s. The user's follow-up debug HTML upload "
            "explained exactly why: the entire origin/destination/date/"
            "Search widget sits inside a literal "
            "`<div id=\"booking-widget-container\" style=\"display: "
            "none;\">` on this results page — hidden by default, not "
            "rendered-and-visible the way the previous DOM read assumed. "
            "The visible part of the page is a compact trip-summary strip "
            "with a small 'Modify' button "
            "(`#ai-pb-modifyTripButton`). Fixed: `page_actions.py` now has "
            "`_reveal_booking_widget()`, called first, which clicks Modify "
            "and waits for the container to actually report itself visible "
            "before touching anything inside it. Per the same honesty "
            "split as before (see page_actions.py's module docstring): "
            "VERIFIED — the `display:none` div and the Modify button both "
            "exist verbatim in the dump; the origin/destination field "
            "containers, autocomplete input, and Search button's disabled "
            "state are all still verified as before. UNVERIFIED — that "
            "clicking Modify is actually what flips that div's display; "
            "this is inferred from the DOM shape (nothing else in the dump "
            "plausibly toggles it), not yet observed post-click. If that "
            "inference is wrong, `_reveal_booking_widget()` now raises a "
            "clear, specific error and saves "
            "`debug_air_india_post_modify_click.html` immediately, instead "
            "of hanging for another 45s against the same hidden input. "
            "STILL A REAL GUESS, unchanged from before: the date-picker "
            "overlay's day-cell selector — `_pick_date()` saves "
            "`debug_air_india_datepicker_<date>.html` if every guess "
            "misses, same 'show, don't guess again' pattern. Next real "
            "milestone: re-run `python -m scraper.run_scraper --target "
            "air_india --routes DEL-BOM` and send back the terminal output "
            "plus whichever new debug_air_india_*.html/.json file(s) it "
            "writes. One real gotcha already caught from the fare data "
            "itself, not guessed: Mumbai has two airport codes in the "
            "air-bounds response — BOM and NMI (Navi Mumbai "
            "International) — that must both resolve to route_id "
            "'DEL-BOM', not two separate routes. See the parser's "
            "docstring and CHANGES.md for the full story."
        ),
    ),
    "spicejet": ScrapeTarget(
        name="spicejet",
        search_url_template=(
            "https://www.spicejet.com/#/book/flight-select"
            "?trip=O&origin={origin}&destination={destination}"
            "&departureDate={date}&adults=1&children=0&infants=0"
        ),
        xhr_pattern=r".*(availability|fare|search|flight).*",
        css_selectors={
            "flight_card": "[class*='flight-row'], [class*='fare-card'], [class*='flightCard']",
            "airline_name": None,  # single-airline site — set to "SpiceJet" directly
            "fare": "[class*='fare'], [class*='price'], [class*='amount']",
        },
        confidence="guessed",
        notes=(
            "Never run against the live site. SpiceJet's booking flow uses "
            "a hash-route ('#/book/...') in the guessed URL above, which "
            "is common for older Angular/React SPAs — if that's stale, the "
            "real current booking-flow URL needs a quick manual check "
            "first (visit spicejet.com, click through to a search, copy "
            "the real URL) before the DevTools XHR hunt even starts."
        ),
    ),
    "akasa": ScrapeTarget(
        name="akasa",
        search_url_template=(
            "https://www.akasaair.com/book/flight-search"
            "?tripType=O&origin={origin}&destination={destination}"
            "&departureDate={date}&adults=1&children=0&infants=0"
        ),
        xhr_pattern=r".*(availability|fare|search|flight).*",
        css_selectors={
            "flight_card": "[class*='flight-card'], [class*='flightCard'], [class*='result-row']",
            "airline_name": None,  # single-airline site — set to "Akasa Air" directly
            "fare": "[class*='fare'], [class*='price'], [class*='amount']",
        },
        confidence="guessed",
        notes=(
            "Never run against the live site — same starting-point-guess "
            "status as air_india/spicejet above. Akasa is the newest of "
            "the three (launched 2022), so its site is more likely to "
            "already be a modern JSON-API-backed SPA like IndiGo's, which "
            "is a good sign for the same fare-radar-style discovery "
            "working here too."
        ),
    ),
}


def build_search_url(target: ScrapeTarget, origin: str, destination: str, date: str) -> str:
    return target.search_url_template.format(origin=origin, destination=destination, date=date)
