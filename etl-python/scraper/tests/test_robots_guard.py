import unittest

from scraper.robots_guard import RobotsGuard, RobotsRules
from scraper.ota_candidates import OTA_CANDIDATES, is_runnable

SAMPLE = """
# modelled on a real OTA robots.txt
User-agent: *
Disallow: /search/result/
Disallow: /flights/search
Disallow: /*.pdf$
Disallow: /api/
Allow: /api/public/
Disallow: *-lp-*

User-agent: Yandex
Disallow: /

User-agent: MSNBot
Crawl-delay: 10
"""


class TestRules(unittest.TestCase):
    def setUp(self):
        self.r = RobotsRules.parse(SAMPLE)

    def test_prefix_disallow(self):
        self.assertFalse(self.r.check("/flights/search?from=DEL&to=BOM")[0])

    def test_unlisted_path_allowed(self):
        self.assertTrue(self.r.check("/about-us")[0])

    def test_wildcard_and_end_anchor(self):
        self.assertFalse(self.r.check("/docs/file.pdf")[0])
        self.assertTrue(self.r.check("/docs/file.pdf.html")[0])

    def test_embedded_wildcard(self):
        self.assertFalse(self.r.check("/x-lp-y")[0])

    def test_longest_match_allow_beats_shorter_disallow(self):
        self.assertTrue(self.r.check("/api/public/fares")[0])
        self.assertFalse(self.r.check("/api/private")[0])

    def test_specific_agent_group_wins(self):
        self.assertFalse(self.r.check("/", "Yandex")[0])
        self.assertTrue(self.r.check("/", "VayuAirfareIndexBot")[0])

    def test_crawl_delay(self):
        self.assertEqual(self.r.crawl_delay("MSNBot"), 10.0)
        self.assertIsNone(self.r.crawl_delay("VayuAirfareIndexBot"))

    def test_empty_disallow_blocks_nothing(self):
        r = RobotsRules.parse("User-agent: *\nDisallow:\n")
        self.assertTrue(r.check("/anything")[0])

    def test_tie_prefers_allow(self):
        r = RobotsRules.parse("User-agent: *\nDisallow: /a\nAllow: /a\n")
        self.assertTrue(r.check("/a")[0])


class TestGuard(unittest.TestCase):
    def _guard(self, status, body="", **kw):
        calls = []

        def fetcher(url):
            calls.append(url)
            return status, body

        g = RobotsGuard(fetcher=fetcher, **kw)
        g.calls = calls
        return g

    def test_disallowed_url_blocked_with_reason(self):
        d = self._guard(200, SAMPLE).check("https://ota.example/flights/search?a=1")
        self.assertFalse(d.allowed)
        self.assertEqual(d.matched_rule, "Disallow: /flights/search")

    def test_allowed_url(self):
        self.assertTrue(self._guard(200, SAMPLE).check("https://ota.example/").allowed)

    def test_missing_robots_allows(self):
        self.assertTrue(self._guard(404).check("https://ota.example/flights/search").allowed)

    def test_unreachable_fails_closed(self):
        self.assertFalse(self._guard(503).check("https://ota.example/").allowed)
        self.assertFalse(self._guard(0).check("https://ota.example/").allowed)

    def test_rate_limited_robots_fails_closed(self):
        self.assertFalse(self._guard(429).check("https://ota.example/").allowed)

    def test_fail_open_option(self):
        self.assertTrue(self._guard(503, fail_closed=False).check("https://ota.example/").allowed)

    def test_robots_fetched_once_per_host(self):
        g = self._guard(200, SAMPLE)
        g.check("https://ota.example/a")
        g.check("https://ota.example/b")
        self.assertEqual(g.calls, ["https://ota.example/robots.txt"])


class TestCandidates(unittest.TestCase):
    def test_nothing_runnable_without_verification(self):
        for name in OTA_CANDIDATES:
            self.assertFalse(is_runnable(name), name)

    def test_ixigo_recorded_as_blocked(self):
        self.assertEqual(OTA_CANDIDATES["ixigo"]["status"], "blocked_by_robots")


if __name__ == "__main__":
    unittest.main()
