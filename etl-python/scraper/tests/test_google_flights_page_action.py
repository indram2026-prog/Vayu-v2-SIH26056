"""
Run with: python3 -m unittest scraper.tests.test_google_flights_page_action -v

Tests the PURE CONTROL FLOW in page_actions_google_flights.py — not a real
browser, and not proof the real google.com/travel/flights DOM matches
anything guessed at here. See that module's own docstring for the full
honesty split: unlike air_india's page_actions.py, nothing here has ever
been checked against a real page at all yet. These tests only prove: the
factory returns a callable, a present consent button gets clicked, and a
missing one is a clean no-op rather than a crash.
"""

from __future__ import annotations

import unittest

from ..page_actions_google_flights import build_google_flights_page_action


class _FakeLocator:
    def __init__(self, page: "_FakePage", selector: str, present: bool):
        self.page = page
        self.selector = selector
        self.present = present

    @property
    def first(self):
        return self

    def count(self) -> int:
        return 1 if self.present else 0

    def wait_for(self, state: str = "visible", timeout: int = 0) -> None:
        if not self.present:
            raise TimeoutError(f"no element for {self.selector!r}")

    def click(self) -> None:
        self.page.clicked_selectors.append(self.selector)


class _FakePage:
    def __init__(self, consent_present: bool = False, consent_selector: str = "button:has-text('Accept all')"):
        self.consent_present = consent_present
        self.consent_selector = consent_selector
        self.clicked_selectors: list[str] = []
        self.waited_ms: list[int] = []

    def locator(self, selector: str) -> _FakeLocator:
        present = self.consent_present and selector == self.consent_selector
        return _FakeLocator(self, selector, present)

    def wait_for_timeout(self, ms: int) -> None:
        self.waited_ms.append(ms)


class TestGoogleFlightsPageAction(unittest.TestCase):
    def setUp(self):
        self.route = {
            "route_id": "DEL-BOM",
            "origin": "DEL",
            "destination": "BOM",
            "origin_name": "Delhi",
            "destination_name": "Mumbai",
        }

    def test_factory_returns_callable_bound_to_route(self):
        action = build_google_flights_page_action(self.route, "2026-10-18")
        self.assertTrue(callable(action))

    def test_no_consent_screen_is_a_clean_no_op(self):
        page = _FakePage(consent_present=False)
        action = build_google_flights_page_action(self.route, "2026-10-18")
        result = action(page)  # must not raise
        self.assertIs(result, page)
        self.assertEqual(page.clicked_selectors, [])
        self.assertIn(4000, page.waited_ms)

    def test_consent_accept_button_is_clicked_when_present(self):
        page = _FakePage(consent_present=True)
        action = build_google_flights_page_action(self.route, "2026-10-18")
        action(page)
        self.assertEqual(page.clicked_selectors, ["button:has-text('Accept all')"])

    def test_alternate_consent_wording_is_also_tried(self):
        page = _FakePage(consent_present=True, consent_selector="button:has-text('I agree')")
        action = build_google_flights_page_action(self.route, "2026-10-18")
        action(page)  # must not raise trying earlier selectors first
        self.assertEqual(page.clicked_selectors, ["button:has-text('I agree')"])


if __name__ == "__main__":
    unittest.main()
