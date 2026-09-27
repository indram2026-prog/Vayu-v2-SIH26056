# SIH26056 — Deploy Guide: Vercel + Supabase + GitHub Actions

## First: does Google Flights really cover all 325 routes?

Yes, with one honest caveat. `targets.py`'s `google_flights` entry builds its
URL from `{origin}`/`{destination}`/`{date}` — nothing DEL-BOM-specific — and
`run_scraper.py --top 325` already iterates the WHOLE basket, not just the
20 it defaults to. So the same code that pulled 57 real fares across 5
airlines for DEL-BOM should generalize to any of the 325 pairs with zero
code changes.

The caveat: "should" is honest, not "confirmed." Every real-world proof so
far is for one route (DEL-BOM), verified twice. 325 different routes will
hit shapes that one route can't: island/UT destinations with far fewer
flights a day, routes with only 1-stop options (no nonstops at all), a few
pairs Google might show a train/bus alternative for instead of "no flights
found." The parser and pipeline are built to degrade gracefully on all of
these (an empty route just doesn't contribute to the index that day — see
`index_engine.py`'s coverage logic below) rather than crash, but "58 route
edge cases might quietly return 0 fares" is a real risk worth watching on
the FIRST full run, via `scrape_report.json` and the anomaly log, not an
assumption to skip checking.

## Architecture — why three services, not one

| Piece | Where it runs | Why there |
|---|---|---|
| `airfare-dashboard` (Next.js) | **Vercel** | Reads from Supabase, renders the site. This is what Vercel is built for. |
| `daily_index` / `route_daily_detail` / `scrape_runs` | **Supabase** (Postgres) | Shared state between the dashboard (reads) and the pipeline (writes). |
| `etl-python/scraper` (Scrapling + real Chromium) | **GitHub Actions** | The one piece Vercel genuinely cannot run: a real headless browser, no execution-time ceiling, evading bot walls. Vercel serverless functions have no browser binary and a ~60s hard limit — this was never going to fit there. |

The dashboard's "Refresh" button talks to Supabase directly (instant). Its
"Run live scrape" button calls GitHub's API to start the Actions workflow,
then polls Supabase's `scrape_runs` table until that workflow finishes and
pushes fresh rows — genuinely live, just not instant (a few minutes).

## Step 1 — Supabase project

1. Create a project at [supabase.com](https://supabase.com) (free tier is fine).
2. SQL Editor -> paste and run `etl-python/schema.sql` (creates `daily_index`,
   `route_daily_detail`, `scrape_runs`).
3. Then paste and run `airfare-dashboard/supabase-review-migration.sql`
   (adds the reviewer-signoff table).
4. Project Settings -> API -> copy the **Project URL** and the
   **service_role key** (not `anon`). You'll need both twice (Vercel and
   GitHub).

## Step 2 — Push this repo to GitHub

If it isn't already:
```
git init
git add .
git commit -m "SIH26056: index engine + Vercel + on-demand refresh"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

## Step 3 — GitHub Actions secrets (for the scheduled/triggered scraper)

Repo -> Settings -> Secrets and variables -> Actions -> New repository secret:

- `SUPABASE_URL` — same Project URL as above
- `SUPABASE_SERVICE_ROLE_KEY` — same service_role key as above

That's it for Actions — `.github/workflows/scrape.yml` is already committed
and will start running on its own nightly schedule (03:17 UTC) once these
two secrets exist.

## Step 4 — A GitHub token so the WEBSITE can trigger a scrape

The "Run live scrape" button needs permission to start that same workflow
from a Vercel API route:

1. GitHub -> Settings (your account, not the repo) -> Developer settings ->
   Personal access tokens -> **Fine-grained tokens** -> Generate new token.
2. Resource owner: you. Repository access: **only** this one repo.
3. Permissions -> Actions: **Read and write**. Nothing else needed.
4. Generate, copy the token once (starts `github_pat_...`).

## Step 5 — Deploy to Vercel

1. [vercel.com](https://vercel.com) -> New Project -> import this GitHub repo.
2. **Root Directory**: click Edit and set it to `airfare-dashboard` — this
   repo has three top-level folders and Vercel needs to know the Next.js
   app is the one nested inside. This is the one non-default setting the
   whole deploy depends on.
3. Framework preset should auto-detect as Next.js. Leave build/output
   settings default.
4. Environment Variables, add:

   | Key | Value |
   |---|---|
   | `SUPABASE_URL` | from Step 1 |
   | `SUPABASE_SERVICE_ROLE_KEY` | from Step 1 |
   | `GITHUB_TOKEN` | from Step 4 |
   | `GITHUB_REPO` | `<you>/<repo>` |

5. Deploy. A few minutes later you have a live URL.

Without Supabase configured, the site still deploys and works fine on
bundled sample data — Steps 1-4 aren't blocking, just what turns on real
numbers and the live-scrape button.

## Step 6 — Seed the first real data

The site has nothing in `daily_index` yet, so it'll show sample data until
one pipeline run completes. Two ways to trigger it:

**A. From GitHub** (recommended for the first run — you can watch the logs):
Repo -> Actions -> "Scrape airfares and update index" -> Run workflow ->
mode = `full` (all 325 routes; expect this to take a couple of hours given
the scraper's polite 4s-between-requests pacing — see `fare_scraper.py`'s
own reasoning for why it's deliberately not faster) -> Run workflow.

**B. From the deployed site**: click "Run live scrape" — this only ever
queues a `quick` (top-20) run, by design, so it finishes in minutes. Use
this for routine on-demand refreshes; use (A) for the first full-basket
seed and let the nightly schedule keep the full basket current after that.

## Step 7 — Verify

1. Open the deployed site. Once Step 6 finishes, reload — you should see a
   real index number, "Computed from N of 325 routes actually scraped
   today," and green dots on the routes with fresh data in the route table.
2. Click **Refresh** — should update instantly (reads Supabase, no scrape).
3. Click **Run live scrape** — should show "Scraping quick basket…", then
   "Done — N route(s) scraped" a few minutes later, then auto-refresh.
4. If "Run live scrape" says "not configured yet" — double check
   `GITHUB_TOKEN` / `GITHUB_REPO` are set in Vercel and redeploy (env var
   changes need a redeploy to take effect).

## Ongoing operation

- Nightly full scrape (325 routes) keeps the headline index current —
  no action needed once Steps 1-4 are done.
- The on-site button gives anyone an on-demand top-20 refresh without
  touching GitHub directly.
- Watch the first several full runs' Actions logs / uploaded
  `scrape_report.json` artifact for routes coming back empty — that's the
  real signal for whether Google Flights' shape holds up across the full
  325-route basket (see the caveat at the top of this guide), not
  something to assume is fine.
