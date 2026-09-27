# Airfare Index Dashboard (Next.js, Vercel-ready)

Real Next.js 14 App Router project. `npm run dev` starts a real dev server;
`vercel deploy` ships a real site with its own URL. This replaces the earlier
Claude Artifact, which was a single static HTML file with nowhere to deploy
it from.

## What's real vs. sample right now

Runs entirely on bundled sample data (`lib/sampleData.ts`, a snapshot of a
real run of the Python pipeline) until you set two env vars. No code changes
needed to switch — `app/api/index-data/route.ts` checks for
`SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` at request time and falls back
cleanly if either is missing.

## The 5 techniques, wired for real (not decoratively)

1. **Skeleton loaders** (`components/Skeleton.tsx`) — shown only on a true
   cold start (nothing in the SWR cache yet), matching the real layout.
2. **Caching** (`components/SWRProvider.tsx`) — SWR with a localStorage-backed
   cache, so a repeat visit renders last-known data instantly and revalidates
   underneath it. Plus real HTTP caching on the API route itself
   (`export const revalidate = 300` + `Cache-Control` headers) so Vercel's
   edge doesn't re-hit Supabase on every request.
3. **Optimistic rendering** (`components/ReviewToggle.tsx`) — the one real
   mutation in the app: an analyst marking a day's index reviewed. Flips to
   "reviewed" the instant you click, confirms in the background, rolls
   back on failure (most "optimistic UI" demos skip the rollback).
4. **Tooltips** (`components/Tooltip.tsx`) — on every data-quality metric
   label, explaining what it means before you second-guess the number.
5. **Put together** — all four in one page (`app/page.tsx`).

## Design direction

Deliberately not the generic AI-generated look: no cream-background-plus-
terracotta-accent, no identical rounded cards with soft shadows, no serif
headline paired with a monospace label face, no all-caps eyebrow badge, no
middle-dot-joined metadata strings. Sections are separated by a single
hairline rule (`app/globals.css`'s `.section` class) rather than boxed cards;
one typeface (Public Sans — a real government-service font, not Inter) does
both headline and body; the only two directional colors (`up`/`down`, a
muted brick red and deep teal) are reserved for price movement, kept
separate from the neutral navy used for the chart line and headline number.

## Local setup

```bash
npm install
npm run dev
```

Open `http://localhost:3000` — runs on sample data immediately, no
Supabase required.

## Step by step: deploy to Vercel

1. **Push this repo to GitHub** (new repo, `git init && git add -A && git
   commit -m "init" && git remote add origin <your-repo-url> && git push -u
   origin main`).
2. **Go to vercel.com → Add New → Project**, import that GitHub repo. Vercel
   auto-detects Next.js — no config needed.
3. **Deploy.** You'll get a live `https://<project>.vercel.app` URL within
   ~a minute, running on sample data.
4. **(Optional, to go live on real data) Wire up Supabase:**
   - In your Supabase project's SQL editor, run
     `../etl-python/schema.sql` (from the SIH26056 repo) then this repo's
     `supabase-review-migration.sql`.
   - In Vercel → your project → Settings → Environment Variables, add
     `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` (Project Settings → API
     in Supabase).
   - Redeploy (Vercel → Deployments → ⋯ → Redeploy), or just push a commit.
   - Point the Python pipeline's `DATABASE_URL` at the same Supabase project
     so `run_pipeline.py` is what actually populates the tables this app reads.
5. **(Optional) Custom domain:** Vercel → Settings → Domains → add
   `airfare-index.mospi.gov.in` (or whatever's appropriate) and follow the
   DNS instructions it gives you.

## Directory guide

```
app/
  page.tsx                 the dashboard
  api/index-data/route.ts  GET - index series, route detail, data quality
  api/review/route.ts      POST - analyst sign-off (the optimistic mutation)
components/                Skeleton, Tooltip, IndexChart, RouteTable,
                            DataQualityPanel, ReviewToggle, SWRProvider
lib/
  types.ts                 shared types, mirrors the Python pipeline's output
  sampleData.ts             fallback snapshot
  supabase.ts               server client, null when unconfigured
```
