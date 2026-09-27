import { NextResponse } from "next/server";
import { getSupabaseServerClient } from "@/lib/supabase";
import { ScrapeRunStatus } from "@/lib/types";

// Polled by RefreshButton.tsx every few seconds after a "run live scrape"
// is triggered. Reads the LATEST row of scrape_runs (see schema.sql) —
// written by etl-python/scraper/supabase_writer.py at the start and end
// of every pipeline run — rather than asking the GitHub Actions API,
// because it's already the same Supabase connection this app uses for
// everything else, and it carries real pipeline detail (routes scraped,
// anomalies, coverage) that a bare CI job-status check wouldn't have.
export async function GET() {
  const supabase = getSupabaseServerClient();
  if (!supabase) {
    const body: ScrapeRunStatus = { configured: false };
    return NextResponse.json(body, { status: 501 });
  }

  const { data, error } = await supabase
    .from("scrape_runs")
    .select("status, target, mode, started_at, finished_at, routes_scraped, routes_anomalous, coverage_weight_pct, error")
    .order("started_at", { ascending: false })
    .limit(1);

  if (error) {
    console.error("[api/rescrape/status] Supabase query failed:", error);
    const body: ScrapeRunStatus = { configured: true, error: "Could not read scrape_runs." };
    return NextResponse.json(body, { status: 502 });
  }

  if (!data?.length) {
    const body: ScrapeRunStatus = { configured: true };
    return NextResponse.json(body);
  }

  const row = data[0];
  const body: ScrapeRunStatus = { configured: true, ...row };
  return NextResponse.json(body, { headers: { "Cache-Control": "no-store" } });
}
