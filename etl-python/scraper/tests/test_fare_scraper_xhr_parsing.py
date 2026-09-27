"""
Run with: python3 -m unittest scraper.tests.test_fare_scraper_xhr_parsing -v

Real-run history behind this file (google_flights, 2026-09-27):

1. GetShoppingResults was captured three times; every one crashed with
   `JSONDecodeError: unexpected character, expected a JSON value: line 1
   column 1 (char 0)` — BEFORE the debug-file-writing code even ran, so
   the run reported "fetch_error" with zero diagnostic files. Root cause:
   several internal Google RPC endpoints prepend a one-line `)]}'`-style
   anti-JSON-hijacking guard before the real payload; a plain
   `response.json()` has no awareness of it and fails on the very first
   byte. Fixed with `_strip_xssi_prefix` + a try/except that falls back
   instead of crashing.
2. No crash, but `.text()` came back empty with no exception — Playwright
   most likely already discarded the buffered response body. Fixed by
   trying several plausible raw-body attribute names
   (`_RAW_TEXT_CANDIDATE_ATTRS`) before giving up, and, on total failure,
   dumping real introspection (`dir(entry)`) instead of a blind guess.
3. Raw text WAS retrieved, guard-stripped, and STILL failed — this time
   with the more specific `Extra data: line 3 column 1 (char 7)`, the
   signature of `json.loads` parsing some small valid value and then
   choking on whatever follows it. First theory: an explicit
   `<byte-length>\n` header in front of each JSON chunk.
4. That theory's own implementation, run against this exact same shape
   of error, came back with 0 usable chunks — real evidence the specific
   byte-exact framing was wrong (or at least incompletely understood).
   Rather than guess a THIRD specific framing, `_split_google_length_
   prefixed_chunks` was replaced entirely by
   `_extract_json_values_from_stream`: a general JSON-value scanner
   (`JSONDecoder.raw_decode`) that pulls out every well-formed top-level
   JSON value from the text and treats anything in between it can't
   parse — a guard line, a bare length header, blank lines — as noise to
   skip past. It works whether the real framing is length-prefixed,
   guard-per-chunk, or something not yet seen, because it never assumes
   an exact byte count.

These tests exercise `_parse_captured_xhr`, `_strip_xssi_prefix`, and
`_extract_json_values_from_stream` directly with fakes shaped like the
real thing — not scrapling itself, which needs a real browser and isn't
available in this sandbox (see fare_scraper.py's own module docstring).
"""

from __future__ import annotations

import json
import unittest

from ..fare_scraper import _extract_json_values_from_stream, _parse_captured_xhr, _strip_xssi_prefix


class _FakeXhrEntry:
    """Mimics the shape fare_scraper.py actually calls: a `.json()` that
    behaves like Playwright's Response.json() (plain `json.loads` on the
    raw text, so it raises on a guard-prefixed body), and a `.text()`
    that returns that same raw text."""

    def __init__(self, raw_text: str, url: str = "https://www.google.com/_/FlightsFrontendUi/data/x"):
        self._raw_text = raw_text
        self.url = url

    def json(self):
        return json.loads(self._raw_text)

    def text(self):
        return self._raw_text


class TestStripXssiPrefix(unittest.TestCase):
    def test_strips_real_google_guard(self):
        raw = ")]}'\n" + json.dumps({"a": 1})
        self.assertEqual(json.loads(_strip_xssi_prefix(raw)), {"a": 1})

    def test_strips_guard_with_trailing_comma(self):
        raw = ")]}',\n" + json.dumps({"a": 1})
        self.assertEqual(json.loads(_strip_xssi_prefix(raw)), {"a": 1})

    def test_leaves_plain_json_unchanged(self):
        raw = json.dumps({"a": 1})
        self.assertEqual(_strip_xssi_prefix(raw), raw)

    def test_tolerates_leading_bom_and_whitespace(self):
        raw = "\ufeff  \n)]}'\n" + json.dumps({"a": 1})
        self.assertEqual(json.loads(_strip_xssi_prefix(raw)), {"a": 1})


class TestExtractJsonValuesFromStream(unittest.TestCase):
    def test_plain_concatenated_json_values_with_no_framing_at_all(self):
        # Theory B: independent JSON values simply back to back, no
        # length header and no repeated guard.
        text = json.dumps({"a": 1}) + "\n" + json.dumps({"b": 2})
        self.assertEqual(_extract_json_values_from_stream(text), [{"a": 1}, {"b": 2}])

    def test_length_header_style_framing_still_works_without_trusting_the_count(self):
        # Theory A (length-prefixed): the header number is parsed as its
        # own small JSON value and dropped as noise; the scanner never
        # needs the count to be byte-exact because it doesn't use it —
        # it just looks for the next valid JSON value after it.
        chunk = json.dumps({"flights": [{"fare": 6147}]})
        text = f"41\n{chunk}\n"
        self.assertEqual(_extract_json_values_from_stream(text), [{"flights": [{"fare": 6147}]}])

    def test_repeated_guard_lines_between_chunks_are_skipped(self):
        # Theory C: each chunk gets its own repeated `)]}'` guard.
        text = ")]}'\n" + json.dumps({"a": 1}) + "\n)]}'\n" + json.dumps({"b": 2})
        self.assertEqual(_extract_json_values_from_stream(text), [{"a": 1}, {"b": 2}])

    def test_leading_blank_lines_before_a_length_header_are_tolerated(self):
        # Matches the real run's error shape: "line 3" implies a blank
        # line, then the header, then the actual chunk.
        chunk = json.dumps({"ok": True})
        text = f"\n\n41\n{chunk}\n"
        self.assertEqual(_extract_json_values_from_stream(text), [{"ok": True}])

    def test_non_json_text_yields_nothing(self):
        self.assertEqual(_extract_json_values_from_stream("<html>nope</html>"), [])

    def test_stops_cleanly_after_a_bad_tail_but_keeps_the_good_values(self):
        text = json.dumps({"a": 1}) + "\nnot valid json at all"
        self.assertEqual(_extract_json_values_from_stream(text), [{"a": 1}])


class TestParseCapturedXhr(unittest.TestCase):
    def test_falls_back_to_text_and_strips_guard(self):
        # This is the exact real-world shape from run #1: .json() raises
        # (guard prefix breaks plain json.loads), .text() has the raw body.
        entry = _FakeXhrEntry(")]}'\n" + json.dumps({"data": [1, 2, 3]}))
        payload, raw_text, error = _parse_captured_xhr(entry)
        self.assertEqual(payload, {"data": [1, 2, 3]})
        self.assertIsNone(error)
        self.assertTrue(raw_text.startswith(")]}'"))

    def test_stream_of_values_after_guard_is_the_run_3_and_4_shape(self):
        # google_flights's 3rd/4th real runs: guard-strip alone raised
        # "Extra data..." — a length-header-shaped value followed by the
        # real chunk. End-to-end through _parse_captured_xhr, not just
        # the scanner in isolation.
        chunk = json.dumps({"flights": [{"fare": 6147, "airline": "AI"}]})
        raw = ")]}'\n" + f"41\n{chunk}\n"
        entry = _FakeXhrEntry(raw)
        payload, raw_text, error = _parse_captured_xhr(entry)
        self.assertEqual(payload, [{"flights": [{"fare": 6147, "airline": "AI"}]}])
        self.assertIsNone(error)
        self.assertEqual(raw_text, raw)

    def test_normal_json_still_works_unchanged(self):
        # Every currently-working target (air_india, indigo, the generic
        # heuristic) must keep taking this exact fast path.
        entry = _FakeXhrEntry(json.dumps({"fares": []}))
        payload, _raw_text, error = _parse_captured_xhr(entry)
        self.assertEqual(payload, {"fares": []})
        self.assertIsNone(error)

    def test_genuinely_unparseable_body_reports_error_and_keeps_raw_text(self):
        entry = _FakeXhrEntry("<html>not json at all</html>")
        payload, raw_text, error = _parse_captured_xhr(entry)
        self.assertIsNone(payload)
        self.assertIn("not json at all", raw_text)
        self.assertIn("0 usable values", error)

    def test_plain_dict_entry_unittest_fake_still_works(self):
        # Existing test fakes elsewhere in this project pass the payload
        # dict directly as `entry`, with no .json()/.text() at all.
        entry = {"already": "parsed"}
        payload, _raw_text, error = _parse_captured_xhr(entry)
        self.assertEqual(payload, {"already": "parsed"})
        self.assertIsNone(error)

    def test_text_raising_falls_back_to_other_candidate_attrs(self):
        # The exact real-world shape from run #2: no crash, but .text()
        # gave back nothing either (a live candidate: Playwright discards
        # a response's buffered body once its page has already navigated
        # on). .content() standing in as a working alternate proves the
        # multi-attribute fallback actually helps.
        class _EntryWithFlakyText:
            url = "https://www.google.com/_/FlightsFrontendUi/data/x"

            def json(self):
                raise ValueError("boom")

            def text(self):
                raise RuntimeError("No resource with given identifier found")

            def content(self):
                return (")]}'\n" + json.dumps({"ok": True})).encode("utf-8")

        payload, raw_text, error = _parse_captured_xhr(_EntryWithFlakyText())
        self.assertEqual(payload, {"ok": True})
        self.assertIsNone(error)
        self.assertIn("ok", raw_text)

    def test_total_failure_dumps_real_introspection_not_a_guess(self):
        # Nothing at all works — the debug file should show exactly what
        # was tried and what the object actually looks like, so the next
        # fix is built from evidence rather than another blind guess.
        class _EntryWithNothingUsable:
            url = "https://www.google.com/_/FlightsFrontendUi/data/x"
            some_other_field = "not a text candidate name"

            def json(self):
                raise ValueError("boom")

        payload, raw_text, error = _parse_captured_xhr(_EntryWithNothingUsable())
        self.assertIsNone(payload)
        self.assertIsNone(raw_text)
        self.assertIn("json() raised", error)
        self.assertIn("raw-text extraction attempts", error)
        self.assertIn("dir(entry)", error)
        self.assertIn("some_other_field", error)


if __name__ == "__main__":
    unittest.main()
