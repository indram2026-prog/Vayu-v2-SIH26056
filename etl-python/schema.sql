-- SIH26056 — core schema for the airfare index pipeline.
-- Idempotent: safe to run on a fresh Supabase project AND safe to re-run
-- against a project that already has these tables from an earlier version
-- of this project (every ADD COLUMN below uses IF NOT EXISTS).
--
-- Run once in the Supabase SQL editor, then run
-- supabase-review-migration.sql (same project) for the reviewer-signoff
-- table the dashboard's "mark reviewed" toggle uses.

create table if not exists daily_index (
    observation_date  date primary key,
    index_value       numeric not null,
    base_date         date not null
);

create table if not exists route_daily_detail (
    route_id          text not null,
    observation_date  date not null references daily_index(observation_date) on delete cascade,
    weight            numeric not null,
    route_price       numeric,             -- latest_price shown on the dashboard
    price_relative    numeric,
    -- 'scraped': real data from this run's scrape, passed the anomaly
    -- filter, and counted in that day's index_value.
    -- 'sample': no fresh trusted data this run — falls back to the last
    -- known price (or the placeholder base_fare if never scraped), shown
    -- for completeness but EXCLUDED from index_value's weighted sum.
    source            text not null default 'sample' check (source in ('scraped', 'sample')),
    airlines          text[] not null default '{}',
    origin_name       text,
    destination_name  text,
    primary key (route_id, observation_date)
);

-- One row per pipeline run — what the dashboard's "Refresh" ->
-- "run live scrape" button polls the status of (see
-- airfare-dashboard/app/api/rescrape/route.ts), and what the on-site
-- "last refreshed" timestamp reads.
create table if not exists scrape_runs (
    id                    bigserial primary key,
    started_at            timestamptz not null default now(),
    finished_at           timestamptz,
    target                text not null,          -- e.g. "google_flights"
    mode                  text not null,           -- "quick" | "full"
    routes_attempted      int,
    routes_scraped        int,                      -- passed anomaly filter
    routes_anomalous      int,                       -- dropped by anomaly_filter
    coverage_weight_pct   numeric,
    status                text not null default 'running' check (status in ('running', 'completed', 'failed')),
    error                 text
);

-- Columns added after the first version of this schema shipped — kept as
-- explicit ALTERs (rather than folded into the CREATE TABLEs above) so
-- re-running this file against an already-populated older database is
-- always safe.
alter table route_daily_detail add column if not exists source text not null default 'sample';
alter table route_daily_detail add column if not exists airlines text[] not null default '{}';
alter table route_daily_detail add column if not exists origin_name text;
alter table route_daily_detail add column if not exists destination_name text;

alter table daily_index enable row level security;
alter table route_daily_detail enable row level security;
alter table scrape_runs enable row level security;

-- Public read for all three (this is a public statistics dashboard) — no
-- public insert/update/delete policy on any of them. Only the
-- service_role key (server-side only, in Vercel's env vars and the GitHub
-- Actions secret, never sent to the browser) can write, because
-- service_role bypasses RLS entirely.
drop policy if exists "public read" on daily_index;
create policy "public read" on daily_index for select using (true);

drop policy if exists "public read" on route_daily_detail;
create policy "public read" on route_daily_detail for select using (true);

drop policy if exists "public read" on scrape_runs;
create policy "public read" on scrape_runs for select using (true);
