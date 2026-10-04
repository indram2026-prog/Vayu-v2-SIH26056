-- Additive migration (safe to re-run). Does not alter existing tables.
-- Run in the Supabase SQL editor AFTER schema.sql.

-- Individual fare quotes with lead time and a fare breakdown.
create table if not exists fare_quotes (
    id                bigserial primary key,
    observed_at       timestamptz not null default now(),
    travel_date       date not null,
    lead_days         int  not null,
    route_id          text not null,
    carrier           text,
    fare_class        text,
    base_fare         numeric,
    taxes             numeric,
    user_development_fee numeric,
    convenience_fee   numeric,
    total_fare        numeric not null check (total_fare > 0),
    source            text not null,
    method            text
);
create index if not exists fare_quotes_route_obs on fare_quotes (route_id, observed_at);
create index if not exists fare_quotes_lead on fare_quotes (lead_days);

-- Matched-model chained index, kept alongside the existing daily_index.
create table if not exists daily_index_chained (
    observation_date     date primary key,
    index_value          numeric not null,
    link                 numeric not null,
    matched_items        int not null,
    matched_weight_pct   numeric not null,
    note                 text not null default ''
);

alter table fare_quotes enable row level security;
alter table daily_index_chained enable row level security;

drop policy if exists "public read" on fare_quotes;
create policy "public read" on fare_quotes for select using (true);
drop policy if exists "public read" on daily_index_chained;
create policy "public read" on daily_index_chained for select using (true);
