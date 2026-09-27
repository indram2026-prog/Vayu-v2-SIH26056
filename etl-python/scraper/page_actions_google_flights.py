"""
Scrapling `page_action` callback for Google Flights.

HONESTY SPLIT (same policy as page_actions.py, read before trusting any
line below): unlike air_india's page_actions.py — which was rewritten 16
times against real `debug_air_india_*.html` dumps a human uploaded after
real runs — NOTHING here has ever touched a live browser, and there is no
real DOM capture of Google Flights to check anything against. Every
selector below is graded honestly as such, not dressed up as more certain
than it is.

WHY THIS FILE IS DELIBERATELY MINIMAL, not a guessed 500-line form-fill
saga: air_india's own history is the argument for restraint here. Its
very first round was also just "load the URL, see what comes back" — the
elaborate Modify-button/date-picker/autocomplete chain only got built
*after* real debug HTML proved the plain URL landed on an empty form.
Guessing that same multi-step chain for an entirely different, more
complex SPA with zero real evidence would mean writing 300 lines of
selectors this file has no way to check, all of which would need
rewriting anyway the moment real evidence arrives — strictly worse than
writing less now and letting the first real run's debug HTML drive what
actually needs fixing, same as it did for air_india.

VERIFIED — nothing. There is no verified line in this file yet.

PLAUSIBLE, DOCUMENTED PATTERN — not confirmed against this exact site,
but a real, publicly-documented mechanism, same confidence tier
targets.py uses for spicejet/akasa:
  - Google Flights' `?q=` deep-link query format ("Flights to X from Y on
    DATE") is a real, widely-used shareable-link pattern for
    google.com/travel/flights — if it holds, the URL alone should load
    directly into a populated results view, meaning THIS FILE may not
    even need to fill in any search-box fields itself, only handle
    whatever interstitial/consent screen appears before the real page
    does. That's the working theory `targets.py`'s search_url_template
    is built on.
  - Google's own consent interstitial (`"Before you continue to Google
    Search"`, seen full-page or as a modal, with an "Accept all" /
    "Reject all" button pair) is real, documented, well-known, and
    appears inconsistently based on region/cookie state — not specific
    to Flights, so `_dismiss_google_consent()` targets it the same
    generic, text-based way regardless of which of its several known
    layouts renders.

GENUINE FIRST GUESS — no source for this at all, most likely things to be
wrong on the first real run, in order of likely impact:
  - That the `?q=` URL format actually pre-populates a full results view
    rather than just the empty search page with the query text sitting
    unsubmitted in the box — UNVERIFIED, the single biggest open question
    this whole target rests on. If wrong, the fix is the same shape as
    air_india's `_reveal_booking_widget` saga: a real page_action that
    fills "Where from?" / "Where to?" and clicks Search, written only
    once real debug HTML shows what that markup actually looks like.
  - The exact shape/path of the internal RPC capture_xhr is watching for
    (`targets.py`'s `xhr_pattern`) — based on a general tip about Google's
    internal frontend-RPC naming conventions, not a captured real request.
  - Any css_selectors fallback in targets.py for this target — Google
    obfuscates result-row class names and rotates them across releases
    (the reason this whole approach leans on the XHR path first), so
    those selectors are a last-resort guess, expected to need a real
    dump to fix, not a confident starting point.

Next real milestone, same as every other target's first round: run it
for real and send back the terminal output plus whichever
`debug_google_flights_*.html`/`.json` file(s) it writes.
"""

from __future__ import annotations

from typing import Callable

# Text-based, not class-based — Google's consent dialog rotates markup far
# more than its button copy. Multiple phrasings covered because the real
# wording is known to vary by region/session, none of it confirmed for
# this specific flow.
_CONSENT_ACCEPT_SELECTORS = (
    "button:has-text('Accept all')",
    "button:has-text('I agree')",
    "div[role='button']:has-text('Accept all')",
)


def _dismiss_google_consent(page) -> None:
    """Best-effort dismiss of Google's cookie/consent interstitial, if one
    renders. Never raises — a missing or already-dismissed consent
    screen is the common case, not an error, and a real result page
    coming back empty afterward is what would actually surface a genuine
    problem here (same "diagnose via the real outcome, don't guess a
    fix for a maybe-problem" posture as the rest of this project).
    """
    for selector in _CONSENT_ACCEPT_SELECTORS:
        button = page.locator(selector)
        if button.count() == 0:
            continue
        try:
            button.first.wait_for(state="visible", timeout=3000)
            button.first.click()
            print(f"    [google_flights] dismissed consent screen via {selector!r}")
        except Exception:  # noqa: BLE001 — best-effort; if this doesn't
            # work, the run continues and the real page content (or lack
            # of it) is the honest signal of whether it mattered.
            continue
        return


def build_google_flights_page_action(route: dict, travel_date: str) -> Callable:  # noqa: ARG001
    """Returns a Scrapling `page_action` callback for one route.

    Deliberately does nothing beyond consent-dismissal and a settle wait
    for now — see this module's docstring for why guessing further here,
    with zero real DOM evidence, would very likely be wasted work. `route`
    and `travel_date` are accepted (matching `ScrapeTarget.page_action_factory`'s
    signature and air_india's own factory) but unused for now — the
    origin/destination/date are already baked into the URL via
    `targets.py`'s `search_url_template`, on the (unverified) theory that
    Google Flights' `?q=` deep link needs no further form interaction.
    """

    def page_action(page):
        _dismiss_google_consent(page)
        # Give the SPA time to hydrate and (if the `?q=` theory holds)
        # render real results before capture_xhr/HTML-fallback parsing
        # runs — same fixed-settle-time pattern used for every other
        # heavy-SPA target in this project (see fare_scraper.py's
        # `wait=6000` comment for why a fixed wait beats `network_idle`
        # for this class of site).
        page.wait_for_timeout(4000)
        return page

    return page_action
