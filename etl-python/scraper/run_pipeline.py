"""
CLI entrypoint for the FULL pipeline: scrape -> normalize -> anomaly_filter
-> index_engine -> (optionally) push to Supabase.

    # Full daily run (all 325 routes) — what the scheduled GitHub Action runs:
    python -m scraper.run_pipeline --target google_flights --top 325 --mode full --push-supabase

    # Quick on-demand refresh (top 20 routes by weight) — what the
    # dashboard's "Run live scrape" button triggers via workflow_dispatch:
    python -m scraper.run_pipeline --target google_flights --top 20 --mode quick --push-supabase

    # Re-run the pipeline stages against an already-scraped file, no
    # internet needed — useful for testing normalize/anomaly_filter/
    # index_engine changes against real captured data:
    python -m scraper.run_pipeline --from-file fares_out.jsonl --dry-run

Run from inside `etl-python/`, same layout requirement as run_scraper.py
(shared/routes.json as a sibling of etl-python/).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date

from .anomaly_filter import filter_anomalies
from .index_engine import RouteBasketEntry, compute_index
from .models import FareRecord
from .normalize import normalize_records
from .run_scraper import load_routes, select_routes

_OUTPUT_PATH_DEFAULT = "pipeline_out.json"


def _load_records_from_jsonl(path: str) -> list[FareRecord]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(FareRecord(**json.loads(line)))
    return records


def _build_payload(result, dropped_count: int, raw_record_count: int, served_from: str) -> dict:
    """Shapes pipeline output to match airfare-dashboard's IndexPayload
    exactly (lib/types.ts) so pipeline_out.json can be dropped straight
    into the dashboard's sample-data path for local testing, with zero
    field-mapping glue code needed on either side."""
    usable = sum(1 for d in result.route_detail if d.source == "scraped")
    return {
        "index_timeseries": [
            {"observation_date": result.observation_date, "index_value": result.index_value, "base_date": result.base_date}
        ],
        "latest_date": result.observation_date,
        "route_detail_latest": [d.to_dict() for d in result.route_detail],
        "data_quality": {
            "imputed_via_carry_forward": len(result.route_detail) - usable,
            "imputation_rate": (len(result.route_detail) - usable) / len(result.route_detail) if result.route_detail else 0.0,
            "source_layer": {
                "total_raw_records": raw_record_count,
                "parse_failed": 0,  # FareRecord.__post_init__ rejects these before they ever reach a jsonl line
                "null_fare_or_sold_out": 0,
                "statistical_anomalies_removed": dropped_count,
                "usable_observations": raw_record_count,
                "usable_rate": 1.0 if raw_record_count == 0 else (raw_record_count) / raw_record_count,
            },
        },
        "coverage_weight_pct": result.coverage_weight_pct,
        "routes_used": result.routes_used,
        "routes_total": result.routes_total,
        "served_from": served_from,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full scrape -> index pipeline")
    parser.add_argument("--target", choices=["indigo", "air_india", "spicejet", "akasa", "makemytrip", "google_flights"],
                         default="google_flights")
    parser.add_argument("--top", type=int, default=20, help="Scrape the top N routes by basket weight")
    parser.add_argument("--routes", type=str, default=None, help="Comma-separated explicit route_ids, overrides --top")
    parser.add_argument("--mode", choices=["quick", "full"], default="quick",
                         help="Recorded in scrape_runs for the dashboard's status display; doesn't itself change behavior")
    parser.add_argument("--from-file", type=str, default=None,
                         help="Load FareRecords from an existing .jsonl instead of scraping live")
    parser.add_argument("--days-ahead", type=int, default=21)
    parser.add_argument("--delay", type=float, default=4.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--out", type=str, default=_OUTPUT_PATH_DEFAULT)
    parser.add_argument("--push-supabase", action="store_true", help="Push results to Supabase (needs env vars)")
    parser.add_argument("--dry-run", action="store_true", help="Never touch Supabase, even if --push-supabase is set")
    args = parser.parse_args()

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    push = args.push_supabase and not args.dry_run
    if args.push_supabase and args.dry_run:
        print("--dry-run set: ignoring --push-supabase, nothing will be written to Supabase.")
    if push and not (supabase_url and supabase_key):
        print("--push-supabase set but SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY env vars are missing.", file=sys.stderr)
        sys.exit(1)

    all_routes = load_routes()
    explicit = args.routes.split(",") if args.routes else None
    selected = select_routes(all_routes, top=args.top, explicit=explicit)
    basket = [
        RouteBasketEntry(r["route_id"], weight=r["weight"], base_price=r["base_fare"],
                          origin_name=r.get("origin_name", ""), destination_name=r.get("destination_name", ""))
        for r in all_routes
    ]
    route_distance_km = {r["route_id"]: r["distance_km"] for r in all_routes}

    run_id = None
    if push:
        from . import supabase_writer
        run_id = supabase_writer.start_scrape_run(
            supabase_url, supabase_key, target=args.target, mode=args.mode, routes_attempted=len(selected)
        )

    try:
        if args.from_file:
            print(f"Loading records from {args.from_file} (no live scraping)...")
            records = _load_records_from_jsonl(args.from_file)
        else:
            print(f"Scraping {len(selected)} route(s) against '{args.target}' (this hits the real internet)...")
            from .fare_scraper import run_scrape
            records, report = run_scrape(
                args.target, selected, days_ahead=args.days_ahead, delay_seconds=args.delay, max_retries=args.retries
            )
            print(f"Scrape done: {report.routes_ok} ok, {report.routes_empty} empty, {report.routes_errored} errored.")

        observations = normalize_records(records)
        print(f"Normalized {len(records)} raw fares into {len(observations)} route observations.")

        last_known_prices: dict[str, float] = {}
        base_date: str | None = None
        if supabase_url and supabase_key:
            from . import supabase_writer
            last_known_prices = supabase_writer.fetch_last_known_prices(supabase_url, supabase_key)
            base_date = supabase_writer.fetch_base_date(supabase_url, supabase_key)

        today = date.today().isoformat()
        base_date = base_date or today  # first run ever defines the base period

        filter_result = filter_anomalies(observations, route_distance_km=route_distance_km, previous_prices=last_known_prices)
        if filter_result.flags:
            print(f"Anomaly filter dropped {len(filter_result.dropped)} route(s):")
            for flag in filter_result.flags:
                print(f"  {flag.route_id}: {flag.reason} — {flag.detail}")

        result = compute_index(
            basket, filter_result.clean, observation_date=today, base_date=base_date,
            last_known_prices=last_known_prices,
        )
        print(
            f"Index for {today}: {result.index_value:.2f} (base {base_date}=100) | "
            f"{result.routes_used}/{result.routes_total} routes scraped this run | "
            f"{result.coverage_weight_pct:.1f}% of basket weight covered"
        )

        payload = _build_payload(result, len(filter_result.dropped), len(records), served_from="supabase" if push else "pipeline")
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"Pipeline output written to {args.out}")

        if push:
            from . import supabase_writer
            supabase_writer.push_index_result(supabase_url, supabase_key, result)
            supabase_writer.finish_scrape_run(
                supabase_url, supabase_key, run_id, status="completed",
                routes_scraped=result.routes_used, routes_anomalous=len(filter_result.dropped),
                coverage_weight_pct=result.coverage_weight_pct,
            )
            print("Pushed to Supabase: daily_index + route_daily_detail updated, scrape_runs marked completed.")

    except Exception as exc:  # noqa: BLE001 — make sure a failed run is visible in scrape_runs, not just a dead CI job
        if push and run_id is not None:
            from . import supabase_writer
            supabase_writer.finish_scrape_run(
                supabase_url, supabase_key, run_id, status="failed",
                routes_scraped=0, routes_anomalous=0, coverage_weight_pct=0.0, error=str(exc),
            )
        raise


if __name__ == "__main__":
    main()
