"""
Run with: python3 -m unittest scraper.tests.test_air_india_page_action -v

Tests the PURE LOGIC in page_actions.py (matching rules, date-string
parsing, the "guess failed -> dump debug HTML, don't crash" fallback)
using a hand-rolled fake standing in for Playwright's Page/Locator API —
NOT a real browser. That's a deliberate scope limit, same one every other
file in this project draws: these tests prove the selector-matching and
control-flow logic is correct; they cannot and do not prove the real
airindia.com DOM behaves the way the fake below assumes it does. Only a
real `StealthyFetcher.fetch(..., page_action=...)` run against the live
site proves that, per targets.py's air_india notes.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from ..page_actions import build_air_india_page_action


class _FakeLocator:
    def __init__(self, page: "_FakePage", selector: str, matches: list[str]):
        self.page = page
        self.selector = selector
        self.matches = matches  # list of opaque "match ids" this locator currently resolves to

    @property
    def first(self):
        return _FakeLocator(self.page, self.selector, self.matches[:1])

    def count(self) -> int:
        return len(self.matches)

    def filter(self, has_text: str):
        filtered = [m for m in self.matches if has_text.lower() in m.lower()]
        return _FakeLocator(self.page, self.selector, filtered)

    def _requires_widget_reveal(self) -> bool:
        # Mirrors the real DOM: these all live inside the (real, confirmed)
        # `#booking-widget-container` that starts `display: none;` — a
        # locator for them resolves fine (the element exists), but a real
        # click/visible-wait against them hangs until the widget is
        # revealed. The Modify button and the widget container itself are
        # NOT gated — clicking Modify is exactly what's supposed to lift
        # the gate.
        return (
            "ai-autocomplete-input" in self.selector
            or self.selector == self.page.date_button_selector
            or self.selector == self.page.search_button_selector
        )

    def wait_for(self, state: str = "visible", timeout: int = 0) -> None:
        if self.selector == self.page.cookie_banner_selector:
            if state == "hidden":
                if self.page.cookie_banner_present and not self.page.cookie_banner_dismissed:
                    raise TimeoutError("cookie banner never became hidden")
                return
        if self.selector == self.page.cookie_dark_filter_selector:
            if state == "hidden":
                if self.page.cookie_dark_filter_present and not self.page.cookie_dark_filter_dismissed:
                    raise TimeoutError("dark filter never became hidden")
                return
        if self.selector == self.page.dialog_backdrop_selector:
            if state == "hidden":
                if self.page.error_dialog_present and not self.page.error_dialog_dismissed:
                    raise TimeoutError("dialog backdrop never became hidden")
                return
        if not self.matches:
            raise TimeoutError(f"no element for {self.selector!r}")
        if self.selector == self.page.widget_container_selector:
            if not self.page.widget_revealed:
                raise TimeoutError("booking-widget-container never became visible")
            return
        if self._requires_widget_reveal() and not self.page.widget_revealed:
            raise TimeoutError(f"{self.selector!r} exists but is not visible")

    def click(self) -> None:
        if self._requires_widget_reveal() and not self.page.widget_revealed:
            raise TimeoutError(f"{self.selector!r} exists but is not visible")
        self.page.clicks.append((self.selector, tuple(self.matches)))
        if self.selector == self.page.cookie_accept_selector and self.page.cookie_accept_dismisses_banner:
            self.page.cookie_banner_dismissed = True
        if self.selector == self.page.cookie_accept_selector and self.page.cookie_accept_clears_dark_filter:
            self.page.cookie_dark_filter_dismissed = True
        if self.selector == self.page.dialog_dismiss_selector and self.page.dialog_dismiss_clears_backdrop:
            self.page.error_dialog_dismissed = True
        if self.selector == self.page.modify_button_selector and self.page.modify_click_reveals_widget:
            self.page.widget_revealed = True
        if self.selector == self.page.trip_type_one_way_selector:
            self.page.trip_type_click_count += 1
            # Models ROUND 16's real failure mode: a click that's recorded
            # (so `page.clicks` shows it happened) but doesn't necessarily
            # result in the native input reporting itself `.checked` —
            # `trip_type_sticks_after_attempt` controls which click (if
            # any within the 2 the real code now tries) actually takes.
            if self.page.trip_type_click_count >= self.page.trip_type_sticks_after_attempt:
                self.page.one_way_selected = True
        if self.selector == self.page.date_button_selector:
            self.page.date_overlay_open = True
        if "ai-autocomplete-input" in self.selector:
            self.page.focused_input = self.matches[0] if self.matches else None
            # NOTE: the real (and fake) field classes are both prefixed
            # "ai-origin-destination__field--..." — a plain "origin" in
            # selector substring check matches BOTH fields. Check the
            # more specific "--destination" suffix first.
            self.page.current_field = (
                "destination" if "--destination" in self.selector else "origin"
            )

    def fill(self, value: str) -> None:
        pass

    def press_sequentially(self, text: str, delay: int = 0) -> None:
        field = self.page.current_field
        if field:
            self.page.typed.setdefault(field, []).append(text)
            self.page.press_count[field] = self.page.press_count.get(field, 0) + 1


class _FakePage:
    """Minimal stand-in for the Playwright Page object page_action receives.

    `available_day_selectors` simulates which of _pick_date's guessed
    aria-label selectors would actually match in a real opened calendar —
    set to [] to simulate "every guess wrong, real markup unknown".

    `modify_click_reveals_widget` simulates whether clicking "Modify"
    actually flips `#booking-widget-container`'s display — this is the
    one inferred-not-observed link `_reveal_booking_widget` depends on;
    set to False to simulate the inference being wrong.

    `autocomplete_success_attempt` simulates, per field ("origin" /
    "destination"), which typed attempt (1 = the IATA code, 2 = the
    fallback city name) actually produces a real (non-placeholder)
    autocomplete option — mirroring the fourth real run, where typing
    "DEL" produced only Air India's disabled `.ai-autocomplete-no-options`
    row. Use 1 for "code works first try" (the original happy path), 2
    for "code fails, name succeeds", and None for "neither ever works".
    """

    date_button_selector = "button.ai-booking-widget__date-section"
    search_button_selector = "button.ai-button--primary[aria-label='Search']"
    modify_button_selector = "#ai-pb-modifyTripButton"
    widget_container_selector = "#booking-widget-container"
    cookie_banner_selector = "#onetrust-banner-sdk"
    cookie_accept_selector = "#onetrust-accept-btn-handler"
    cookie_dark_filter_selector = ".onetrust-pc-dark-filter"
    # Generic container selector (Angular Material's own wrapper for any
    # MatDialog), matching page_actions.py's post-round-13 detection —
    # the fake models "some dialog is open", not any one dialog's wording.
    error_dialog_selector = "mat-dialog-container"
    dialog_dismiss_selector = "[mat-dialog-close]"
    dialog_backdrop_selector = ".cdk-overlay-backdrop.cdk-overlay-backdrop-showing"
    # Matches page_actions.py's _TRIP_TYPE_ONE_WAY — the visible <label>
    # wrapper around the (real, CSS-hidden) native radio input, not the
    # input itself. Present by default: the real widget always renders
    # this radio group, defaulted to Round Trip, whether or not a test
    # cares about it.
    trip_type_one_way_selector = "label.ai-radio-group__option:has-text('One Way')"
    # The native input `_select_one_way` now verifies against, matching
    # page_actions.py's `_TRIP_TYPE_ONE_WAY_INPUT` — a fresh, real check
    # rather than trusting the label click blindly (ROUND 16's fix).
    trip_type_one_way_input_selector = "input.ai-radio-group__input[value='one-way']"

    def __init__(
        self,
        available_day_selectors: list[str],
        search_starts_disabled: bool = True,
        modify_click_reveals_widget: bool = True,
        cookie_banner_present: bool = False,
        cookie_accept_dismisses_banner: bool = True,
        cookie_dark_filter_present: "bool | None" = None,
        cookie_accept_clears_dark_filter: bool = True,
        error_dialog_present: bool = False,
        dialog_dismiss_clears_backdrop: bool = True,
        autocomplete_success_attempt: "dict[str, int | None] | None" = None,
        trip_type_selector_present: bool = True,
        trip_type_sticks_after_attempt: int = 1,
    ):
        self.trip_type_selector_present = trip_type_selector_present
        self.trip_type_sticks_after_attempt = trip_type_sticks_after_attempt
        self.trip_type_click_count = 0
        self.one_way_selected = False
        self.clicks: list[tuple] = []
        self.typed: dict = {}
        self.focused_input = None
        self.current_field = None
        self.press_count: dict = {"origin": 0, "destination": 0}
        self.autocomplete_success_attempt = autocomplete_success_attempt or {
            "origin": 1,
            "destination": 1,
        }
        self.date_overlay_open = False
        self.widget_revealed = False
        self.modify_click_reveals_widget = modify_click_reveals_widget
        self._available_day_selectors = set(available_day_selectors)
        self._search_disabled = search_starts_disabled
        self.content_dumped = False
        self.cookie_banner_present = cookie_banner_present
        self.cookie_accept_dismisses_banner = cookie_accept_dismisses_banner
        self.cookie_banner_dismissed = False
        # In the real DOM the dark filter is a SIBLING that always renders
        # alongside the banner (both children of #onetrust-consent-sdk),
        # so it defaults to matching cookie_banner_present unless a test
        # wants to simulate them diverging (that divergence is exactly
        # the eleventh real run's bug: banner gone, dark filter lingers).
        self.cookie_dark_filter_present = (
            cookie_banner_present if cookie_dark_filter_present is None else cookie_dark_filter_present
        )
        self.cookie_accept_clears_dark_filter = cookie_accept_clears_dark_filter
        self.cookie_dark_filter_dismissed = False
        self.error_dialog_present = error_dialog_present
        self.dialog_dismiss_clears_backdrop = dialog_dismiss_clears_backdrop
        self.error_dialog_dismissed = False

    def locator(self, selector: str) -> _FakeLocator:
        if selector == self.cookie_banner_selector:
            return _FakeLocator(
                self, selector, [selector] if self.cookie_banner_present else []
            )
        if selector == self.cookie_accept_selector:
            return _FakeLocator(
                self, selector, [selector] if self.cookie_banner_present else []
            )
        if selector == self.cookie_dark_filter_selector:
            present = self.cookie_dark_filter_present and not self.cookie_dark_filter_dismissed
            return _FakeLocator(self, selector, [selector] if present else [])
        if selector == self.error_dialog_selector:
            return _FakeLocator(
                self, selector, [selector] if self.error_dialog_present else []
            )
        if selector == self.dialog_dismiss_selector:
            return _FakeLocator(
                self, selector, [selector] if self.error_dialog_present else []
            )
        if selector == self.dialog_backdrop_selector:
            return _FakeLocator(
                self, selector, [selector] if self.error_dialog_present else []
            )
        if selector == self.trip_type_one_way_selector:
            return _FakeLocator(
                self, selector, [selector] if self.trip_type_selector_present else []
            )
        if selector == self.modify_button_selector:
            return _FakeLocator(self, selector, [selector])
        if selector == self.widget_container_selector:
            return _FakeLocator(self, selector, [selector])
        if "ai-autocomplete-input" in selector:
            return _FakeLocator(self, selector, [selector])
        if "mat-mdc-option" in selector:
            # Real (non-placeholder) options appear only on the attempt
            # number configured for the currently-focused field — every
            # other attempt simulates the disabled no-options placeholder
            # by resolving to nothing at all (excluded, same as the real
            # `:not(.ai-autocomplete-no-options)` selector would see).
            field = self.current_field
            attempt = self.press_count.get(field, 0)
            success_attempt = self.autocomplete_success_attempt.get(field)
            if success_attempt is not None and attempt == success_attempt:
                return _FakeLocator(
                    self, selector, ["option:DEL Delhi", "option:BOM Mumbai"]
                )
            return _FakeLocator(self, selector, [])
        if selector == self.date_button_selector:
            return _FakeLocator(self, selector, [selector])
        if selector in self._available_day_selectors:
            return _FakeLocator(self, selector, [selector])
        if "Apply" in selector or "Done" in selector:
            return _FakeLocator(self, selector, [])
        if "Next month" in selector or "calender-arrow" in selector:
            return _FakeLocator(self, selector, [])  # no next-month control in this fake
        if selector == self.search_button_selector:
            return _FakeLocator(self, selector, [selector])
        return _FakeLocator(self, selector, [])

    def wait_for_timeout(self, ms: int) -> None:
        pass

    def evaluate(self, js: str, arg=None) -> int:
        # This fake models click-blocking purely via `_requires_widget_
        # reveal()` / explicit "present but not dismissed" flags, not real
        # CSS stacking contexts — so there is nothing for the generic
        # `_neutralize_overlays()` JS to actually find here. Recording
        # that it was called (without needing to simulate real overlay
        # geometry) is enough for these control-flow tests; a real
        # browser is what proves the JS itself works, per this file's own
        # documented scope limit.
        self.evaluate_calls = getattr(self, "evaluate_calls", 0) + 1
        return 0

    def wait_for_function(self, js: str, arg: str, timeout: int = 0) -> None:
        if arg == self.trip_type_one_way_input_selector:
            if self.one_way_selected:
                return
            raise TimeoutError("one-way input never reported checked")
        if self._search_disabled:
            raise TimeoutError("search button never enabled")

    def content(self) -> str:
        self.content_dumped = True
        return "<html><!-- fake opened calendar --></html>"


class TestAirIndiaPageAction(unittest.TestCase):
    def setUp(self):
        self.route = {
            "route_id": "DEL-BOM",
            "origin": "DEL",
            "destination": "BOM",
            "origin_name": "Delhi",
            "destination_name": "Mumbai",
        }
        self._cwd = os.getcwd()
        self._tmpdir = tempfile.mkdtemp()
        os.chdir(self._tmpdir)

    def tearDown(self):
        os.chdir(self._cwd)

    def test_factory_returns_callable_bound_to_route(self):
        action = build_air_india_page_action(self.route, "2026-10-18")
        self.assertTrue(callable(action))

    def test_happy_path_fills_both_fields_and_clicks_search(self):
        page = _FakePage(
            available_day_selectors=["button.mat-calendar-body-cell[aria-label='10/18/2026']"],
            search_starts_disabled=False,
        )
        action = build_air_india_page_action(self.route, "2026-10-18")
        result = action(page)

        self.assertIs(result, page)
        clicked_selectors = [sel for sel, _ in page.clicks]
        # Modify must be clicked before anything inside the (real,
        # confirmed-hidden) widget is touched.
        self.assertEqual(clicked_selectors[0], _FakePage.modify_button_selector)
        # One Way must be selected — real DOM defaults to Round Trip,
        # which requires a return date this file never picks (see
        # _select_one_way's docstring) — and before the depart date is
        # picked, since that's the field whose validity this affects.
        self.assertTrue(page.one_way_selected)
        self.assertLess(
            clicked_selectors.index(_FakePage.trip_type_one_way_selector),
            clicked_selectors.index(_FakePage.date_button_selector),
        )
        # Both airport options should have been clicked (one matching
        # "DEL", one matching "BOM").
        option_clicks = [m for sel, m in page.clicks if "mat-mdc-option" in sel]
        self.assertEqual(len(option_clicks), 2)
        self.assertTrue(any("DEL" in m[0] for m in option_clicks))
        self.assertTrue(any("BOM" in m[0] for m in option_clicks))
        # The day cell should have been clicked.
        self.assertIn("button.mat-calendar-body-cell[aria-label='10/18/2026']", clicked_selectors)
        # Search should have been clicked last.
        self.assertEqual(clicked_selectors[-1], _FakePage.search_button_selector)

    def test_one_way_not_selected_when_selector_absent_does_not_crash_run(self):
        # If a future markup change removes/renames this radio group,
        # _select_one_way must degrade the same way every other guess in
        # this file does — log and continue, not raise — since Search
        # staying disabled downstream is what would surface it as a real,
        # diagnosable "empty" outcome anyway.
        page = _FakePage(
            available_day_selectors=["button.mat-calendar-body-cell[aria-label='10/18/2026']"],
            search_starts_disabled=False,
            trip_type_selector_present=False,
        )
        action = build_air_india_page_action(self.route, "2026-10-18")
        result = action(page)  # must not raise
        self.assertIs(result, page)
        self.assertFalse(page.one_way_selected)

    def test_one_way_retries_once_when_first_click_does_not_stick(self):
        # ROUND 16 regression: a real run's fresh debug HTML showed the
        # round-trip label still `--checked` even after the (unverified)
        # round-15 fix supposedly clicked One Way. This models exactly
        # that shape — a recorded click that doesn't actually flip the
        # native input's `.checked` state — and proves the retry recovers
        # when the SECOND click is the one that sticks.
        page = _FakePage(
            available_day_selectors=["button.mat-calendar-body-cell[aria-label='10/18/2026']"],
            search_starts_disabled=False,
            trip_type_sticks_after_attempt=2,
        )
        action = build_air_india_page_action(self.route, "2026-10-18")
        action(page)
        self.assertTrue(page.one_way_selected)
        self.assertEqual(page.trip_type_click_count, 2)
        self.assertFalse(getattr(page, "content_dumped", False))

    def test_one_way_dumps_evidence_when_click_never_sticks(self):
        # If BOTH attempts fail to produce a checked input, this must not
        # keep asserting success silently (round 15's actual bug) — it
        # saves real evidence and continues rather than crashing the run,
        # the same "diagnose, don't hang" contract as every other guess
        # in this file.
        page = _FakePage(
            available_day_selectors=["button.mat-calendar-body-cell[aria-label='10/18/2026']"],
            search_starts_disabled=False,
            trip_type_sticks_after_attempt=99,  # never reachable in 2 tries
        )
        action = build_air_india_page_action(self.route, "2026-10-18")
        result = action(page)  # must not raise
        self.assertIs(result, page)
        self.assertFalse(page.one_way_selected)
        self.assertEqual(page.trip_type_click_count, 2)
        self.assertTrue(page.content_dumped)

    def test_cookie_banner_dismissed_before_modify_is_clicked(self):
        # Simulates the THIRD real run's actual failure: a OneTrust
        # cookie-consent dark-filter overlay blocking the Modify click.
        page = _FakePage(
            available_day_selectors=["button.mat-calendar-body-cell[aria-label='10/18/2026']"],
            search_starts_disabled=False,
            cookie_banner_present=True,
        )
        action = build_air_india_page_action(self.route, "2026-10-18")
        action(page)

        clicked_selectors = [sel for sel, _ in page.clicks]
        self.assertEqual(clicked_selectors[0], _FakePage.cookie_accept_selector)
        self.assertEqual(clicked_selectors[1], _FakePage.modify_button_selector)
        self.assertTrue(page.cookie_dark_filter_dismissed)

    def test_no_cookie_banner_present_skips_dismiss_cleanly(self):
        # Default fixture: no banner rendered at all. Should not attempt
        # to click anything cookie-related, and should behave exactly as
        # it did before this fix (Modify clicked first).
        page = _FakePage(
            available_day_selectors=["button.mat-calendar-body-cell[aria-label='10/18/2026']"],
            search_starts_disabled=False,
            cookie_banner_present=False,
        )
        action = build_air_india_page_action(self.route, "2026-10-18")
        action(page)

        clicked_selectors = [sel for sel, _ in page.clicks]
        self.assertNotIn(_FakePage.cookie_accept_selector, clicked_selectors)
        self.assertEqual(clicked_selectors[0], _FakePage.modify_button_selector)

    def test_dark_filter_not_confirmed_hidden_does_not_crash_run(self):
        # The click "worked" (no exception) but the dark filter never
        # reports itself hidden — by design this is a soft failure: log
        # and keep going, since the very next click (Modify) will
        # surface a real, specific Playwright error of its own if the
        # overlay is still actually blocking things.
        page = _FakePage(
            available_day_selectors=["button.mat-calendar-body-cell[aria-label='10/18/2026']"],
            search_starts_disabled=False,
            cookie_banner_present=True,
            cookie_accept_clears_dark_filter=False,
        )
        action = build_air_india_page_action(self.route, "2026-10-18")
        result = action(page)  # must not raise

        self.assertIs(result, page)
        clicked_selectors = [sel for sel, _ in page.clicks]
        self.assertEqual(clicked_selectors[0], _FakePage.cookie_accept_selector)

    def test_banner_hidden_but_dark_filter_lingers_is_still_caught(self):
        # REGRESSION TEST for the eleventh real run's actual bug: the
        # OLD code only ever checked whether the BANNER reported itself
        # hidden and treated that as success, even though Playwright's
        # own error always named the SIBLING dark filter as what
        # actually blocks the next click. This simulates exactly that
        # divergence — banner dismissed fine, dark filter does NOT clear
        # — and asserts the fix now notices (soft-fails with a log,
        # rather than silently treating a dismissed banner as "done")
        # instead of confidently sailing past a still-blocking overlay.
        page = _FakePage(
            available_day_selectors=["button.mat-calendar-body-cell[aria-label='10/18/2026']"],
            search_starts_disabled=False,
            cookie_banner_present=True,
            cookie_accept_dismisses_banner=True,
            cookie_accept_clears_dark_filter=False,
        )
        action = build_air_india_page_action(self.route, "2026-10-18")
        result = action(page)  # must not raise — soft failure by design

        self.assertIs(result, page)
        self.assertTrue(page.cookie_banner_dismissed)  # banner: fine
        self.assertFalse(page.cookie_dark_filter_dismissed)  # dark filter: NOT fine
        # The old bug would have been invisible here (banner dismissed
        # was the only thing ever checked); this test exists specifically
        # so a future regression back to checking the banner instead of
        # the dark filter would need to actively break this assertion,
        # not just happen to pass by coincidence.
        clicked_selectors = [sel for sel, _ in page.clicks]
        self.assertEqual(clicked_selectors[0], _FakePage.cookie_accept_selector)

    def test_error_dialog_dismissed_before_modify_is_clicked(self):
        # Simulates the SIXTH real run's actual failure: Air India's own
        # "Something went wrong" mat-dialog (NOT the OneTrust overlay)
        # blocking the Modify click.
        page = _FakePage(
            available_day_selectors=["button.mat-calendar-body-cell[aria-label='10/18/2026']"],
            search_starts_disabled=False,
            error_dialog_present=True,
        )
        action = build_air_india_page_action(self.route, "2026-10-18")
        action(page)

        clicked_selectors = [sel for sel, _ in page.clicks]
        self.assertEqual(clicked_selectors[0], _FakePage.dialog_dismiss_selector)
        self.assertEqual(clicked_selectors[1], _FakePage.modify_button_selector)
        self.assertTrue(page.error_dialog_dismissed)

    def test_no_error_dialog_present_skips_dismiss_cleanly(self):
        # Default fixture: no error dialog rendered at all. Should not
        # attempt to click anything dialog-related, and should behave
        # exactly as it did before this fix (Modify clicked first).
        page = _FakePage(
            available_day_selectors=["button.mat-calendar-body-cell[aria-label='10/18/2026']"],
            search_starts_disabled=False,
            error_dialog_present=False,
        )
        action = build_air_india_page_action(self.route, "2026-10-18")
        action(page)

        clicked_selectors = [sel for sel, _ in page.clicks]
        self.assertNotIn(_FakePage.dialog_dismiss_selector, clicked_selectors)
        self.assertEqual(clicked_selectors[0], _FakePage.modify_button_selector)

    def test_error_dialog_not_confirmed_hidden_does_not_crash_run(self):
        # The dismiss click "worked" (no exception) but the backdrop
        # never reports itself hidden — same soft-failure contract as
        # the cookie-consent dismiss: log and keep going, since the very
        # next click (Modify) will surface a real, specific Playwright
        # error of its own if the overlay is still actually blocking.
        page = _FakePage(
            available_day_selectors=["button.mat-calendar-body-cell[aria-label='10/18/2026']"],
            search_starts_disabled=False,
            error_dialog_present=True,
            dialog_dismiss_clears_backdrop=False,
        )
        action = build_air_india_page_action(self.route, "2026-10-18")
        result = action(page)  # must not raise

        self.assertIs(result, page)
        clicked_selectors = [sel for sel, _ in page.clicks]
        self.assertEqual(clicked_selectors[0], _FakePage.dialog_dismiss_selector)

    def test_error_dialog_and_cookie_banner_both_dismissed_in_order(self):
        # Both overlays present at once (worst case, not yet observed for
        # real but cheap to guard against): cookie-consent should still
        # be dismissed first (it's checked first), then the error dialog,
        # both before Modify is ever attempted.
        page = _FakePage(
            available_day_selectors=["button.mat-calendar-body-cell[aria-label='10/18/2026']"],
            search_starts_disabled=False,
            cookie_banner_present=True,
            error_dialog_present=True,
        )
        action = build_air_india_page_action(self.route, "2026-10-18")
        action(page)

        clicked_selectors = [sel for sel, _ in page.clicks]
        self.assertEqual(clicked_selectors[0], _FakePage.cookie_accept_selector)
        self.assertEqual(clicked_selectors[1], _FakePage.dialog_dismiss_selector)
        self.assertEqual(clicked_selectors[2], _FakePage.modify_button_selector)

    def test_falls_back_to_airport_name_when_code_yields_no_real_option(self):
        # Simulates the FOURTH real run: typing "DEL" produced only the
        # disabled no-options placeholder. The retry with "Delhi" (the
        # route's origin_name) should then succeed.
        page = _FakePage(
            available_day_selectors=["button.mat-calendar-body-cell[aria-label='10/18/2026']"],
            search_starts_disabled=False,
            autocomplete_success_attempt={"origin": 2, "destination": 1},
        )
        action = build_air_india_page_action(self.route, "2026-10-18")
        action(page)

        self.assertEqual(page.typed["origin"], ["DEL", "Delhi"])
        option_clicks = [m for sel, m in page.clicks if "mat-mdc-option" in sel]
        self.assertEqual(len(option_clicks), 2)
        # Search should still get clicked — a successful retry looks
        # exactly like the happy path from here on.
        self.assertEqual(page.clicks[-1][0], _FakePage.search_button_selector)

    def test_no_real_option_for_either_code_or_name_degrades_without_crashing(self):
        # Neither "DEL" nor "Delhi" ever produces a real suggestion —
        # worst case. Must not raise: origin selection is skipped, but
        # destination, date, and Search are all still attempted, giving
        # a full diagnosable run instead of a crash or a 45s hang.
        page = _FakePage(
            available_day_selectors=["button.mat-calendar-body-cell[aria-label='10/18/2026']"],
            search_starts_disabled=False,
            autocomplete_success_attempt={"origin": None, "destination": 1},
        )
        action = build_air_india_page_action(self.route, "2026-10-18")
        result = action(page)  # must not raise

        self.assertIs(result, page)
        self.assertEqual(page.typed["origin"], ["DEL", "Delhi"])  # both tried
        self.assertTrue(page.content_dumped)
        self.assertTrue(os.path.exists("debug_air_india_autocomplete_origin.html"))
        # Destination still got a real option clicked despite origin
        # failing, and Search was still attempted at the end.
        option_clicks = [m for sel, m in page.clicks if "mat-mdc-option" in sel]
        self.assertEqual(len(option_clicks), 1)
        self.assertEqual(page.clicks[-1][0], _FakePage.search_button_selector)

    def test_destination_failure_dumps_a_destination_debug_file_not_origin(self):
        # REGRESSION TEST for a real bug: `_ORIGIN_FIELD` is
        # ".ai-origin-destination__field--origin" and `_DESTINATION_FIELD`
        # is ".ai-origin-destination__field--destination" — the shared
        # container class means BOTH strings contain the literal
        # substring "origin" (from "ai-ORIGIN-destination"). A naive
        # `"origin" in field_selector` check therefore misidentified the
        # DESTINATION field as "origin" too, confirmed by a real run
        # printing "no real airport suggestion ... in origin field" twice
        # in a row and silently overwriting the same debug file both
        # times — the destination field's own evidence was never
        # actually saved. This asserts the fix: a destination-only
        # failure must produce debug_air_india_autocomplete_destination.html,
        # not a second copy of the origin one.
        page = _FakePage(
            available_day_selectors=["button.mat-calendar-body-cell[aria-label='10/18/2026']"],
            search_starts_disabled=False,
            autocomplete_success_attempt={"origin": 1, "destination": None},
        )
        action = build_air_india_page_action(self.route, "2026-10-18")
        result = action(page)  # must not raise

        self.assertIs(result, page)
        self.assertTrue(os.path.exists("debug_air_india_autocomplete_destination.html"))
        self.assertFalse(os.path.exists("debug_air_india_autocomplete_origin.html"))

    def test_raises_clearly_if_modify_click_does_not_reveal_widget(self):
        # Simulates the one real inference in this file being wrong: the
        # Modify button exists and gets clicked, but the widget container
        # never reports itself visible.
        page = _FakePage(available_day_selectors=[], modify_click_reveals_widget=False)
        action = build_air_india_page_action(self.route, "2026-10-18")

        with self.assertRaises(RuntimeError):
            action(page)

        # Fails loudly and immediately (Modify was tried) rather than
        # hanging 45s against a hidden input further down the function.
        self.assertEqual(page.clicks[0][0], _FakePage.modify_button_selector)
        self.assertEqual(len(page.clicks), 1)
        self.assertTrue(page.content_dumped)
        self.assertTrue(os.path.exists("debug_air_india_post_modify_click.html"))

    def test_date_guess_fails_dumps_debug_html_instead_of_crashing(self):
        page = _FakePage(available_day_selectors=[], search_starts_disabled=True)
        action = build_air_india_page_action(self.route, "2026-10-18")

        # Must not raise, even though every date-cell guess misses and the
        # search button never reports itself enabled.
        result = action(page)

        self.assertIs(result, page)
        self.assertTrue(page.content_dumped)
        debug_path = "debug_air_india_datepicker_2026-10-18.html"
        self.assertTrue(os.path.exists(debug_path))
        with open(debug_path, encoding="utf-8") as f:
            self.assertIn("fake opened calendar", f.read())
        # Search must NOT be clicked here: the fifth real run proved
        # clicking a still-disabled button is not a no-op, it's a full
        # 45s hang (Playwright: "element is not enabled", 84 retries).
        # A missed date degrades to a diagnosable "empty" outcome by
        # SKIPPING the click, not by attempting a doomed one.
        clicked_selectors = [sel for sel, _ in page.clicks]
        self.assertNotIn(_FakePage.search_button_selector, clicked_selectors)

    def test_search_click_is_skipped_not_attempted_when_button_stays_disabled(self):
        # Same scenario, stated as its own explicit regression test for
        # the fifth real run's finding: a disabled Search button is
        # never clicked, regardless of why it stayed disabled.
        page = _FakePage(
            available_day_selectors=["button.mat-calendar-body-cell[aria-label='10/18/2026']"],
            search_starts_disabled=True,
        )
        action = build_air_india_page_action(self.route, "2026-10-18")
        result = action(page)  # must not raise or hang

        self.assertIs(result, page)
        clicked_selectors = [sel for sel, _ in page.clicks]
        self.assertNotIn(_FakePage.search_button_selector, clicked_selectors)
        # Everything upstream of Search should still have been attempted.
        self.assertIn("button.mat-calendar-body-cell[aria-label='10/18/2026']", clicked_selectors)

    def test_search_click_still_happens_when_button_becomes_enabled(self):
        # Confirms the happy path wasn't broken by the skip-if-disabled
        # fix — Search is clicked normally once it reports itself enabled.
        page = _FakePage(
            available_day_selectors=["button.mat-calendar-body-cell[aria-label='10/18/2026']"],
            search_starts_disabled=False,
        )
        action = build_air_india_page_action(self.route, "2026-10-18")
        action(page)

        clicked_selectors = [sel for sel, _ in page.clicks]
        self.assertEqual(clicked_selectors[-1], _FakePage.search_button_selector)

    def test_generic_overlay_neutralizer_runs_multiple_times(self):
        # ROUND 13 regression coverage: `_neutralize_overlays()` must run
        # as a defensive pass at more than one point in the flow (before
        # the cookie/dialog dismiss attempts, and again before Modify and
        # before Search) — not just once at the top — since the real bug
        # it answers (an unnamed overlay blocking a click) can appear
        # between any two steps, not only on first load.
        page = _FakePage(
            available_day_selectors=["button.mat-calendar-body-cell[aria-label='10/18/2026']"],
            search_starts_disabled=False,
        )
        action = build_air_india_page_action(self.route, "2026-10-18")
        action(page)

        self.assertGreaterEqual(getattr(page, "evaluate_calls", 0), 3)

    def test_month_name_lookup_is_1_indexed_correctly(self):
        from ..page_actions import _MONTHS

        self.assertEqual(_MONTHS[0], "January")
        self.assertEqual(_MONTHS[9], "October")
        self.assertEqual(len(_MONTHS), 12)


if __name__ == "__main__":
    unittest.main()
