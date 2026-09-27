"""
Turns a captured XHR JSON payload (from Scrapling's `capture_xhr` /
`response.captured_xhr`) into a list of FareRecord.

Why heuristic key-scanning instead of a fixed JSON path: every OTA's search
API returns a different, deeply nested, undocumented shape, and that shape
changes across A/B tests and deploys without notice. A fixed path like
`data["results"][0]["fare"]["total"]` breaks the instant the site changes
one level of nesting. Instead, this recursively walks the whole payload and
pulls out every dict that *looks like* a flight-fare object — matches Scrapling's
own philosophy (in its CSS/adaptive parser) of recognizing things by shape,
not by a brittle fixed address.

This module is pure stdlib — zero dependency on the `scrapling` package —
specifically so it can be unit-tested in this sandbox (no network, no
scrapling installed) and in any CI runner without browser dependencies.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Optional

from .models import FareRecord, FareRecordError

# Key names seen across major Indian OTA/airline search APIs in publicly
# documented API traces. Not verified against a live response in this
# session — extend this list the moment you inspect real payloads.
_FARE_KEYS = (
    "totalFare", "total_fare", "totalPrice", "total_price",
    "fareAmount", "fare_amount", "amount", "price", "displayPrice",
    "grossFare", "netFare",
)
_AIRLINE_KEYS = (
    "airline", "airlineName", "marketingCarrier", "carrierName",
    "operatingCarrier", "flightCarrier",
)


def _walk_with_ancestors(obj: Any, ancestors: tuple[dict, ...] = ()) -> Iterable[tuple[dict, tuple[dict, ...]]]:
    """Yield every (dict, ancestor_dicts) pair anywhere in the (possibly
    deeply nested) JSON tree, nearest ancestor last. Carrying ancestors
    matters in practice: real search APIs commonly put the fare one level
    down in a `fareDetails`/`priceBreakup` sub-object while the airline
    name stays on the parent `flight` object — a plain flat walk finds the
    fare but, without ancestor context, can't see the sibling airline
    field that lives one level up."""
    if isinstance(obj, dict):
        yield obj, ancestors
        for v in obj.values():
            yield from _walk_with_ancestors(v, ancestors + (obj,))
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_with_ancestors(item, ancestors)


def _first_present(d: dict, keys: tuple[str, ...]) -> Optional[Any]:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _first_present_in_node_or_ancestors(
    node: dict, ancestors: tuple[dict, ...], keys: tuple[str, ...]
) -> Optional[Any]:
    """Check the node itself first, then walk up through ancestors nearest
    first — a fare-object's own airline field (if any) should win over a
    same-named field further up the tree."""
    found = _first_present(node, keys)
    if found is not None:
        return found
    for ancestor in reversed(ancestors):
        found = _first_present(ancestor, keys)
        if found is not None:
            return found
    return None


def _coerce_fare(value: Any) -> Optional[float]:
    """Fare fields show up as int, float, numeric string, or (rarely) a
    string with currency formatting like '₹7,054'. Handle the common
    cases; give up (return None) rather than guess on anything weirder."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = "".join(ch for ch in value if ch.isdigit() or ch == ".")
        if cleaned:
            try:
                return float(cleaned)
            except ValueError:
                return None
    return None


def extract_fares_from_xhr(
    payload: dict,
    *,
    route_id: str,
    origin: str,
    destination: str,
    travel_date: str,
    source: str,
    fare_type: str = "displayed",
) -> list[FareRecord]:
    """Scan a captured JSON payload for fare-shaped dicts and return the
    valid ones as FareRecord. Records that fail FareRecord's own sanity
    checks (bad range, missing fields) are silently skipped, not raised —
    a single malformed entry in a 40-flight search response shouldn't take
    down the whole scrape."""
    records: list[FareRecord] = []
    seen_signatures: set[tuple] = set()

    for node, ancestors in _walk_with_ancestors(payload):
        raw_fare = _first_present(node, _FARE_KEYS)
        if raw_fare is None:
            continue
        fare = _coerce_fare(raw_fare)
        if fare is None:
            continue

        airline = _first_present_in_node_or_ancestors(node, ancestors, _AIRLINE_KEYS) or ""
        if not isinstance(airline, str):
            airline = str(airline)

        # Dedup: the same flight often appears twice in a payload (once in
        # a "cheapest per airline" summary block, once in the full list).
        signature = (route_id, airline, round(fare, 2))
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)

        try:
            records.append(
                FareRecord(
                    route_id=route_id,
                    origin=origin,
                    destination=destination,
                    airline=airline,
                    fare=fare,
                    fare_type=fare_type,
                    travel_date=travel_date,
                    source=source,
                    method="xhr_capture",
                    confidence="unverified",
                    raw_ref=f"xhr:{source}",
                )
            )
        except FareRecordError:
            # Sane-band or shape check failed — most likely this dict
            # wasn't actually a fare (e.g. a baggage fee or a seat count
            # that happened to use one of the same key names). Skip it.
            continue

    return records


def extract_indigo_fare_radar(payload: dict, *, source: str = "indigo") -> list[FareRecord]:
    """Parser for IndiGo's real `fare-radar` endpoint
    (https://6ewai.goindigo.in/r10next/web/fare-radar), confirmed against a
    live response on 2026-09-27 — this is the one parser in this file that
    is `confidence="verified"`, not a guess.

    Verified real shape:
        {
          "origin": "DEL", "originCity": "Delhi", "currency": "INR",
          "travelDate": "2026-09-28", "dateLabel": "Mon, 28 Sep",
          "fares": [
            {"iata": "BOM", "city": "Mumbai", "fare": 6147, "time": "16:15"},
            ...
          ]
        }

    Two things worth knowing before you rely on this:

    1. This is NOT a point-to-point search result — it's IndiGo's
       "cheapest fares from this origin" widget, fanning one origin out to
       several destination cities in a single response. That means one
       request can yield several routes' fares at once (a genuine
       efficiency win over one-request-per-route), but it also means the
       `destination`/route requested in the URL is not guaranteed to be
       one of the destinations actually returned — check the caller's
       wanted route against the `iata` values in the response.
    2. The `travelDate` in the response (confirmed: "2026-09-28", the
       upcoming Monday) did NOT match the `departureDate` query parameter
       that was actually requested ("2026-10-18") — the endpoint appears
       to ignore that parameter and always show near-term fares. Use the
       date IndiGo itself reports, not the one you asked for, or you will
       silently mislabel every record with the wrong travel date.
    """
    records: list[FareRecord] = []
    origin = payload.get("origin")
    travel_date = payload.get("travelDate")
    fares = payload.get("fares")
    if not origin or not travel_date or not isinstance(fares, list):
        return records

    for entry in fares:
        if not isinstance(entry, dict):
            continue
        destination = entry.get("iata")
        raw_fare = entry.get("fare")
        if not destination or raw_fare is None:
            continue
        fare = _coerce_fare(raw_fare)
        if fare is None:
            continue
        try:
            records.append(
                FareRecord(
                    route_id=f"{origin}-{destination}",
                    origin=origin,
                    destination=destination,
                    airline="IndiGo",  # single-airline site, not in the payload itself
                    fare=fare,
                    fare_type="displayed",
                    travel_date=travel_date,
                    source=source,
                    method="xhr_capture",
                    confidence="verified",
                    raw_ref="xhr:indigo:fare-radar",
                )
            )
        except FareRecordError:
            continue

    return records


def extract_air_india_air_bounds(payload: dict, *, source: str = "air_india") -> list[FareRecord]:
    """Parser for Air India's real booking-search endpoint

        https://api.airindia.com/cbiz-booking/v2/prime/search/air-bounds

    confirmed against a live response captured on 2026-09-27 (found via
    Chrome DevTools' Network-panel response-body search, the same
    "watch the XHR list, search every body for a fare you can see on
    screen" technique that found IndiGo's fare-radar endpoint). Like
    `extract_indigo_fare_radar`, this is `confidence="verified"` — a real
    shape, not a guess — but note what "verified" covers here: the JSON
    shape itself is confirmed from a real browser session; a `Scrapling`
    `StealthyFetcher` run has NOT yet independently confirmed it can
    trigger/capture this same request (see targets.py's notes).

    Real shape (heavily trimmed):
        {
          "responsePayload": [
            {"airBoundGroups": [
              {
                "boundDetails": {
                  "originLocationCode": "DEL", "destinationLocationCode": "BOM",
                  "segments": [{"flightId": "SEG-AI2951-DELBOM-2026-10-15-1330"}]
                },
                "airBounds": [
                  {"fareFamilyCode": "YHININ",
                   "availabilityDetails": [{"cabin": "eco", ...}],
                   "prices": {"totalPrices": [{"base": 4943, "total": 6822, ...}]}},
                  {"fareFamilyCode": "PFININ", ...},   <- premium economy
                  {"fareFamilyCode": "CFININ", ...},   <- business
                  ... up to 8 fare families for one flight
                ]
              }, ...
            ]}
          ],
          "dictionaries": {
            "location": {"NMI": {"cityCode": "BOM", ...}, "BOM": {"cityCode": "BOM", ...}},
            "airline": {"AI": "AIR INDIA"},
            "flight": {"SEG-AI2951-DELBOM-2026-10-15-1330": {
                "marketingAirlineCode": "AI", "marketingFlightNumber": "2951",
                "departure": {"locationCode": "DEL", "dateTime": "2026-10-15T13:30:00..."},
                "arrival": {"locationCode": "BOM", ...}
            }}
          }
        }

    Two real things this endpoint does that a naive parser would get wrong
    (same spirit as the two IndiGo gotchas documented above):

    1. **One flight → many fares, not one.** Unlike IndiGo's fare-radar
       (one fare per destination), each `airBoundGroups` entry here is ONE
       specific flight, and its `airBounds` list holds every bookable fare
       family for that flight — Economy Saver/Standard/Flex, Premium
       Economy, Business — commonly 6-8 real, independently bookable
       prices per flight. Picking "the first one" or deduping down to one
       per flight (the way the generic heuristic parser dedups) would
       silently throw away real fares. This parser returns all of them;
       picking a headline "cheapest displayed fare" per route is left to
       the caller/downstream aggregation, not this parser's job.
    2. **Airport code ≠ route-basket city code.** `boundDetails` reports
       real IATA *airport* codes, and Mumbai has two: `BOM` (Chhatrapati
       Shivaji Maharaj) and `NMI` (Navi Mumbai International) — confirmed
       both appear in the same live response for the same DEL-origin
       search. `shared/routes.json`'s basket is keyed by major-airport
       city codes, so a flight landing at NMI must still resolve to route
       `DEL-BOM`, not a phantom `DEL-NMI` that doesn't exist anywhere else
       in the pipeline. Fixed by resolving both ends through
       `dictionaries.location[code]["cityCode"]` rather than trusting the
       raw airport code directly — skip this and NMI flights silently
       vanish from every route-level aggregate.

    The travel date is read from `dictionaries.flight[...].departure.dateTime`
    (a real per-flight timestamp), not a request query parameter — unlike
    IndiGo's endpoint, nothing here suggested the date is ignored, but
    reading it from the flight record itself is still the more defensible
    source of truth. The returned fare is the `total` (all taxes/fees
    included, matching Air India's own displayed price), so `fare_type` is
    stamped `"all_in"`, not `"displayed"`.
    """
    records: list[FareRecord] = []

    response_payload = payload.get("responsePayload")
    dictionaries = payload.get("dictionaries")
    if not isinstance(response_payload, list) or not isinstance(dictionaries, dict):
        return records

    flights: dict = dictionaries.get("flight") or {}
    locations: dict = dictionaries.get("location") or {}
    airlines: dict = dictionaries.get("airline") or {}

    def city_code(airport_code: Optional[str]) -> Optional[str]:
        """Resolve a raw airport code (e.g. 'NMI') to the city-level code
        the route basket uses (e.g. 'BOM'). Falls back to the airport code
        itself if it's not in the location dictionary at all, rather than
        dropping the record outright — better to keep a plausibly-correct
        route_id than silently lose real fare data."""
        if not airport_code:
            return None
        loc = locations.get(airport_code)
        if isinstance(loc, dict) and loc.get("cityCode"):
            return loc["cityCode"]
        return airport_code

    for payload_item in response_payload:
        if not isinstance(payload_item, dict):
            continue
        groups = payload_item.get("airBoundGroups")
        if not isinstance(groups, list):
            continue

        for group in groups:
            if not isinstance(group, dict):
                continue
            bound = group.get("boundDetails") or {}
            segments = bound.get("segments") or []
            if not segments:
                continue

            first_flight = flights.get(segments[0].get("flightId"), {}) or {}
            last_flight = flights.get(segments[-1].get("flightId"), {}) or {}

            origin = city_code(
                bound.get("originLocationCode")
                or (first_flight.get("departure") or {}).get("locationCode")
            )
            destination = city_code(
                bound.get("destinationLocationCode")
                or (last_flight.get("arrival") or {}).get("locationCode")
            )
            if not origin or not destination:
                continue
            route_id = f"{origin}-{destination}"

            departure_dt = (first_flight.get("departure") or {}).get("dateTime")
            travel_date = departure_dt[:10] if isinstance(departure_dt, str) and len(departure_dt) >= 10 else None
            if not travel_date:
                continue

            marketing_code = first_flight.get("marketingAirlineCode")
            airline_raw = airlines.get(marketing_code) if marketing_code else None
            airline = airline_raw.title() if isinstance(airline_raw, str) else "Air India"

            for air_bound in group.get("airBounds") or []:
                if not isinstance(air_bound, dict):
                    continue
                fare_family_code = air_bound.get("fareFamilyCode") or ""
                prices = air_bound.get("prices") or {}
                total_prices = prices.get("totalPrices") or []
                price_entry = total_prices[0] if total_prices else None
                if not isinstance(price_entry, dict):
                    continue
                fare = _coerce_fare(price_entry.get("total"))
                if fare is None:
                    continue

                availability = air_bound.get("availabilityDetails") or []
                cabin = availability[0].get("cabin") if availability and isinstance(availability[0], dict) else None

                try:
                    records.append(
                        FareRecord(
                            route_id=route_id,
                            origin=origin,
                            destination=destination,
                            airline=airline,
                            fare=fare,
                            fare_type="all_in",
                            travel_date=travel_date,
                            source=source,
                            method="xhr_capture",
                            confidence="verified",
                            raw_ref=f"xhr:air_india:air-bounds:{fare_family_code or cabin or 'unknown'}",
                        )
                    )
                except FareRecordError:
                    continue

    return records


# ---------------------------------------------------------------------------
# google_flights: batchexecute RPC ("wrb.fr") — verified 2026-09-27
# ---------------------------------------------------------------------------
#
# Real shape, confirmed against a live captured
# GetShoppingResults response (debug_google_flights_DEL-BOM_xhr_0.json,
# 251KB, real internet, real fares visible in it):
#
# The top level is Google's generic `batchexecute` RPC envelope, the same
# framing used by many internal Google services (not Flights-specific —
# this is why fare_scraper.py's `_strip_xssi_prefix` / stream-scanner logic
# was written generically rather than hardcoded to one API). One response
# is a JSON array of frames; the ones that matter here look like:
#
#     ["wrb.fr", null, "<a second, independently JSON-encoded string>", ...]
#
# That third element is NOT itself nested JSON in the outer document — it
# is a STRING containing JSON, so it needs its own `json.loads()` call.
# This one response held SIX such "wrb.fr" frames (successive chunks of
# the same search, each restating and extending the flight list — the same
# flight recurs across frames with the same short opaque id, e.g. "Gm2ZA"),
# plus two bookkeeping frames ("di", "e") that carry no fare data.
#
# Inside a decoded frame, one flight *itinerary* (a specific bookable
# routing, one or more physical legs) is a list shaped like:
#
#     [carrier_code, [airline_name], [[leg_1_details], [leg_2_details], ...],
#      origin_iata, [dep_y, dep_m, dep_d], [dep_h, dep_m?],
#      dest_iata, [arr_y, arr_m, arr_d], [arr_h, arr_m?],
#      total_duration_min, overnight_day_offset_or_null, ...,
#      <price info array>, <availability array>, [[carrier, name, url]]]
#
# and each leg's own details array is shaped like:
#
#     [null, null, null, leg_origin_iata, leg_origin_name, leg_dest_name,
#      leg_dest_iata, null, [dep_h, dep_m?], null, [arr_h, arr_m?],
#      leg_duration_min, [...amenity flags...], num_stops_on_leg,
#      "NN in" (legroom), null, 1, "<aircraft model>", null, false,
#      [dep_y, dep_m, dep_d], [arr_y, arr_m, arr_d],
#      [carrier, flight_number, null, airline_name],
#      null, null, 1, null, null, null, null, "NN inches", <int>, 1]
#
# The itinerary-level price is a very distinctively-shaped 18-element
# array found somewhere inside the itinerary (position varies with how
# many legs/connection-info fields precede it, so this is found by shape,
# not by a fixed index — same philosophy as the generic heuristic parser
# above):
#
#     [null, null, <category:int>, <delta:int>, null, true, true,
#      <PRICE:int>, <AVG_PRICE:int>, ..., <MIN_PRICE:int>, <count:int>,
#      false, null, null, 1, null, <category_again:int>]
#
# Cross-checked three ways before trusting the /10 scaling below (not a
# guess — real evidence): (1) FareRecord's own sanity band is
# ₹1,000–₹1,00,000; the raw PRICE ints (e.g. 86974, 122000, 161000) are
# 10x too large for that band, dividing by 10 puts every single one of
# them inside it. (2) The same raw integer (e.g. 86974) also appears
# embedded in the per-leg details array right after the legroom string —
# it's the same value in the same units in two unrelated places in the
# payload, not a coincidence. (3) A separate 60-point price-history graph
# elsewhere in the payload reports prices already in plain rupees in the
# 11,500–14,000 range for this exact route/date; PRICE/10 for this
# response's flights (₹8,697–₹16,100) lands in the same real-world
# neighborhood. All three agree, so PRICE/10 is used, but flagged
# `confidence="verified"` on the *shape*, with the /10 divisor called out
# here explicitly in case a future capture disagrees.
def _decode_wrb_fr_frames(payload: Any) -> Iterable[Any]:
    """Recursively find every `["wrb.fr", ..., "<json-string>", ...]` frame
    anywhere in `payload` (however it's nested — a single flat list of
    frames, a list of chunks each holding one frame, etc., since framing
    has already proven to vary run-to-run for this endpoint) and yield
    each frame's THIRD element, re-decoded from its own JSON string.
    Frames whose third element isn't parseable JSON are skipped, not
    fatal — 30+ real fares typically ride on the other frames."""
    if isinstance(payload, dict):
        for v in payload.values():
            yield from _decode_wrb_fr_frames(v)
        return
    if not isinstance(payload, list):
        return
    if (
        len(payload) >= 3
        and payload[0] == "wrb.fr"
        and isinstance(payload[2], str)
    ):
        try:
            yield json.loads(payload[2])
        except (json.JSONDecodeError, TypeError):
            pass
        return  # a real frame's own children aren't further frames
    for item in payload:
        yield from _decode_wrb_fr_frames(item)


def _is_price_info_array(v: Any) -> bool:
    return (
        isinstance(v, list)
        and len(v) == 18
        and v[0] is None
        and v[1] is None
        and isinstance(v[2], int)
        and v[4] is None
        and v[5] is True
        and v[6] is True
        and isinstance(v[7], int)
        and isinstance(v[8], int)
    )


def _find_price_info(node: Any) -> Optional[dict]:
    """Depth-first search for the distinctively-shaped price array
    (see module docstring above) anywhere inside one itinerary node.
    Returns the FIRST one found — an itinerary only ever carries one."""
    if _is_price_info_array(node):
        return {"price": node[7] / 10.0, "avg_price": node[8] / 10.0, "min_price": node[10] / 10.0 if isinstance(node[10], int) else None}
    if isinstance(node, list):
        for item in node:
            found = _find_price_info(item)
            if found is not None:
                return found
    return None


def _is_itinerary(item: Any) -> bool:
    return (
        isinstance(item, list)
        and len(item) >= 10
        and isinstance(item[0], str) and 2 <= len(item[0]) <= 3
        and isinstance(item[1], list) and len(item[1]) >= 1 and isinstance(item[1][0], str)
        and isinstance(item[2], list) and len(item[2]) >= 1
        and isinstance(item[3], str) and len(item[3]) == 3
        and isinstance(item[6], str) and len(item[6]) == 3
        and isinstance(item[9], int)  # total duration, minutes
    )


def _iter_itineraries(node: Any) -> Iterable[list]:
    """Depth-first walk yielding every itinerary-shaped list found. Once a
    node matches, its children are NOT walked further for itineraries —
    each leg-details sub-array is shaped similarly enough (also starts
    with airport-code-like strings) that walking inside a confirmed match
    risks false positives; the interesting sub-fields are read directly
    off the matched node instead."""
    if _is_itinerary(node):
        yield node
        return
    if isinstance(node, list):
        for item in node:
            yield from _iter_itineraries(item)


def _hms_to_str(t: Any) -> Optional[str]:
    """[hour] or [hour, minute] -> 'HH:MM'. Google omits the minute
    entirely for on-the-hour times (e.g. [6] means 6:00), never a null
    placeholder — handle both to be safe."""
    if not isinstance(t, list) or not t or not isinstance(t[0], int):
        return None
    hour = t[0]
    minute = t[1] if len(t) > 1 and isinstance(t[1], int) else 0
    return f"{hour:02d}:{minute:02d}"


def _ymd_to_iso(d: Any) -> Optional[str]:
    if isinstance(d, list) and len(d) == 3 and all(isinstance(x, int) for x in d):
        return f"{d[0]:04d}-{d[1]:02d}-{d[2]:02d}"
    return None


def extract_google_flights_batchexecute(
    payload: Any, *, source: str = "google_flights"
) -> list[FareRecord]:
    """Parser for Google Flights' real `GetShoppingResults` batchexecute
    response — see the long comment above this function for the verified
    real shape and how the price-scaling divisor was cross-checked, not
    guessed.

    Real behavior worth knowing before relying on this:

    1. **One flight repeats across several frames.** The same response
       held six "wrb.fr" frames, and the same itinerary shows up in
       multiple of them (Google appears to send successive, overlapping
       snapshots of the same result set rather than one final list).
       Deduped here by (carrier, flight numbers, origin, destination,
       departure date+time) — a real short opaque per-itinerary id exists
       in the payload too (e.g. "Gm2ZA") but at a position that shifts
       with how many optional fields precede it, so the derived signature
       above is the more robust dedup key.
    2. **Connections are one itinerary, not one row per leg.** A
       DEL→LKO→BOM connection is a single itinerary entry whose
       `[[leg_1], [leg_2]]` sub-list has two leg-details arrays; this
       parser reports it as ONE fare for route DEL-BOM (the outer
       origin/destination), not two separate fares for DEL-LKO and
       LKO-BOM — matching what a person actually searching DEL-BOM sees
       and would pay.
    3. **Multiple carriers show up in one search** (SpiceJet, Akasa, Air
       India, IndiGo, Air India Express all appeared for one DEL-BOM/
       2026-10-18 query) — this parser returns every one it finds, not
       just the cheapest; picking a headline fare per route is left to
       the caller, same division of responsibility as
       `extract_air_india_air_bounds`.
    4. Google's `origin/destination` fields here are already city-major
       airport IATA codes (DEL, BOM, ...) in every case seen so far — no
       AI-style dual-airport-code resolution has been needed, but if a
       future capture shows a second-airport code for a metro (the way
       Air India's NMI/BOM split did), this parser will need the same
       `dictionaries.location`-style resolution added.
    """
    records: list[FareRecord] = []
    seen_signatures: set[tuple] = set()

    for frame in _decode_wrb_fr_frames(payload):
        for itinerary in _iter_itineraries(frame):
            origin = itinerary[3]
            destination = itinerary[6]
            route_id = f"{origin}-{destination}"

            legs = itinerary[2]
            first_leg = legs[0] if legs and isinstance(legs[0], list) else None
            flight_info = None
            if isinstance(first_leg, list) and len(first_leg) > 22 and isinstance(first_leg[22], list):
                flight_info = first_leg[22]
            flight_number = flight_info[1] if flight_info and len(flight_info) > 1 else None
            aircraft = first_leg[17] if isinstance(first_leg, list) and len(first_leg) > 17 else None

            dep_date = _ymd_to_iso(itinerary[4]) if len(itinerary) > 4 else None
            dep_time = _hms_to_str(itinerary[5]) if len(itinerary) > 5 else None
            if not dep_date:
                continue  # no usable travel_date -> can't build a sane FareRecord

            price_info = _find_price_info(itinerary)
            if not price_info:
                continue
            fare = price_info["price"]

            airline = itinerary[1][0]

            signature = (
                itinerary[0], flight_number, origin, destination, dep_date, dep_time, round(fare, 2)
            )
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)

            try:
                records.append(
                    FareRecord(
                        route_id=route_id,
                        origin=origin,
                        destination=destination,
                        airline=airline,
                        fare=fare,
                        fare_type="displayed",
                        travel_date=dep_date,
                        source=source,
                        method="xhr_capture",
                        confidence="verified",
                        raw_ref=(
                            f"xhr:google_flights:GetShoppingResults:"
                            f"{itinerary[0]}{flight_number or ''}"
                            + (f":{aircraft}" if aircraft else "")
                        ),
                    )
                )
            except FareRecordError:
                continue

    return records
