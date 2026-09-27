import { NextRequest, NextResponse } from "next/server";
import { getSupabaseServerClient } from "@/lib/supabase";
import { SAMPLE_DATA } from "@/lib/sampleData";
import { IndexPayload } from "@/lib/types";

// Real HTTP-level caching, not decorative: this route is revalidated at most
// once every 5 minutes (matches how often the pipeline actually produces a
// new number), so repeat visits within that window are served from Vercel's
// edge cache rather than re-querying Supabase every time. The on-site
// "Refresh" button bypasses this deliberately — see the ?fresh=1 handling
// below — because a person who just clicked Refresh should never be served
// a 5-minute-stale cached response.
export const revalidate = 300;

export async function GET(request: NextRequest) {
  const isFreshRequest = request.nextUrl.searchParams.get("fresh") === "1";
  const supabase = getSupabaseServerClient();

  if (!supabase) {
    const payload: IndexPayload = { ...SAMPLE_DATA, reviewed_dates: [], served_from: "sample" };
    return NextResponse.json(payload, {
      headers: isFreshRequest
        ? { "Cache-Control": "no-store" }
        : { "Cache-Control": "public, s-maxage=300, stale-while-revalidate=600" },
    });
  }

  try {
    // Two-step, not one parallel Promise.all: route_daily_detail has to be
    // filtered to *one specific day*, and we don't know which day that is
    // until daily_index comes back. Filtering by the actual latest date is
    // correct regardless of how much history has accumulated.
    const { data: indexRows, error: indexErr } = await supabase
      .from("daily_index")
      .select("observation_date, index_value, base_date")
      .order("observation_date");

    if (indexErr || !indexRows?.length) {
      throw indexErr ?? new Error("no rows in daily_index");
    }

    const latest = indexRows[indexRows.length - 1];

    const [{ data: detailRows, error: detailErr }, { data: reviewRows }] = await Promise.all([
      supabase
        .from("route_daily_detail")
        .select("route_id, weight, route_price, price_relative, source, airlines, origin_name, destination_name")
        .eq("observation_date", latest.observation_date),
      supabase.from("daily_index_review").select("observation_date"),
    ]);

    if (detailErr) throw detailErr;

    const rows = detailRows ?? [];
    const totalWeight = rows.reduce((sum, r) => sum + Number(r.weight ?? 0), 0);
    const scrapedWeight = rows
      .filter((r) => r.source === "scraped")
      .reduce((sum, r) => sum + Number(r.weight ?? 0), 0);

    const payload: IndexPayload = {
      index_timeseries: indexRows,
      latest_date: latest.observation_date,
      route_detail_latest: rows.map((r) => ({
        route_id: r.route_id,
        weight: r.weight,
        base_price: null, // base price is a derived value; recomputed client-side from the series if needed
        latest_price: r.route_price,
        price_relative: r.price_relative,
        source: (r.source as "scraped" | "sample") ?? "sample",
        airlines: r.airlines ?? [],
        origin_name: r.origin_name ?? undefined,
        destination_name: r.destination_name ?? undefined,
      })),
      data_quality: SAMPLE_DATA.data_quality, // TODO: wire to a `daily_data_quality` table once the pipeline writes one
      reviewed_dates: (reviewRows ?? []).map((r) => r.observation_date),
      served_from: "supabase",
      coverage_weight_pct: totalWeight > 0 ? (scrapedWeight / totalWeight) * 100 : 0,
      routes_used: rows.filter((r) => r.source === "scraped").length,
      routes_total: rows.length,
    };

    return NextResponse.json(payload, {
      headers: isFreshRequest
        ? { "Cache-Control": "no-store" }
        : { "Cache-Control": "public, s-maxage=300, stale-while-revalidate=600" },
    });
  } catch (err) {
    console.error("[api/index-data] Supabase query failed, falling back to sample data:", err);
    const payload: IndexPayload = { ...SAMPLE_DATA, reviewed_dates: [], served_from: "sample" };
    return NextResponse.json(payload, {
      headers: { "Cache-Control": "public, s-maxage=60, stale-while-revalidate=120" }, // shorter TTL: this is a degraded response
    });
  }
}
