"""
Replace the gravity-model placeholder weights with DGCA passenger traffic.

You supply a CSV of DGCA city-pair passenger numbers (columns: origin,
destination, passengers). Directions are combined, so DEL->BOM and BOM->DEL add
up to one route. This module ships NO traffic numbers; it only reads yours.

Weights:
  - routes found in the DGCA file get weight proportional to passengers
  - routes not in the file keep their existing (gravity) weight
  - the DGCA-derived group is scaled so that all weights still sum to 1.0,
    with the unmatched routes keeping the share they already held
Each route records `weight_source` ("dgca" or "gravity") and the result reports
how much of the basket the DGCA data actually covers.

    python -m scraper.dgca_weights dgca_traffic.csv  # writes shared/routes_dgca.json
"""

from __future__ import annotations

import csv
import json
import os
import sys
from typing import Iterable


def load_traffic(path: str) -> "dict[frozenset, float]":
    traffic: "dict[frozenset, float]" = {}
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            o, d = row["origin"].strip().upper(), row["destination"].strip().upper()
            try:
                n = float(str(row["passengers"]).replace(",", ""))
            except ValueError:
                continue
            if o == d or n <= 0:
                continue
            key = frozenset((o, d))
            traffic[key] = traffic.get(key, 0.0) + n
    return traffic


def apply_dgca_weights(routes: "Iterable[dict]", traffic: "dict[frozenset, float]") -> "tuple[list[dict], dict]":
    routes = [dict(r) for r in routes]
    matched = [r for r in routes if frozenset((r["origin"], r["destination"])) in traffic]
    unmatched = [r for r in routes if r not in matched]
    old_total = sum(r["weight"] for r in routes) or 1.0
    unmatched_share = sum(r["weight"] for r in unmatched) / old_total
    matched_share = 1.0 - unmatched_share
    pax_total = sum(traffic[frozenset((r["origin"], r["destination"]))] for r in matched)

    for r in routes:
        key = frozenset((r["origin"], r["destination"]))
        if key in traffic and pax_total > 0:
            r["weight"] = matched_share * traffic[key] / pax_total
            r["weight_source"] = "dgca"
        else:
            r["weight"] = r["weight"] / old_total
            r["weight_source"] = "gravity"
    summary = {
        "routes_total": len(routes),
        "routes_with_dgca": len(matched),
        "dgca_weight_share_pct": round(100.0 * matched_share, 2),
        "weights_sum": sum(r["weight"] for r in routes),
    }
    return routes, summary


def main(argv: "list[str] | None" = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: python -m scraper.dgca_weights <dgca_traffic.csv> [out.json]")
        return 2
    here = os.path.dirname(__file__)
    src = os.path.join(here, "..", "..", "shared", "routes.json")
    out = args[1] if len(args) > 1 else os.path.join(here, "..", "..", "shared", "routes_dgca.json")
    with open(src, encoding="utf-8") as fh:
        data = json.load(fh)
    routes, summary = apply_dgca_weights(data["routes"], load_traffic(args[0]))
    data["routes"] = routes
    data["methodology"] = "Weights from DGCA city-pair passenger traffic where available; gravity-model weights otherwise. See weight_source per route."
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    print(json.dumps(summary, indent=2))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
