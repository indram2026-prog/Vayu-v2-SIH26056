"""
Back-test the daily index against DGCA monthly average fares (pure stdlib).

You supply two CSVs:
  index CSV : date,index_value               (daily series from the pipeline)
  DGCA CSV  : month,avg_fare                  (YYYY-MM, rupees)
This module ships no DGCA numbers.

Because DGCA publishes monthly averages and our index is a daily relative
(base 100), both are rebased to the same base month and compared on the months
they share: correlation of levels, mean absolute error of the rebased levels,
and whether month-over-month direction agrees. With a single shared month there
is nothing to correlate; the report says so instead of inventing a statistic.

    python -m scraper.backtest index.csv dgca.csv
"""

from __future__ import annotations

import csv
import math
import sys
from typing import Mapping


def load_index_csv(path: str) -> "dict[str, float]":
    with open(path, encoding="utf-8", newline="") as fh:
        return {r["date"][:10]: float(r["index_value"]) for r in csv.DictReader(fh)}


def load_dgca_csv(path: str) -> "dict[str, float]":
    with open(path, encoding="utf-8", newline="") as fh:
        return {r["month"][:7]: float(str(r["avg_fare"]).replace(",", "")) for r in csv.DictReader(fh)}


def monthly_mean(daily: Mapping[str, float]) -> "dict[str, float]":
    buckets: "dict[str, list[float]]" = {}
    for d, v in daily.items():
        buckets.setdefault(d[:7], []).append(v)
    return {m: sum(v) / len(v) for m, v in buckets.items()}


def _pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sxx * syy)


def days_covered(daily: Mapping[str, float]) -> int:
    return len(daily)


def compare(index_daily: Mapping[str, float], dgca_monthly: Mapping[str, float]) -> dict:
    idx_m = monthly_mean(index_daily)
    months = sorted(set(idx_m) & set(dgca_monthly))
    report: dict = {
        "index_days": days_covered(index_daily),
        "meets_30_day_requirement": days_covered(index_daily) >= 30,
        "shared_months": months,
    }
    if not months:
        report["status"] = "no_shared_months"
        return report
    base = months[0]
    idx_rebased = [100.0 * idx_m[m] / idx_m[base] for m in months]
    dgca_rebased = [100.0 * dgca_monthly[m] / dgca_monthly[base] for m in months]
    report["rebased_to"] = base
    report["index_rebased"] = dict(zip(months, idx_rebased))
    report["dgca_rebased"] = dict(zip(months, dgca_rebased))
    if len(months) < 2:
        report["status"] = "single_month_only"
        return report
    report["status"] = "ok"
    report["mean_abs_error_pts"] = sum(abs(a - b) for a, b in zip(idx_rebased, dgca_rebased)) / len(months)
    report["pearson_r"] = _pearson(idx_rebased, dgca_rebased) if len(months) >= 3 else None
    steps = [(idx_rebased[i] - idx_rebased[i - 1], dgca_rebased[i] - dgca_rebased[i - 1]) for i in range(1, len(months))]
    agree = sum(1 for a, b in steps if (a >= 0) == (b >= 0))
    report["direction_agreement"] = f"{agree}/{len(steps)}"
    return report


def main(argv: "list[str] | None" = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: python -m scraper.backtest <index.csv> <dgca.csv>")
        return 2
    import json
    print(json.dumps(compare(load_index_csv(args[0]), load_dgca_csv(args[1])), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
