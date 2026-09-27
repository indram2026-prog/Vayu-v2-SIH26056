export interface IndexPoint {
  observation_date: string;
  index_value: number;
  base_date: string;
}

export interface RouteDetail {
  route_id: string;
  weight: number;
  base_price: number | null;
  latest_price: number | null;
  price_relative: number | null;
  // Optional because the live Supabase path (route_daily_detail table)
  // doesn't carry these yet — see app/api/index-data/route.ts. The search
  // bar falls back to route_id-only matching when they're absent.
  origin_name?: string;
  destination_name?: string;
  // "scraped": this row is real data the pipeline actually captured and
  // counted in today's index_value this run.
  // "sample": no fresh trusted data this run — falls back to the last
  // known real price (or the placeholder base_price if never scraped).
  // Undefined only for the bundled static sampleData.ts snapshot, which
  // predates this field entirely — treat undefined the same as "sample".
  source?: "scraped" | "sample";
  airlines?: string[];
}

export interface SourceLayerQuality {
  total_raw_records: number;
  parse_failed: number;
  null_fare_or_sold_out: number;
  statistical_anomalies_removed: number;
  usable_observations: number;
  usable_rate: number;
}

export interface DataQuality {
  imputed_via_carry_forward: number;
  imputation_rate: number;
  source_layer: SourceLayerQuality;
}

export interface IndexPayload {
  index_timeseries: IndexPoint[];
  latest_date: string;
  route_detail_latest: RouteDetail[];
  data_quality: DataQuality;
  reviewed_dates: string[]; // dates a MoSPI analyst has signed off on
  served_from: "supabase" | "sample";
  // What fraction of the 325-route basket's weight the LATEST day's
  // index_value was actually computed from (real scraped data only — see
  // etl-python/scraper/index_engine.py). Optional because the bundled
  // sampleData.ts snapshot predates this field.
  coverage_weight_pct?: number;
  routes_used?: number;
  routes_total?: number;
}

export interface ScrapeRunStatus {
  configured: boolean; // false if Supabase env vars aren't set at all
  status?: "running" | "completed" | "failed";
  target?: string;
  mode?: "quick" | "full";
  started_at?: string;
  finished_at?: string | null;
  routes_scraped?: number | null;
  routes_anomalous?: number | null;
  coverage_weight_pct?: number | null;
  error?: string | null;
}
