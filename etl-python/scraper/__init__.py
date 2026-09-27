"""Scrapling-based airfare scraper for SIH26056.

Public entrypoints:
  - models.FareRecord            — the shared output schema
  - xhr_parser.extract_fares_from_xhr  — pure-Python, unit-tested
  - html_parser.extract_fares_from_html — needs scrapling installed
  - fare_scraper.run_scrape       — needs scrapling + a real browser
  - run_scraper.main              — CLI wrapper around run_scrape
"""
