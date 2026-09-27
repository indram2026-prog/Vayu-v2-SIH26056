"use client";

import useSWR from "swr";
import { IndexPayload } from "@/lib/types";
import { DashboardSkeleton } from "@/components/Skeleton";
import { IndexChart } from "@/components/IndexChart";
import { RouteTable } from "@/components/RouteTable";
import { DataQualityPanel } from "@/components/DataQualityPanel";
import { ReviewToggle } from "@/components/ReviewToggle";
import { InfoTooltip } from "@/components/Tooltip";
import { RefreshButton } from "@/components/RefreshButton";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export default function Page() {
  const { data, error } = useSWR<IndexPayload>("/api/index-data", fetcher);

  // Only a true cold start (nothing in the localStorage-backed SWR cache
  // yet) shows the skeleton. A repeat visit renders last-known data
  // immediately, then SWR revalidates quietly underneath it.
  if (!data && !error) {
    return (
      <main className="mx-auto max-w-2xl px-5 py-10">
        <DashboardSkeleton />
      </main>
    );
  }

  if (error || !data) {
    return (
      <main className="mx-auto max-w-2xl px-5 py-10">
        <p className="text-sm text-muted dark:text-muted-dark">
          Could not load today&apos;s index. Reload, or check back shortly.
        </p>
      </main>
    );
  }

  const ts = data.index_timeseries;
  const latest = ts[ts.length - 1];
  const prev = ts.length > 1 ? ts[ts.length - 2] : latest;
  const dayDelta = latest.index_value - prev.index_value;
  const isReviewed = data.reviewed_dates.includes(latest.observation_date);

  return (
    <main className="mx-auto max-w-2xl px-5 py-10">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold leading-snug">India Real-Time Airfare Price Index</h1>
        <p className="mt-2 text-sm leading-relaxed text-muted dark:text-muted-dark">
          A weighted composite of {data.route_detail_latest.length} domestic sectors across India&apos;s
          major airports, economy cabin, drawn from four advance-purchase windows and four sources.
          {data.served_from === "sample" && " Running on sample data — connect Supabase for live figures."}
        </p>
      </header>

      <div className="mb-1 flex flex-wrap items-baseline gap-4">
        <div className="nums text-5xl font-semibold text-accent dark:text-accent-dark">
          {latest.index_value.toFixed(2)}
        </div>
        <div className={`nums text-sm ${dayDelta >= 0 ? "text-up dark:text-up-dark" : "text-down dark:text-down-dark"}`}>
          {dayDelta >= 0 ? "up" : "down"} {Math.abs(dayDelta).toFixed(2)} from the previous day
        </div>
        <ReviewToggle date={latest.observation_date} initiallyReviewed={isReviewed} />
      </div>
      <div className="mb-4 text-sm text-muted dark:text-muted-dark">
        Base period {latest.base_date}, set to 100.
        {typeof data.routes_used === "number" && typeof data.routes_total === "number" && (
          <>
            {" "}
            Computed from{" "}
            <span className="text-live dark:text-live-dark">
              {data.routes_used} of {data.routes_total} routes
            </span>{" "}
            actually scraped today ({(data.coverage_weight_pct ?? 0).toFixed(1)}% of basket weight) — real-time
            data only, never sample fares.
          </>
        )}
      </div>
      <div className="mb-8">
        <RefreshButton />
      </div>

      <section className="section mb-8">
        <h2 className="mb-4 text-sm font-medium">Index over the last {ts.length} days</h2>
        <IndexChart data={ts} />
      </section>

      <section className="section mb-8">
        <h2 className="mb-4 text-sm font-medium">Route detail, latest day</h2>
        <RouteTable routes={data.route_detail_latest} />
        <p className="mt-4 text-xs leading-relaxed text-muted dark:text-muted-dark">
          Weights are illustrative placeholders shaped on India&apos;s known domestic traffic pattern.
          Production weights should come from DGCA&apos;s published sector-wise passenger traffic data.
        </p>
      </section>

      <section className="section">
        <h2 className="mb-4 flex items-center text-sm font-medium">
          Data quality
          <InfoTooltip label="What an analyst checks before trusting today's number." />
        </h2>
        <DataQualityPanel dq={data.data_quality} />
      </section>

      <footer className="mt-8 text-xs leading-relaxed text-muted dark:text-muted-dark">
        Pipeline: scrapers, normalization, a robust cross-source anomaly filter, then a Laspeyres-type
        weighted index. Runs on synthetic fare data until the live scrapers are connected.
      </footer>
    </main>
  );
}
