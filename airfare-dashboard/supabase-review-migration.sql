-- Additive to the schema in the SIH26056 etl-python repo (schema.sql).
-- Run this once in the Supabase SQL editor for the same project.

create table if not exists daily_index_review (
    observation_date  date primary key references daily_index(observation_date),
    reviewed_at       timestamptz not null default now()
);

alter table daily_index_review enable row level security;
create policy "public read" on daily_index_review for select using (true);
-- No public insert/update policy: only the service_role key (used by this
-- Next.js app's server-side API route, never exposed to the browser) can
-- write a review sign-off.
