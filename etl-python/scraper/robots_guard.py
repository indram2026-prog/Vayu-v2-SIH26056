"""
robots.txt compliance guard for the Vayu scraper (pure stdlib, no scrapling).

Why this exists: the SIH26056 problem statement requires scraping to remain
compliant with each source's robots.txt and terms of service. This module
makes that checkable in code instead of just stated in documents.

It implements the matching rules of RFC 9309:
  - the most specific user-agent group wins, falling back to `*`
  - `*` matches any run of characters, a trailing `$` anchors the end
  - among matching rules the LONGEST path wins; Allow wins a tie
  - robots.txt missing (4xx) -> everything allowed
  - robots.txt unreachable (5xx / network error) -> treated as disallowed
    (fail closed), because we cannot show we are allowed

This module is ADDITIVE: nothing in the existing pipeline imports it yet.
Wiring it into fare_scraper.py is a separate, deliberate step.

Check a site from the command line (needs real internet):

    python -m scraper.robots_guard https://www.example.com/ /flights/search /about

It prints the allow/disallow decision per path and saves the fetched
robots.txt next to where you ran it, as evidence for the docs.
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

DEFAULT_USER_AGENT = "VayuAirfareIndexBot"
Fetcher = Callable[[str], "tuple[int, str]"]  # url -> (http_status, body_text)


@dataclass(frozen=True)
class RobotsDecision:
    allowed: bool
    reason: str
    matched_rule: Optional[str] = None
    robots_url: str = ""


def _pattern(path: str) -> "re.Pattern[str]":
    anchored = path.endswith("$")
    if anchored:
        path = path[:-1]
    body = ".*".join(re.escape(part) for part in path.split("*"))
    return re.compile("^" + body + ("$" if anchored else ""))


@dataclass
class _Rule:
    allow: bool
    path: str

    def matches(self, target: str) -> bool:
        return bool(_pattern(self.path).match(target))


class RobotsRules:
    """Parsed robots.txt. Build with RobotsRules.parse(text)."""

    def __init__(self, groups: "list[tuple[list[str], list[_Rule], Optional[float]]]"):
        self._groups = groups

    @classmethod
    def parse(cls, text: str) -> "RobotsRules":
        groups: "list[tuple[list[str], list[_Rule], Optional[float]]]" = []
        agents: list[str] = []
        rules: list[_Rule] = []
        delay: Optional[float] = None
        in_rules = False

        def flush() -> None:
            nonlocal agents, rules, delay, in_rules
            if agents:
                groups.append((agents, rules, delay))
            agents, rules, delay, in_rules = [], [], None, False

        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            key, value = key.strip().lower(), value.strip()
            if key == "user-agent":
                if in_rules:
                    flush()
                agents.append(value.lower())
            elif key in ("allow", "disallow"):
                in_rules = True
                if value:  # an empty Disallow means "nothing blocked"
                    rules.append(_Rule(allow=(key == "allow"), path=value))
            elif key == "crawl-delay":
                in_rules = True
                try:
                    delay = float(value)
                except ValueError:
                    pass
        flush()
        return cls(groups)

    def _group_for(self, user_agent: str):
        ua = user_agent.lower()
        best, best_len = None, -1
        star = None
        for agents, rules, delay in self._groups:
            for token in agents:
                if token == "*":
                    star = star or (rules, delay)
                elif token and token in ua and len(token) > best_len:
                    best, best_len = (rules, delay), len(token)
        return best or star

    def check(self, path_and_query: str, user_agent: str = DEFAULT_USER_AGENT):
        """Return (allowed, matched_rule_text or None)."""
        group = self._group_for(user_agent)
        if group is None:
            return True, None
        rules, _ = group
        winner: Optional[_Rule] = None
        for rule in rules:
            if rule.matches(path_and_query):
                if (
                    winner is None
                    or len(rule.path) > len(winner.path)
                    or (len(rule.path) == len(winner.path) and rule.allow and not winner.allow)
                ):
                    winner = rule
        if winner is None:
            return True, None
        return winner.allow, ("Allow: " if winner.allow else "Disallow: ") + winner.path

    def crawl_delay(self, user_agent: str = DEFAULT_USER_AGENT) -> Optional[float]:
        group = self._group_for(user_agent)
        return group[1] if group else None


def _default_fetcher(url: str) -> "tuple[int, str]":
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except Exception:  # noqa: BLE001 - network failure is a normal outcome here
        return 0, ""


class RobotsGuard:
    """Per-host cached robots.txt checker. `fetcher` is injectable for tests."""

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        fetcher: Optional[Fetcher] = None,
        fail_closed: bool = True,
    ) -> None:
        self.user_agent = user_agent
        self._fetch = fetcher or _default_fetcher
        self.fail_closed = fail_closed
        self._cache: "dict[str, tuple[Optional[RobotsRules], str]]" = {}

    def _rules_for(self, origin: str) -> "tuple[Optional[RobotsRules], str]":
        if origin in self._cache:
            return self._cache[origin]
        status, body = self._fetch(origin + "/robots.txt")
        if status == 200:
            entry = (RobotsRules.parse(body), "robots.txt fetched")
        elif 400 <= status < 500 and status != 429:
            entry = (RobotsRules([]), f"no robots.txt (HTTP {status}); all allowed")
        else:
            entry = (None, f"robots.txt unreachable (HTTP {status}); cannot confirm access")
        self._cache[origin] = entry
        return entry

    def check(self, url: str) -> RobotsDecision:
        parts = urllib.parse.urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        robots_url = origin + "/robots.txt"
        rules, note = self._rules_for(origin)
        if rules is None:
            return RobotsDecision(not self.fail_closed, note, None, robots_url)
        target = (parts.path or "/") + (("?" + parts.query) if parts.query else "")
        allowed, rule = rules.check(target, self.user_agent)
        return RobotsDecision(allowed, note, rule, robots_url)

    def crawl_delay(self, url: str) -> Optional[float]:
        parts = urllib.parse.urlsplit(url)
        rules, _ = self._rules_for(f"{parts.scheme}://{parts.netloc}")
        return rules.crawl_delay(self.user_agent) if rules else None


def main(argv: "Optional[list[str]]" = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 2:
        print("usage: python -m scraper.robots_guard <site-origin-url> <path-or-url> [...]")
        return 2
    origin = args[0].rstrip("/")
    guard = RobotsGuard()
    status, body = _default_fetcher(origin + "/robots.txt")
    host = urllib.parse.urlsplit(origin).netloc.replace(":", "_")
    if body:
        with open(f"robots_{host}.txt", "w", encoding="utf-8") as fh:
            fh.write(body)
        print(f"saved robots_{host}.txt (HTTP {status})")
    else:
        print(f"could not read robots.txt (HTTP {status})")
    for item in args[1:]:
        url = item if item.startswith("http") else origin + (item if item.startswith("/") else "/" + item)
        d = guard.check(url)
        verdict = "ALLOWED " if d.allowed else "DISALLOWED"
        print(f"{verdict} {url}  [{d.matched_rule or d.reason}]")
    delay = guard.crawl_delay(origin + "/")
    if delay:
        print(f"Crawl-delay for our user-agent: {delay}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
