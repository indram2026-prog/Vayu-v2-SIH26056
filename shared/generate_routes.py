"""
Generates shared/routes.json — the single source of truth for the 325-route
basket (26 major Indian domestic airports, all unordered pairs: C(26,2) = 325).

Why a gravity model, not hand-picked weights:
  CPI-style index weights are supposed to reflect actual expenditure share.
  Until this project is wired to DGCA's published sector-wise passenger
  traffic data (see route_weights.py docstring), a gravity model — weight
  proportional to (traffic mass at A * traffic mass at B) / distance(A, B)
  — is the standard transport-economics stand-in: it reproduces the shape of
  real air-travel demand (heavy metro-metro routes dominate, thin
  tier-2/tier-3 long-haul routes are small) without inventing 325 numbers by
  hand. It is explicitly a placeholder — see the note this script writes
  into routes.json's "methodology" field.

Reproducibility: every number here is a pure function of the AIRPORTS table
below. Re-running this script always regenerates byte-identical weights, and
base fares are seeded off route_id (not Python's global random state), so
adding or re-ordering routes never reshuffles fares for unrelated routes.

Run:
    python3 generate_routes.py
Writes:
    ./routes.json  (this file's own directory, i.e. shared/routes.json)
"""

from __future__ import annotations
import json
import math
import hashlib
import os

# name, IATA, lat, lon, illustrative relative traffic mass (NOT official DGCA
# figures — swap this table for real DGCA sector-wise traffic the moment
# it's available; everything downstream recomputes automatically).
AIRPORTS: list[tuple[str, str, float, float, float]] = [
    ("Delhi",            "DEL", 28.5562, 77.1000, 100.0),
    ("Mumbai",           "BOM", 19.0887, 72.8679,  90.0),
    ("Bengaluru",        "BLR", 13.1989, 77.7068,  80.0),
    ("Hyderabad",        "HYD", 17.2403, 78.4294,  55.0),
    ("Chennai",          "MAA", 12.9941, 80.1709,  45.0),
    ("Kolkata",          "CCU", 22.6547, 88.4467,  40.0),
    ("Pune",             "PNQ", 18.5822, 73.9197,  28.0),
    ("Ahmedabad",        "AMD", 23.0772, 72.6347,  25.0),
    ("Goa",              "GOI", 15.3808, 73.8314,  20.0),
    ("Kochi",            "COK", 10.1520, 76.4019,  18.0),
    ("Jaipur",           "JAI", 26.8242, 75.8122,  15.0),
    ("Lucknow",          "LKO", 26.7606, 80.8893,  14.0),
    ("Chandigarh",       "IXC", 30.6735, 76.7885,  13.0),
    ("Guwahati",         "GAU", 26.1061, 91.5859,  12.0),
    ("Patna",            "PAT", 25.5913, 85.0880,  11.0),
    ("Bhubaneswar",      "BBI", 20.2444, 85.8178,  10.0),
    ("Thiruvananthapuram","TRV", 8.4821, 76.9200,   9.0),
    ("Nagpur",           "NAG", 21.0922, 79.0472,   9.0),
    ("Indore",           "IDR", 22.7218, 75.8011,   8.5),
    ("Varanasi",         "VNS", 25.4524, 82.8593,   8.0),
    ("Visakhapatnam",    "VTZ", 17.7211, 83.2245,   7.0),
    ("Srinagar",         "SXR", 33.9871, 74.7742,   7.0),
    ("Raipur",           "RPR", 21.1804, 81.7388,   6.0),
    ("Ranchi",           "IXR", 23.3143, 85.3217,   6.0),
    ("Madurai",          "IXM",  9.8345, 78.0934,   5.0),
    ("Bagdogra",         "IXB", 26.6812, 88.3286,   5.0),
]

assert len(AIRPORTS) == 26, f"expected 26 airports, got {len(AIRPORTS)}"

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def seeded_unit(route_id: str, salt: str) -> float:
    """Deterministic pseudo-random float in [0, 1), seeded off the route_id
    string (not global RNG state) so fares are reproducible and adding a
    route never perturbs any other route's fare."""
    h = hashlib.sha256(f"{route_id}:{salt}".encode()).hexdigest()
    return int(h[:12], 16) / 0xFFFFFFFFFFFF


def build_routes() -> list[dict]:
    n = len(AIRPORTS)
    raw: list[dict] = []
    for i in range(n):
        for j in range(i + 1, n):
            a, b = AIRPORTS[i], AIRPORTS[j]
            dist = haversine_km(a[2], a[3], b[2], b[3])
            route_id = f"{a[1]}-{b[1]}"
            # Naive 1/distance gravity over-weights short commuter hops (e.g.
            # BOM-PNQ at 124km) that road/rail/car actually absorb most of in
            # reality, and under-weights the long trunk metro corridors
            # (DEL-BOM, DEL-BLR) that dominate real domestic RPKs despite the
            # distance. A distance floor is the standard fix: below ~300km,
            # air's modal share is disproportionately small regardless of the
            # raw gravity pull, so impedance stops falling any further.
            impedance_dist = max(dist, 600.0)
            gravity = (a[4] * b[4]) / impedance_dist
            # Base fare: floor + per-km rate + small deterministic route-specific
            # jitter (+/-4%), so it isn't a suspiciously perfect straight line.
            floor, per_km = 2200.0, 3.6
            jitter = 0.96 + seeded_unit(route_id, "fare") * 0.08
            base_fare = round((floor + per_km * dist) * jitter, 2)
            raw.append({
                "route_id": route_id,
                "origin": a[1], "destination": b[1],
                "origin_name": a[0], "destination_name": b[0],
                "distance_km": round(dist, 1),
                "_gravity": gravity,
                "base_fare": base_fare,
            })

    total_gravity = sum(r["_gravity"] for r in raw)
    for r in raw:
        r["weight"] = r["_gravity"] / total_gravity
        del r["_gravity"]

    # Normalize away floating-point drift so the sum is exactly 1.0, the same
    # way route_weights.py's own assert expects — give the largest route the
    # residual rather than spreading a fudge factor across all 325.
    residual = 1.0 - sum(r["weight"] for r in raw)
    raw.sort(key=lambda r: r["weight"], reverse=True)
    raw[0]["weight"] += residual
    raw.sort(key=lambda r: r["route_id"])
    return raw


def main():
    routes = build_routes()
    assert len(routes) == 325, f"expected 325 routes, got {len(routes)}"
    assert abs(sum(r["weight"] for r in routes) - 1.0) < 1e-9

    payload = {
        "methodology": (
            "Gravity model placeholder (weight ~ mass_i * mass_j / distance_ij). "
            "Replace AIRPORTS traffic-mass column with DGCA published domestic "
            "sector-wise passenger traffic the moment it's available, then "
            "re-run this script — every consumer (route_weights.py, the TS "
            "scrapers, the dashboard) re-derives from this one file."
        ),
        "generated_by": "shared/generate_routes.py",
        "airport_count": len(AIRPORTS),
        "route_count": len(routes),
        "routes": routes,
    }

    out_path = os.path.join(os.path.dirname(__file__), "routes.json")
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)

    top5 = sorted(routes, key=lambda r: r["weight"], reverse=True)[:5]
    print(f"Wrote {out_path}")
    print(f"{len(routes)} routes, weights sum to {sum(r['weight'] for r in routes):.10f}")
    print("Top 5 by weight:")
    for r in top5:
        print(f"  {r['route_id']:8s} weight={r['weight']:.4f}  base_fare=Rs.{r['base_fare']:.0f}  dist={r['distance_km']}km")


if __name__ == "__main__":
    main()
