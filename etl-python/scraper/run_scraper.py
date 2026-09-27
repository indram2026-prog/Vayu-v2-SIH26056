"""
CLI entrypoint.

    python -m scraper.run_scraper --target makemytrip --top 20
    python -m scraper.run_scraper --target indigo --routes DEL-BOM,BLR-HYD

Run from inside `etl-python/`, with `shared/routes.json` present as a
sibling of `etl-python/` (same layout CHANGES.md documents for
route_weights.py — one shared source of truth for the route basket).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_ROUTES_JSON = os.path.join(os.path.dirname(__file__), "..", "..", "shared", "routes.json")


def load_routes() -> list[dict]:
    with open(_ROUTES_JSON, encoding="utf-8") as f:
        data = json.load(f)
    return data["routes"]


def select_routes(all_routes: list[dict], *, top: int | None, explicit: list[str] | None) -> list[dict]:
    if explicit:
        wanted = set(explicit)
        selected = [r for r in all_routes if r["route_id"] in wanted]
        missing = wanted - {r["route_id"] for r in selected}
        if missing:
            print(f"warning: route_id(s) not found in shared/routes.json: {sorted(missing)}", file=sys.stderr)
        return selected

    ranked = sorted(all_routes, key=lambda r: r["weight"], reverse=True)
    return ranked[: top or 20]


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape domestic airfares with Scrapling")
    parser.add_argument(
        "--target",
        choices=["indigo", "air_india", "spicejet", "akasa", "makemytrip", "google_flights"],
        required=True,
    )
    parser.add_argument("--top", type=int, default=20, help="Scrape the top N routes by basket weight")
    parser.add_argument("--routes", type=str, default=None, help="Comma-separated explicit route_ids, overrides --top")
    parser.add_argument("--days-ahead", type=int, default=21)
    parser.add_argument("--delay", type=float, default=4.0, help="Seconds between requests")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--out", type=str, default="fares_out.jsonl")
    parser.add_argument("--report", type=str, default="scrape_report.json")
    args = parser.parse_args()

    try:
        all_routes = load_routes()
    except FileNotFoundError:
        print(
            f"Could not find shared/routes.json at {_ROUTES_JSON!r}. "
            "Run this from etl-python/ with shared/ as a sibling folder — "
            "see CHANGES.md for the exact layout.",
            file=sys.stderr,
        )
        sys.exit(1)

    explicit = args.routes.split(",") if args.routes else None
    routes = select_routes(all_routes, top=args.top, explicit=explicit)
    if not routes:
        print("No routes selected — check --routes / --top.", file=sys.stderr)
        sys.exit(1)

    print(f"Scraping {len(routes)} route(s) against '{args.target}' (this hits the real internet)...")

    # Imported here, not at module top, so `--help` and route-selection
    # logic work even without scrapling installed.
    from .fare_scraper import run_scrape, write_output

    records, report = run_scrape(
        args.target,
        routes,
        days_ahead=args.days_ahead,
        delay_seconds=args.delay,
        max_retries=args.retries,
    )
    write_output(records, report, args.out, args.report)

    for o in report.outcomes:
        print(
            f"  {o.route_id}: {o.status} | http={o.http_status} "
            f"| xhr_captured={o.xhr_captured_count} | html_cards={o.html_cards_found} "
            f"| fares_found={o.record_count}"
            + (f" | debug_html={o.debug_html_path}" if o.debug_html_path else "")
            + (f" | error={o.error}" if o.error else "")
        )
    print(
        f"Done. {report.routes_ok} ok, {report.routes_empty} empty, "
        f"{report.routes_errored} errored, out of {report.routes_attempted} routes attempted."
    )
    print(f"Fares written to {args.out}, report written to {args.report}")


if __name__ == "__main__":
    main()
