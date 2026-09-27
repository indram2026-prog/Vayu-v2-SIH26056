"""
Scrapling `page_action` callbacks — the "fill the form, click Search"
step targets.py's air_india entry has been pointing at since the first
live attempt came back with `xhr_captured=0`.

HONESTY SPLIT — read this before trusting any one selector below. Unlike
most of this file's siblings, this one is graded per-line, not per-file,
because the input it was written against (`debug_air_india_DEL-BOM.html`,
a real 629KB DOM dump of
https://www.airindia.com/in/en/ibe/booking.html#/availability/departure,
uploaded by the user after a real run) only shows the page in its
*empty* state — the origin/destination widget as first rendered, before
anything was typed, and before the date button was ever clicked. That
means some of this is a transcription of real markup, and some of it is
still a guess about markup that dump never captured. Both are labelled
below, not blended together.

VERIFIED — present verbatim in the real dump, byte-for-byte:
  - `#onetrust-banner-sdk` / `#onetrust-accept-btn-handler` /
    `.onetrust-pc-dark-filter` — the site's cookie-consent banner, its
    "Accept All" button, and the SIBLING full-page dark overlay
    (`z-index:2147483645`, both under the same `#onetrust-consent-sdk`
    wrapper) that actually blocks clicks. This is what the THIRD real
    run first hit, and what an ELEVENTH real run hit again, byte-for-
    byte identical Playwright output — because the original fix waited
    for the wrong sibling (`#onetrust-banner-sdk`) to report itself
    hidden instead of the dark filter Playwright's own error names. See
    `_dismiss_cookie_consent`'s docstring for the full mismatch; it now
    waits on `.onetrust-pc-dark-filter` directly. All three selectors
    are OneTrust's own fixed IDs/classes (unchanged across any site using
    their SDK), not a guess about Air India's markup specifically.
  - `#booking-widget-container` — literally `style="display: none;"` in
    the raw HTML. THIS is the real cause of the timeout the first real
    run hit (`Locator.click: Timeout 45000ms exceeded ... element is not
    visible`, 83 retries, never once visible): the origin/destination/
    date/Search widget this whole file targets is a SINGLE hidden `<div
    id="booking-widget-container">` wrapping an `<ai-booking-widget
    id="global-booking-widget" ... ishome="true">` — it looks like a
    homepage widget fragment embedded (inert, display:none) on this
    results page, not something shown by default here. The visible part
    of this page is a compact trip-summary strip
    (`ai-pb-trip-details`, showing "Adult 1", "Economy", literal "_"
    placeholders for the empty route/date) with a small
    `button#ai-pb-modifyTripButton` labelled "Modify". Clicking it is
    the missing first step — nothing else in the DOM plausibly toggles
    that `display:none`, and Angular apps commonly drive a bound
    `[style.display]` off exactly this kind of "edit" trigger.
    UNVERIFIED CONTINUATION: that clicking Modify actually flips this
    div's display — inferred from the DOM shape, not yet observed after
    the click. If wrong, `page_action` now surfaces that immediately
    (see `_reveal_booking_widget`'s docstring) instead of hanging for
    45s against the same invisible input a second time.
  - `.ai-origin-destination__field--origin` / `--destination` — the two
    field containers. This is the ONLY reliable way to tell them apart:
    both inputs' own `aria-label` reads "Select origin airport" — a real
    quirk in Air India's own markup (confirmed in the dump, not a typo
    introduced here) — so selecting by aria-label would silently type
    into the origin box twice.
  - `input.ai-autocomplete-input` — the actual text input inside each
    field container.
  - `button.ai-button--primary[aria-label="Search"]` — confirmed
    `disabled=""` plus class `ai-button--disabled` in the empty-form
    state, which is *why* this code waits for `disabled` to clear before
    clicking rather than clicking immediately.
  - `button.ai-booking-widget__date-section[aria-label="Open date picker"]`
    — confirmed present, confirmed label text "Select Date" (i.e. no
    default date pre-filled). Confirmed EMPTY of any calendar/day-cell
    markup — the dump was taken before this button was ever clicked, so
    whatever it opens simply isn't on file yet.
  - `.ai-autocomplete-no-options.mat-mdc-option` — a real, permanently-
    disabled "no matches" placeholder row this autocomplete renders,
    confirmed by its own dedicated CSS rule (italic, centered text) and
    by the FOURTH real run's terminal output, verbatim: typing "DEL"
    resolved this exact class, `aria-disabled="true"`, and Playwright
    reported `element is not enabled` 84 times over the full 45s trying
    to click it. `_AUTOCOMPLETE_REAL_OPTION` now excludes it explicitly.
  - `button.mat-calendar-body-cell[aria-label='{M}/{D}/{Y}']` (no leading
    zeros, e.g. `aria-label="12/1/2026"`) — the real day-cell markup from
    Angular Material's `MatCalendar`, byte-for-byte from the FIFTH real
    run's own `debug_air_india_datepicker_*.html`. The two OLD aria-label
    guesses in `_pick_date` (a spelled-out month name) were flatly wrong,
    not close — see that function's docstring for how this alone (not
    any actual need to navigate months) explains the whole prior failure.
  - `#ai-pb-error-dialog` plus the generic `[mat-dialog-close]` attribute
    on its two buttons — Air India's own "Something went wrong" error
    dialog and Angular Material's built-in dismiss mechanism, both
    present verbatim in the SIXTH real run's fresh dump. THIS, not
    OneTrust again, is the real cause of that run's timeout:
    `Locator.click` on `#ai-pb-modifyTripButton` failed because a
    `.cdk-overlay-backdrop cdk-overlay-dark-backdrop
    cdk-overlay-backdrop-showing` "intercepts pointer events", 84
    retries, never once clearing — but the dump's own markup shows this
    backdrop belongs to a genuine `<mat-dialog-container>` wrapping
    `#ai-pb-error-dialog` ("The system is facing an unexpected issue and
    failed to process your request."), a completely different subtree
    from `#onetrust-consent-sdk`. Both dismiss controls inside it — the
    `.ai-pb-close-btn` (X) and `.ai-pb-primary-btn` ("Okay") — carry a
    bare `mat-dialog-close` attribute, confirmed on both elements in the
    dump: Angular Material's own generic "close this dialog" directive,
    not a guess tied to this one error message. `_dismiss_blocking_dialog()`
    targets that generic attribute (not either button's specific class)
    for exactly that reason — so it should also clear a differently-
    worded `MatDialog` if a future run hits one.
  - Clicking a `disabled` button is NOT a Playwright no-op. Verified by
    the fifth real run's own terminal output: `Locator.click` on the
    (still-disabled) Search button retried for the full 45s, `element is
    not enabled`, 84 times — identical shape to every other blocking-
    click failure in this file. The OLD code's comment asserting
    otherwise was simply incorrect. `page_action` now SKIPS the click
    entirely when `wait_for_function` reports the button never enabled,
    instead of attempting — and hanging on — a click that was never
    going to succeed.

PLAUSIBLE, NOT VERIFIED HERE — standard Angular Material framework
classes (the site is visibly built on `mat-mdc-*` components), same
confidence tier `targets.py` uses for spicejet/akasa ("matches a
documented, common pattern; not confirmed against this exact site"):
  - `.mat-mdc-autocomplete-panel .mat-mdc-option` for the airport
    dropdown list that should appear after typing.

GENUINE FIRST GUESS — no source for this at all yet, most likely thing
to be wrong on the first real run:
  - *Why* Air India's backend throws the `#ai-pb-error-dialog` error at
    all on a fresh page load, before the widget was ever touched —
    possibly bot-detection, possibly a flaky upstream call, possibly
    rate-limiting from six real runs in short succession. Nothing here
    confirms which. `_dismiss_blocking_dialog()` only handles the
    symptom (clear it so the flow can proceed); if it turns out to
    recur on every single run from here, that's a bigger problem this
    alone won't fix.
  - That clicking `#ai-pb-modifyTripButton` is what reveals
    `#booking-widget-container` (see `_reveal_booking_widget`'s
    docstring) — the button and the hidden container are both real, but
    the causal link between them is inferred, not observed.
  - That this autocomplete filters by airport/city NAME rather than
    IATA code — the working theory `_select_airport`'s retry is built
    to test, after typing "DEL" produced only the disabled no-options
    placeholder on the fourth real run. Not yet confirmed either way.
  - The two now-DEPRIORITIZED spelled-out-month aria-label guesses kept
    as a last-ditch fallback in `_pick_date` (see its docstring) — kept
    only for robustness, expected to keep missing.

ROUND 13 — a fifth overlay-shaped bug, answered with a generic fix
instead of a fifth named selector: a THIRTEENTH real run's own log
showed the OneTrust Accept button click itself raising an exception —
`[air_india] cookie banner present but Accept button click raised ... —
continuing anyway` — even though the dump from that same failed run
confirms the banner and its Accept button were both present and
correctly structured. Four prior fixes in this file (the dark filter
twice, the hidden widget container, the error dialog) each chased one
NAMED culprit. This one doesn't: `_neutralize_overlays()` strips
`pointer-events` from ANY full-viewport, high-z-index, fixed/absolute
element currently intercepting clicks, whatever it is, run as a
defensive pass before every risky click in `page_action` — not just
once. `_dismiss_blocking_dialog()` was also generalized the same
direction: it now detects on Angular Material's own generic
`mat-dialog-container` wrapper instead of `#ai-pb-error-dialog`'s
message-specific id, so a differently-worded MatDialog next time doesn't
need its own hand-written case either. UNVERIFIED: neither change has
been proven against a live run yet — both are new this pass, built on
standard CSS stacking rules and Angular Material's own documented
component structure rather than a guess about Air India's markup
specifically, but "should work generically" is not the same claim as
"observed to work here." Next real milestone is unchanged: run it for
real and send back the terminal output.
"""

from __future__ import annotations

from typing import Callable, Optional

_COOKIE_BANNER = "#onetrust-banner-sdk"
_COOKIE_ACCEPT_BUTTON = "#onetrust-accept-btn-handler"
_COOKIE_DARK_FILTER = ".onetrust-pc-dark-filter"
# GENERIC, not tied to any one dialog's copy or id: `mat-dialog-container`
# is Angular Material's own wrapper element for *every* MatDialog the app
# opens, whatever it says. Detecting on this instead of `#ai-pb-error-
# dialog` (the old, message-specific selector) means a differently-worded
# dialog Air India throws next — a session-timeout notice, a rate-limit
# warning, anything else built on the same MatDialog component — gets
# caught by the same code path, not silently ignored until it earns its
# own hand-written case. See _dismiss_blocking_dialog's docstring.
_DIALOG_CONTAINER = "mat-dialog-container"
_DIALOG_DISMISS_BUTTON = "[mat-dialog-close]"
_DIALOG_BACKDROP = ".cdk-overlay-backdrop.cdk-overlay-backdrop-showing"

# GENERIC overlay kill-switch. Every blocking-click bug found in this file
# so far (OneTrust's dark filter, Air India's own error dialog, and now a
# THIRTEENTH real run where even the OneTrust Accept button itself got
# blocked) has the identical shape: some full-viewport, high-z-index,
# fixed/absolute element sits on top of whatever we're trying to click,
# and Playwright retries for the full 45s timeout instead of failing fast.
# Each fix so far chased ONE named culprit — which only ever protects
# against that exact overlay recurring, not the next new one. This JS
# strips `pointer-events` from ANY element matching that shape (large,
# positioned, high z-index, currently intercepting), regardless of which
# widget produced it or what it's called, run as a defensive pass before
# every risky click in `page_action`. It does not touch anything smaller
# than 80% of the viewport (a cookie banner's own rounded corner panel,
# or a centered dialog box), so real interactive controls we still WANT
# to click — the Accept button, a dialog's own close button — are left
# alone; only the full-page backdrop behind them is neutralized.
_OVERLAY_NEUTRALIZE_JS = """
() => {
    const vw = window.innerWidth || document.documentElement.clientWidth;
    const vh = window.innerHeight || document.documentElement.clientHeight;
    let neutralized = 0;
    for (const el of document.querySelectorAll('body *')) {
        const cs = window.getComputedStyle(el);
        if (cs.display === 'none' || cs.visibility === 'hidden') continue;
        if (parseFloat(cs.opacity) === 0) continue;
        if (cs.position !== 'fixed' && cs.position !== 'absolute') continue;
        if (cs.pointerEvents === 'none') continue;
        const z = parseInt(cs.zIndex, 10);
        if (!Number.isFinite(z) || z < 1000) continue;
        const rect = el.getBoundingClientRect();
        if (rect.width < vw * 0.8 || rect.height < vh * 0.8) continue;
        el.style.setProperty('pointer-events', 'none', 'important');
        neutralized++;
    }
    return neutralized;
}
"""
_MODIFY_BUTTON = "#ai-pb-modifyTripButton"
_WIDGET_CONTAINER = "#booking-widget-container"
_ORIGIN_FIELD = ".ai-origin-destination__field--origin"
_DESTINATION_FIELD = ".ai-origin-destination__field--destination"
_AUTOCOMPLETE_INPUT = "input.ai-autocomplete-input"
_AUTOCOMPLETE_OPTION = ".mat-mdc-autocomplete-panel .mat-mdc-option"
_AUTOCOMPLETE_REAL_OPTION = f"{_AUTOCOMPLETE_OPTION}:not(.ai-autocomplete-no-options)"
_DATE_BUTTON = "button.ai-booking-widget__date-section"
_SEARCH_BUTTON = "button.ai-button--primary[aria-label='Search']"
_TRIP_TYPE_ONE_WAY = "label.ai-radio-group__option:has-text('One Way')"
# The NATIVE input, not the label — used only to VERIFY the click actually
# stuck (its real, unstyled `.checked` DOM property), never clicked
# directly (it's the CSS-hidden element the label wraps; see
# `_select_one_way`'s docstring for why clicking it directly would fail
# Playwright's visibility check).
_TRIP_TYPE_ONE_WAY_INPUT = "input.ai-radio-group__input[value='one-way']"

_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def _neutralize_overlays(page) -> int:
    """Generic backstop: strip pointer-events from any full-viewport,
    high-z-index overlay currently covering the page, whatever it is.

    Why this exists, and why NOW rather than another named-selector fix:
    the THIRTEENTH real run hit a new failure — the print in that run's
    own log, verbatim: `[air_india] cookie banner present but Accept
    button click raised ... — continuing anyway`. The debug HTML that run
    wrote back confirms the banner and its Accept button were genuinely
    present and correctly structured (DOM order: dark filter, then the
    banner as its later sibling, so by CSS stacking rules the banner
    SHOULD paint on top at equal z-index) — but the click still didn't
    land. Four separate overlay-shaped bugs in this file so far
    (`_dismiss_cookie_consent`'s dark filter, twice; `_reveal_booking_
    widget`'s hidden container; `_dismiss_blocking_dialog`'s error
    dialog) all share one root shape: SOME element the code didn't know
    to check for was sitting on top of the click target. Writing a fifth
    named case only protects against that fifth overlay recurring, not
    a sixth. This function instead handles the SHAPE of the problem: it
    hides (via `pointer-events: none`) anything fixed/absolute, z-index
    >= 1000, and covering at least 80% of the viewport in both
    dimensions — a deliberately narrow definition of \"full-page
    backdrop\", so a cookie banner's own rounded corner panel or a
    centered dialog box (real controls we still want clickable) are
    never touched, only the invisible-but-blocking layer behind them.

    Run as a defensive pass before every risky click in `page_action`,
    not just once at the top — a new overlay (a rate-limit warning, a
    session dialog, anything else) can appear between steps, not only on
    first load.

    UNVERIFIED: this exact mechanism has not yet been proven against a
    live run — it's new this pass, built from solid, standard CSS
    stacking-context rules rather than a guess about Air India's markup,
    but the honest thing to say is that no real run has confirmed it
    clears the specific interception the thirteenth run hit. If the next
    real run still fails on a blocked click, that click's exact selector
    and Playwright's own \"intercepts pointer events\" message naming the
    culprit is the next real thing to inspect.
    """
    try:
        count = page.evaluate(_OVERLAY_NEUTRALIZE_JS)
    except Exception:  # noqa: BLE001 — diagnostics/defense must never
        # crash the run; if evaluate() itself isn't available or throws,
        # the named-selector dismiss functions below are still attempted.
        return 0
    if count:
        print(
            f"    [air_india] neutralized {count} full-viewport overlay(s) "
            f"blocking pointer events"
        )
    return count


def _click_if_visible(page, selector: str, timeout: int = 2000) -> bool:
    """Click the first VISIBLE match for `selector` if one appears within
    `timeout`; otherwise do nothing and return False. Never hangs the
    full 45s default timeout on a match that exists but isn't visible.

    Why this exists: a real run found a NEW instance of this project's
    single most recurring failure shape — `.count() > 0` only proves an
    element is somewhere in the DOM, not that clicking it is safe.
    `_pick_date`'s old "confirm" step searched the whole page for any
    button whose text was "Apply" or "Done" — broad by design, since no
    real confirm-button markup for THIS date picker was ever captured —
    and on a real run it matched `#filter-apply-handler`, a real button
    belonging to some unrelated, hidden control elsewhere on the page,
    not the date picker's own confirm step. `.count() > 0` was true, so
    the old code clicked it unconditionally — Playwright then retried for
    the full 45s, `element is not visible`, 84 times, verbatim, the exact
    same failure shape as the Modify button (§11), the OneTrust dark
    filter (§12), and the disabled Search button (§14) before it. This
    helper makes "found but never visible" a fast, logged no-op instead
    of another 45-second hang, for any optional/best-effort click in this
    file going forward — not just this one call site.
    """
    locator = page.locator(selector)
    if locator.count() == 0:
        return False
    try:
        locator.first.wait_for(state="visible", timeout=timeout)
    except Exception:  # noqa: BLE001 — exists but never became visible in
        # time; the caller treats this as "nothing to click", not an error.
        return False
    locator.first.click()
    return True


def _dismiss_cookie_consent(page) -> None:
    """Accept Air India's OneTrust cookie banner before touching anything
    else on the page.

    Why this exists: the second real run got past `_reveal_booking_widget`
    cleanly and failed with a *different*, fully explicit Playwright
    error — clicking `#ai-pb-modifyTripButton` timed out because a
    `<div class="onetrust-pc-dark-filter ot-fade-in">` "intercepts
    pointer events", 83 retries, always the same overlay, never once
    clearing. The fresh `debug_air_india_DEL-BOM.html` from that same run
    confirms exactly what that overlay is: `#onetrust-consent-sdk` wraps
    a full-page dark filter at `z-index:2147483645` (deliberately above
    every other element on the page) plus the visible cookie banner
    `#onetrust-banner-sdk` — SIBLINGS, both direct children of
    `#onetrust-consent-sdk`, not one nested inside the other. The
    banner's own `#onetrust-accept-btn-handler` ("Accept All") button
    sits inside the banner, unhidden.

    BUG, FOUND AND FIXED HERE: an eleventh real run hit the *exact same*
    Playwright error, byte-for-byte — `.onetrust-pc-dark-filter`
    "intercepts pointer events", 83 retries — proving the original fix
    for this never actually worked. The reason, on inspection, is a
    plain mismatch between what this docstring always said and what the
    code below actually did: this correctly *named* the dark filter as
    the real blocking element above, but then waited for
    `#onetrust-banner-sdk` (the banner) to report itself hidden — a
    SIBLING element, not the one Playwright's own error names. Because
    OneTrust's CSS toggles `ot-hide` on each affected element
    individually (`.onetrust-pc-dark-filter.ot-hide{display:none
    !important}` is its own dedicated rule, not inherited from a parent
    or from the banner), the banner can genuinely report itself hidden
    while this sibling lingers a beat past its own 400ms fade-out
    (`.onetrust-pc-dark-filter.ot-fade-in{animation-duration:400ms}`,
    confirmed in the dump's own CSS) — or fails to clear at all if Accept
    didn't propagate to it that run. Waiting on the wrong element let
    this soft-fail "succeed" on runs where timing happened to cooperate,
    and silently do nothing useful on the ones where it didn't — exactly
    what an eleventh real run just proved. Fixed below: this now waits
    for `.onetrust-pc-dark-filter` itself, the actual element named in
    both real failures, not a proxy for it.

    Unlike the Modify-button reveal, none of this is a site-specific
    guess: both `onetrust-accept-btn-handler` and
    `onetrust-pc-dark-filter` are OneTrust's own fixed classes/IDs,
    identical across every site embedding their consent SDK. What's
    still NOT observed is a real post-click confirmation that Accept
    reliably clears the dark filter within a bounded time on THIS site's
    build — so this waits for it to report itself hidden, and if it
    doesn't, logs and continues rather than raising. Rationale for
    continuing instead of failing loud here (the opposite choice from
    `_reveal_booking_widget`): a stray overlay is a blocking-click
    problem the very next line will hit again and surface on its own,
    with its own clear Playwright timeout — there's no risk of silently
    limping forward on a wrong inference the way there would be for the
    widget-reveal step.
    """
    banner = page.locator(_COOKIE_BANNER)
    if banner.count() == 0:
        return  # no banner rendered at all — nothing to dismiss
    try:
        page.locator(_COOKIE_ACCEPT_BUTTON).first.click()
    except Exception as exc:  # noqa: BLE001 — banner present but button
        # not clickable for some reason; log it (this used to be a
        # silent `return`, which meant a genuinely failed Accept click
        # left no trace in the run's own output) and fall through to let
        # the next real click (Modify) surface whatever is actually
        # going on.
        print(
            f"    [air_india] cookie banner present but Accept button "
            f"click raised {exc!r} — continuing anyway"
        )
        return
    dark_filter = page.locator(_COOKIE_DARK_FILTER)
    if dark_filter.count() == 0:
        return  # no dark-filter overlay rendered this run — nothing more to wait for
    try:
        dark_filter.first.wait_for(state="hidden", timeout=8000)
    except Exception:  # noqa: BLE001 — soft failure by design, see
        # docstring: don't crash the run over a dismiss step that may
        # have actually worked even if the visibility check is flaky.
        print(
            "    [air_india] clicked cookie-consent accept button but "
            ".onetrust-pc-dark-filter never reported itself hidden — "
            "continuing anyway"
        )


def _dismiss_blocking_dialog(page) -> None:
    """Dismiss Air India's own transient "Something went wrong" error
    dialog before it can block the very next click (Modify).

    Why this exists: the sixth real run's terminal output showed a
    DIFFERENT overlay than the OneTrust one `_dismiss_cookie_consent`
    already handles — `Locator.click` on `#ai-pb-modifyTripButton` timed
    out because `.cdk-overlay-backdrop.cdk-overlay-dark-backdrop.
    cdk-overlay-backdrop-showing` "intercepts pointer events", 84
    retries, never once clearing. The fresh `debug_air_india_DEL-BOM.html`
    from that same run shows exactly what this overlay actually is, and
    it isn't OneTrust's: a real Angular Material `<mat-dialog-container>`
    wrapping `#ai-pb-error-dialog`, Air India's own error dialog reading
    "Something went wrong / The system is facing an unexpected issue and
    failed to process your request." — present verbatim, byte-for-byte,
    not inferred.

    VERIFIED: both dismiss controls inside it — the `.ai-pb-close-btn`
    (X) and `.ai-pb-primary-btn` ("Okay") — carry a bare `mat-dialog-
    close` attribute, confirmed on both elements in the dump. That's
    Angular Material's own built-in "close this dialog" directive, the
    same generic mechanism any `MatDialog` in the app would use, not a
    guess specific to this one error message — which is also why this
    targets the generic `[mat-dialog-close]` attribute rather than
    either button's specific class: if a differently-worded dialog (a
    different error, a session-timeout notice, anything else built on
    the same `MatDialog` component) blocks a future run the same way,
    this same one-line fix should still clear it.

    UNVERIFIED: *why* the backend throws this error at all on a fresh
    page load, before the widget was ever touched — see the module
    docstring's "GENUINE FIRST GUESS" section. This function only
    handles the symptom (dismiss so the flow can proceed); if the error
    keeps recurring every run from here, that's a different, bigger
    problem this alone won't fix.

    GENERALIZED this pass: the old check looked for `#ai-pb-error-
    dialog` specifically — this Air India error's own id, tied to its
    exact wording. Detecting on `mat-dialog-container` instead (Angular
    Material's own wrapper for every `MatDialog` the app opens, whatever
    it says) means a differently-worded dialog next time — a session
    notice, a rate-limit warning, anything else built on the same
    component — gets caught here too, instead of needing its own
    hand-written selector added after the fact like this one was.
    """
    dialog = page.locator(_DIALOG_CONTAINER)
    if dialog.count() == 0:
        return  # no dialog rendered this run — nothing to dismiss
    try:
        page.locator(_DIALOG_DISMISS_BUTTON).first.click()
    except Exception:  # noqa: BLE001 — dialog present but button not
        # clickable for some reason; fall through and let the very next
        # click (Modify) surface whatever is actually still going on.
        return
    try:
        page.locator(_DIALOG_BACKDROP).first.wait_for(state="hidden", timeout=5000)
    except Exception:  # noqa: BLE001 — soft failure by design, same
        # rationale as `_dismiss_cookie_consent`: don't crash the run over
        # a dismiss step that may have actually worked even if the
        # visibility check is flaky.
        print(
            "    [air_india] clicked error-dialog dismiss button but the "
            "backdrop never reported itself hidden — continuing anyway"
        )


def _reveal_booking_widget(page) -> None:
    """Click "Modify" and wait for the (real, confirmed `display:none`)
    booking-widget container to actually become visible before touching
    anything inside it.

    Why this exists: the first real run against a live browser hung for
    the full 45s Playwright timeout trying to click the origin input,
    then reported the input resolved fine but was "not visible" after 83
    retries. The debug HTML that run wrote back showed why: the entire
    widget lives inside `<div id="booking-widget-container"
    style="display: none;">` — literally hidden by default on this
    results page. The only plausible visible trigger in the same dump is
    `#ai-pb-modifyTripButton` ("Modify"), so this clicks that first.

    That the click actually reveals the container is the one inference
    here, not yet directly observed — so this raises a clear, specific
    error (and saves the post-click HTML) rather than silently falling
    through to the same 45s "not visible" timeout a second time if the
    inference turns out to be wrong.
    """
    page.locator(_MODIFY_BUTTON).first.click()
    try:
        page.locator(_WIDGET_CONTAINER).first.wait_for(state="visible", timeout=8000)
    except Exception as exc:  # noqa: BLE001 — surface a clear, specific
        # failure instead of letting the caller hang for another 45s
        # against the same hidden input.
        try:
            with open("debug_air_india_post_modify_click.html", "w", encoding="utf-8") as f:
                f.write(page.content())
            print(
                "    [air_india] clicked Modify but the widget never became "
                "visible — saved debug_air_india_post_modify_click.html"
            )
        except Exception:  # noqa: BLE001 — diagnostics must never crash the run
            pass
        raise RuntimeError(
            "Clicked #ai-pb-modifyTripButton but #booking-widget-container "
            "never became visible — the Modify-button guess in "
            "page_actions.py may be wrong, or it reveals something other "
            "than this container. See debug_air_india_post_modify_click.html."
        ) from exc


def _select_one_way(page) -> None:
    """Click the "One Way" trip-type radio option before touching dates.

    REAL BUG, found by inspecting a full-success `debug_air_india_DEL-BOM.html`
    (a run past every previous overlay/field/date bug in this file): origin
    (`ai-autocomplete-field--has-value`, bottom-label "Delhi"), destination
    (same class, "Mumbai"), and the depart date
    (`ai-booking-widget__date-field__value` reading "18 Oct 2026") were ALL
    filled in correctly. The Search button was still disabled anyway. The
    reason, confirmed in that same dump: the trip-type radio group defaults
    to `value="round-trip"` (`ai-radio-group__option--checked` sits on that
    label, not on "one-way"), and nothing in this file ever selects a trip
    type — it only ever calls `_pick_date` once, for the depart date. A
    round-trip search also requires a RETURN date; with the widget
    defaulted to round-trip and no return date ever picked, the form is
    correctly, silently invalid. Every previous round in this file chased
    an overlay, a hidden container, or a wrong selector — this is the first
    bug that isn't any of those: everything clicked fine, the *form itself*
    still wanted one more required field that was never in scope.

    This scraper only ever wants a plain one-way fare (matches `tripType=O`
    in the MakeMyTrip URL template right next to this target in
    targets.py) — so the fix is to switch the widget to One Way, not to
    also fill in a return date (which would fetch a fare bundled with a
    return leg instead of the one-way fare this project collects).

    The actual `<input type="radio">` is visually hidden by the site's own
    CSS (`position:absolute;opacity:0;width:0;height:0` — confirmed in the
    dump, the standard hide-the-input/style-the-label pattern), so clicking
    the `<input>` directly would fail Playwright's actionability check
    exactly like every other hidden-element bug already fixed in this
    file. This clicks the visible `<label>` wrapper instead — the same
    element a real user's cursor actually lands on.

    ROUND 16 — the first guess (click the label, trust it, move on) was
    itself unverified and turned out to be insufficient: a real run with
    that fix in place still came back with Search disabled, and the fresh
    debug HTML it saved shows the SAME `round-trip` label still carrying
    `ai-radio-group__option--checked` — the click either didn't land, or
    landed and got overwritten by something else before the run ended,
    with nothing in the terminal output to tell those two apart. That's a
    real gap in this function's own honesty split from the last round: it
    logged nothing on the (assumed) success path, so a silent failure and
    a silent success were indistinguishable from the outside — exactly the
    kind of unverified inference this file's own methodology (see the
    module docstring) is supposed to catch before calling something done.

    Fixed here: this now VERIFIES the click actually stuck, by reading the
    real, native `<input>`'s own `.checked` DOM property (not the styled
    label's class, which is just as capable of lagging or lying as the
    thing it's meant to confirm) via `wait_for_function`. If it isn't
    checked yet, this retries the label click once — covers the
    possibility that the first click landed before Angular finished
    binding the handler, or before some async default-restore overwrote
    it. If it's STILL not checked after the retry, this stops guessing a
    third time blind: it saves the real live DOM to
    `debug_air_india_trip_type.html` and logs clearly, so the next real
    run finally supplies the evidence (is the click not landing at all? is
    something resetting it afterward? is the selector itself stale?)
    needed to fix this for real instead of re-guessing.

    Not raised as a hard failure (unlike `_reveal_booking_widget`'s
    contract): a missed trip-type switch degrades the same way a missed
    airport or missed date already does in this file — Search stays
    disabled, the run finishes as a clean, diagnosable "empty" rather than
    a crash.
    """
    option = page.locator(_TRIP_TYPE_ONE_WAY)
    if option.count() == 0:
        return  # no trip-type selector rendered this run — nothing to switch

    def _checked() -> bool:
        try:
            page.wait_for_function(
                "sel => { const el = document.querySelector(sel); return !!(el && el.checked); }",
                arg=_TRIP_TYPE_ONE_WAY_INPUT,
                timeout=1500,
            )
            return True
        except Exception:  # noqa: BLE001 — not checked (yet); caller decides
            return False

    for attempt in (1, 2):
        try:
            option.first.wait_for(state="visible", timeout=5000)
            option.first.click()
        except Exception as exc:  # noqa: BLE001 — best-effort; a failed
            # click attempt here still gets the same evidence-dump
            # treatment below if the retry also doesn't result in a
            # checked input.
            print(
                f"    [air_india] One Way click attempt {attempt} raised "
                f"{exc!r}"
            )
        if _checked():
            return  # verified — the earlier silent-assumption bug this
            # round fixes is exactly not doing this check at all.

    # Both attempts failed to produce a checked input — stop guessing and
    # save real evidence instead, same contract as every other "guess
    # failed" branch in this file (_pick_date, _select_airport).
    try:
        with open("debug_air_india_trip_type.html", "w", encoding="utf-8") as f:
            f.write(page.content())
        print(
            "    [air_india] clicked One Way twice but the underlying "
            "radio input never reported itself checked — saved "
            "debug_air_india_trip_type.html for real evidence"
        )
    except Exception:  # noqa: BLE001 — diagnostics must never crash the run
        pass


def _select_airport(page, field_selector: str, code: str, name: Optional[str]) -> bool:
    """Type into one origin/destination box and click the matching real
    suggestion. Returns True if a real option was clicked, False if it
    gave up (see below) — mirrors `_pick_date`'s "diagnose, don't hang"
    contract, since a missed origin/destination degrades the same way a
    missed date does: Search stays disabled, the run finishes as a clean,
    diagnosable "empty" instead of crashing or hanging.

    VERIFIED, from the FOURTH real run's actual terminal output: typing
    the IATA `code` (e.g. "DEL") and waiting for
    `.mat-mdc-autocomplete-panel .mat-mdc-option` — the OLD selector,
    with no exclusion — resolved to
    `<mat-option ... class="... ai-autocomplete-no-options ...
    mdc-list-item--disabled">`, a real, distinct, permanently-disabled
    placeholder Air India's own CSS defines for "no matches" (confirmed
    in the dump: `.ai-autocomplete-no-options.mat-mdc-option{...
    font-style:italic; text-align:center}`, i.e. an intentional empty-
    state row, not a loading flicker). The old code picked it as "the
    first suggestion" and spent the full 45s retrying a click Playwright
    itself reported as `element is not enabled` 84 times. That bug is
    fixed here unconditionally: `_AUTOCOMPLETE_REAL_OPTION` excludes it,
    so a disabled placeholder can never again be waited on or clicked as
    if it were a real match.

    UNVERIFIED HYPOTHESIS for WHY nothing matched "DEL" — not yet
    observed to be true, just the most likely explanation given a
    dedicated disabled-placeholder component exists at all: this
    autocomplete may filter on city/airport NAME rather than IATA code.
    So this now retries once with `name` (e.g. "Delhi") if the code
    produces only the placeholder or nothing — a hypothesis this retry
    itself will confirm or kill on the next real run. If BOTH the code
    and the name come up empty, this stops guessing a third time: it
    saves the real live autocomplete-panel HTML to disk and returns
    False rather than clicking anything blind.
    """
    input_sel = f"{field_selector} {_AUTOCOMPLETE_INPUT}"
    box = page.locator(input_sel)

    def _type_and_wait_for_real_option(text: str) -> bool:
        box.click()
        box.fill("")
        # `press_sequentially` sends real per-key events, which Angular's
        # (input)-bound autocomplete needs to fire its filter — `.fill()`
        # sets the value in one shot and typically does NOT trigger it.
        box.press_sequentially(text, delay=80)
        try:
            # The CDK overlay panel renders appended to <body>, not nested
            # under the field — so this searches page-wide, not scoped to
            # field_selector.
            page.locator(_AUTOCOMPLETE_REAL_OPTION).first.wait_for(
                state="visible", timeout=6000
            )
            return True
        except Exception:  # noqa: BLE001 — no real option for this text;
            # caller decides whether to retry with a different string.
            return False

    found = _type_and_wait_for_real_option(code)
    tried_name = False
    if not found and name:
        tried_name = True
        found = _type_and_wait_for_real_option(name)

    if not found:
        # REAL BUG, found via a real run: both field selectors contain the
        # literal substring "origin" — `_ORIGIN_FIELD` is
        # ".ai-origin-destination__field--origin" AND `_DESTINATION_FIELD`
        # is ".ai-origin-destination__field--destination", which itself
        # contains "ai-ORIGIN-destination" as part of the shared
        # container class name. A naive `"origin" in field_selector`
        # check is therefore true for BOTH fields, so this always
        # resolved to "origin" — confirmed by a real run's own log
        # printing "no real airport suggestion ... in origin field" TWICE
        # in a row (once for the real origin, once for the destination),
        # and silently overwriting the same
        # debug_air_india_autocomplete_origin.html both times, losing the
        # destination field's own diagnostic evidence entirely. The test
        # fake's own `_FakeLocator.click()` already had a comment flagging
        # this exact substring trap and checked the more specific
        # "--destination" suffix first — this real function never got the
        # matching fix. Fixed the same way here: check "--destination"
        # first.
        field_tag = "destination" if "--destination" in field_selector else "origin"
        try:
            with open(
                f"debug_air_india_autocomplete_{field_tag}.html", "w", encoding="utf-8"
            ) as f:
                f.write(page.content())
            print(
                f"    [air_india] no real airport suggestion for code={code!r}"
                f"{' or name=' + repr(name) if tried_name else ''} in "
                f"{field_tag} field — saved "
                f"debug_air_india_autocomplete_{field_tag}.html"
            )
        except Exception:  # noqa: BLE001 — diagnostics must never crash the run
            pass
        return False

    # Matches on EITHER the IATA code or the city name (whichever this
    # dropdown actually renders text as is exactly what the retry above
    # is for finding out) — case-insensitive, first match wins.
    options = page.locator(_AUTOCOMPLETE_REAL_OPTION)
    match = options.filter(has_text=code)
    if name and match.count() == 0:
        match = options.filter(has_text=name)
    if match.count() == 0:
        # A real (non-placeholder) option list rendered but neither the
        # code nor the name text-matched any row — fall back to the
        # first real suggestion rather than giving up on a filled panel.
        match = options.first
    match.first.click()
    return True


def _pick_date(page, travel_date: str) -> bool:
    """Open the date picker and try to select `travel_date` (ISO
    "YYYY-MM-DD"). Returns True if a day cell was actually clicked.

    VERIFIED, from the fresh `debug_air_india_datepicker_2026-10-18.html`
    the fifth real run wrote (saved because the OLD guesses below all
    missed): the real, rendered day-cell markup is
    `<button type="button" class="mat-calendar-body-cell ..."
    aria-label="12/1/2026">`, byte-for-byte — Angular Material's
    `MatCalendar`, `aria-label` as US-style `M/D/YYYY` with NO leading
    zeros on month or day (e.g. "12/1/2026", not "12/01/2026" or
    "1 December 2026"). This is a fixed property of the Angular Material
    component itself, not something that varies month to month, so it's
    treated as verified for every month, not just December (the one
    month this particular dump happened to capture — see below for why).

    The OLD guesses (`"<day> <Month> <year>"` / `"<day> <Month>"`, e.g.
    "18 October 2026") were simply the wrong format, full stop — not
    close, not partially right. That explains the whole prior failure:
    the run's own debug dump shows this landed on DECEMBER (`12/1/2026`
    was the first cell), after two "next month" clicks from the loop
    below — meaning the calendar's *initial* view was already on
    OCTOBER, our actual target month, and every attempt would have
    matched on attempt #1 with zero navigation needed, had the format
    been right from the start. The "next month" advancing itself was
    real and worked correctly (confirmed by reaching December at all);
    it just kept firing pointlessly against a selector that could never
    match, burning through all 3 attempts before giving up.

    Tries, in order, now:
      1. VERIFIED: `button.mat-calendar-body-cell[aria-label='{M}/{D}/{Y}']`
         with no leading zeros — the real format above.
      2. Two old, now-DISPROVEN "<day> <Month>[<year>]" guesses, kept
         only as a last-ditch fallback in case some other calendar
         instance on this site renders differently — expected to keep
         missing based on current evidence.
    If nothing matches after up to 3 months of "next month" clicks, it
    dumps the opened calendar's HTML to disk and returns False — the
    Search button then simply stays disabled, which shows up as a
    normal, diagnosable "empty" outcome rather than a crash.
    """
    page.locator(_DATE_BUTTON).first.click()
    page.wait_for_timeout(1000)  # let whatever overlay this opens render

    year, month, day = travel_date.split("-")
    month_name = _MONTHS[int(month) - 1]
    month_num = str(int(month))  # strip any leading zero
    day_num = str(int(day))  # strip any leading zero

    candidates = [
        f"button.mat-calendar-body-cell[aria-label='{month_num}/{day_num}/{year}']",
        f"[aria-label*='{day_num} {month_name} {year}']",
        f"[aria-label*='{day_num} {month_name}']",
    ]
    for _ in range(3):  # allow up to 3 "next month" clicks if not visible yet
        for sel in candidates:
            cell = page.locator(sel)
            if cell.count() > 0:
                cell.first.click()
                # Some date pickers need an explicit confirm after picking
                # a day. BUG FIXED HERE, found via a real run: this used to
                # be an unconditional `.count() > 0` click, page-wide, on
                # any button whose text was "Apply" or "Done" — no real
                # confirm-button markup for THIS date picker was ever
                # captured, so the search was left broad on purpose. On a
                # real run that broad search matched `#filter-apply-
                # handler`, an unrelated hidden control elsewhere on the
                # page, and hung the full 45s clicking an invisible
                # element. `_click_if_visible` makes this the fast, safe
                # no-op it was always meant to be: a real confirm button
                # (if one exists here at all) will already be visible
                # right after picking a day, so a short 2s wait is plenty.
                _click_if_visible(
                    page, "button:has-text('Apply'), button:has-text('Done')", timeout=2000
                )
                return True
        next_month = page.locator(
            "[aria-label*='Next month'], .ai-pb-calender-arrow.next"
        )
        if next_month.count() == 0:
            break
        next_month.first.click()
        page.wait_for_timeout(500)

    # Every guess failed — save real evidence instead of a fourth guess.
    try:
        with open(f"debug_air_india_datepicker_{travel_date}.html", "w", encoding="utf-8") as f:
            f.write(page.content())
        print(
            f"    [air_india] date picker opened but no day cell matched — "
            f"saved debug_air_india_datepicker_{travel_date}.html for real selectors"
        )
    except Exception:  # noqa: BLE001 — diagnostics must never crash the run
        pass
    return False


def build_air_india_page_action(route: dict, travel_date: str) -> Callable:
    """Returns a Scrapling `page_action` callback bound to one route.

    `route` is one entry from shared/routes.json — uses `origin`,
    `destination`, and (if present) `origin_name`/`destination_name`.
    """
    origin = route["origin"]
    destination = route["destination"]
    origin_name = route.get("origin_name")
    destination_name = route.get("destination_name")

    def page_action(page):
        # Generic overlay backstop runs FIRST, before the named-selector
        # dismiss functions even get a chance — see `_neutralize_
        # overlays`'s docstring for why: the thirteenth real run showed
        # even the OneTrust Accept button itself, a click these named
        # functions already targeted correctly, can still get blocked by
        # something neither of them checks for. Stripping pointer-events
        # from any full-viewport high-z-index layer before anything else
        # runs gives every click below a clean shot, regardless of which
        # named overlay (if any) is also present.
        _neutralize_overlays(page)
        _dismiss_cookie_consent(page)
        _dismiss_blocking_dialog(page)
        # Run it again right before the first click that actually matters
        # (Modify) — a fresh overlay can appear between steps, not only
        # on first load, and this call is a cheap, idempotent no-op when
        # there's nothing left to neutralize.
        _neutralize_overlays(page)
        _reveal_booking_widget(page)
        # Must happen before _pick_date: the widget defaults to Round
        # Trip, which requires a return date this file never picks — see
        # `_select_one_way`'s docstring for how that (not an overlay, not
        # a selector) turned out to be why Search stayed disabled even
        # after every field this file DOES fill in was confirmed correct.
        _select_one_way(page)
        # Neither call raises on a miss — a missed airport degrades to a
        # diagnosable "empty" outcome (see `_select_airport`'s docstring)
        # exactly like a missed date does, so both fields are always
        # attempted even if the first one didn't find a real match.
        _select_airport(page, _ORIGIN_FIELD, origin, origin_name)
        _select_airport(page, _DESTINATION_FIELD, destination, destination_name)
        _pick_date(page, travel_date)
        _neutralize_overlays(page)  # backstop before the Search click too

        search_btn = page.locator(_SEARCH_BUTTON)
        search_btn.first.wait_for(state="visible", timeout=5000)
        search_enabled = True
        try:
            # Wait for the real `disabled` attribute (confirmed present
            # on the button in the empty-form state) to clear.
            page.wait_for_function(
                "sel => { const el = document.querySelector(sel); return el && !el.disabled; }",
                arg=_SEARCH_BUTTON,
                timeout=10000,
            )
        except Exception:  # noqa: BLE001 — button never reported itself
            # enabled; see below for why this now SKIPS the click instead
            # of attempting it anyway.
            search_enabled = False

        if search_enabled:
            search_btn.first.click()
        else:
            # VERIFIED WRONG, from the fifth real run's own terminal
            # output: the OLD comment here claimed "a disabled click is a
            # harmless no-op" — that is false. Playwright's `.click()`
            # actively retries a disabled element for the FULL 45s
            # timeout (`element is not enabled`, 84 retries, verbatim),
            # exactly like every other blocking-click failure in this
            # file. Clicking a still-disabled Search button doesn't
            # degrade gracefully — it hangs just as hard as clicking a
            # hidden one did in `_reveal_booking_widget`. So this now
            # skips the click entirely when the button never became
            # enabled, and lets the run finish immediately as a clean,
            # diagnosable "empty" (upstream date/airport selection is
            # what actually failed) instead of wasting the full timeout
            # proving what `wait_for_function` already just proved.
            print(
                "    [air_india] Search button never became enabled — "
                "skipping the click instead of hanging on a disabled "
                "element for the full timeout"
            )
        page.wait_for_timeout(3000)  # give the air-bounds XHR time to fire
        return page

    return page_action
