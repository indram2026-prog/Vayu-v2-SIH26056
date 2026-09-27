"""
Talks to Supabase's REST API (PostgREST) to (a) read the most recent known
price per route, so anomaly_filter.py has a day-over-day baseline, and (b)
push a completed pipeline run's results.

Deliberately built on `urllib.request` (Python stdlib) rather than the
`supabase-py` package or `requests` — this keeps the whole pipeline
(models/normalize/anomaly_filter/index_engine all already stdlib-only)
installable and testable with ZERO third-party dependencies beyond
`scrapling` itself, and a GitHub Actions runner never needs a second
package install step just to push results.

Every function here takes url/key explicitly rather than reading env vars
itself — makes it trivially unit-testable (nothing to monkeypatch) and
keeps env-var handling in exactly one place: run_pipeline.py's CLI layer.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional

from .index_engine import IndexResult


class SupabaseError(RuntimeError):
    pass


def _request(url: str, service_key: str, method: str, path: str, *, params: str = "", body: Optional[list] = None,
             prefer: str = "") -> object:
    full_url = f"{url.rstrip('/')}/rest/v1/{path}{params}"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(full_url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SupabaseError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SupabaseError(f"{method} {path} -> {exc}") from exc


def fetch_last_known_prices(url: str, service_key: str) -> dict[str, float]:
    """Most recent 'scraped' (not 'sample') price per route across all of
    history — used as anomaly_filter's day-over-day baseline AND as
    index_engine's display fallback for routes with no fresh data today.
    One request, ordered so the LAST row per route_id wins when collapsed
    client-side (PostgREST doesn't have a native DISTINCT ON over REST)."""
    rows = _request(
        url, service_key, "GET", "route_daily_detail",
        params="?select=route_id,route_price,observation_date&source=eq.scraped&order=observation_date.asc",
    )
    latest: dict[str, float] = {}
    for row in rows or []:
        if row.get("route_price") is not None:
            latest[row["route_id"]] = float(row["route_price"])
    return latest


def fetch_base_date(url: str, service_key: str) -> Optional[str]:
    """The base_date already committed to in daily_index (the very first
    row's base_date), so every subsequent run keeps using the SAME base
    period rather than accidentally re-basing to 100 every run. Returns
    None if daily_index is empty (this is the first run ever)."""
    rows = _request(
        url, service_key, "GET", "daily_index",
        params="?select=base_date&order=observation_date.asc&limit=1",
    )
    if rows:
        return rows[0]["base_date"]
    return None


def start_scrape_run(url: str, service_key: str, *, target: str, mode: str, routes_attempted: int) -> int:
    rows = _request(
        url, service_key, "POST", "scrape_runs",
        body=[{"target": target, "mode": mode, "routes_attempted": routes_attempted, "status": "running"}],
        prefer="return=representation",
    )
    return rows[0]["id"]


def finish_scrape_run(url: str, service_key: str, run_id: int, *, status: str, routes_scraped: int,
                       routes_anomalous: int, coverage_weight_pct: float, error: Optional[str] = None) -> None:
    from datetime import datetime, timezone

    _request(
        url, service_key, "PATCH", "scrape_runs",
        params=f"?id=eq.{run_id}",
        body=[{
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "routes_scraped": routes_scraped,
            "routes_anomalous": routes_anomalous,
            "coverage_weight_pct": coverage_weight_pct,
            "error": error,
        }],
    )


def push_index_result(url: str, service_key: str, result: IndexResult) -> None:
    """Upserts one day's daily_index row and its route_daily_detail rows.
    on_conflict targets the primary keys declared in schema.sql, so
    re-running the pipeline twice for the same observation_date (e.g. a
    quick refresh followed later by the scheduled full run) updates that
    day's numbers in place rather than erroring or duplicating."""
    _request(
        url, service_key, "POST", "daily_index",
        params="?on_conflict=observation_date",
        body=[{
            "observation_date": result.observation_date,
            "index_value": result.index_value,
            "base_date": result.base_date,
        }],
        prefer="resolution=merge-duplicates",
    )

    detail_rows = [
        {
            "route_id": d.route_id,
            "observation_date": result.observation_date,
            "weight": d.weight,
            "route_price": d.latest_price,
            "price_relative": d.price_relative,
            "source": d.source,
            "airlines": d.airlines,
            "origin_name": d.origin_name,
            "destination_name": d.destination_name,
        }
        for d in result.route_detail
    ]
    # PostgREST can choke on very large single-request bodies in practice;
    # 325 small rows is fine in one call, but chunking keeps this correct
    # even if the basket grows well past that.
    chunk_size = 500
    for i in range(0, len(detail_rows), chunk_size):
        _request(
            url, service_key, "POST", "route_daily_detail",
            params="?on_conflict=route_id,observation_date",
            body=detail_rows[i : i + chunk_size],
            prefer="resolution=merge-duplicates",
        )
