# Vayu: India Real-Time Airfare Price Index

SIH 2026, Problem Statement SIH26056, Team ByteBrigade.

Vayu is a daily, route-level airfare index for 325 Indian domestic routes (all pairs across 26 major airports). A scheduled pipeline collects fares, filters anomalies, computes a weighted index and publishes it to a public dashboard.

- Live dashboard: https://vayu-v2-sih-26056-phi.vercel.app/
- Supporting documents (methodology, architecture, test evidence, sources): https://drive.google.com/drive/folders/1W08H-hPXIVdFnE4K7pouNTne93_iXziN?usp=sharing

## Status and known limitations

This is a working prototype. Read these before interpreting the numbers.

- **Reference prices are modelled, not surveyed.** Each route's base price is a formula (Rs 2,200 + Rs 3.6 per km, with a small route-specific factor). The index level is therefore not inflation since the base date. Day-to-day change is the meaningful signal.
- **Basket weights are illustrative.** A gravity model with placeholder airport traffic masses, not DGCA data.
- **One source, one window.** The scheduled run uses Google Flights for departures 21 days ahead. IndiGo and Air India parsers exist and are tested on real captured responses, but are not in the scheduled run.
- **Coverage varies by run.** The index is computed only from routes scraped and accepted that day, renormalised, and the covered share of basket weight is shown beside the index.

See the methodology note for detail.

## How it works

scrape -> normalise (median fare per route) -> anomaly filter -> index -> Supabase -> dashboard

    index = 100 x SUM(w_i x price_i / base_price_i) / SUM(w_i)

The sums run over routes with fresh, accepted data on that day.

## Repository layout

    etl-python/scraper/     scraper, parsers, normalise, anomaly filter, index engine, tests
    etl-python/schema.sql   database schema (Supabase / PostgreSQL)
    shared/                 route basket generator and routes.json (325 routes)
    airfare-dashboard/      Next.js dashboard (Vercel)
    .github/workflows/      scheduled and on-demand scrape workflow
    docs/                   supporting documents

## Run the tests

    cd etl-python
    pip install -r scraper/requirements.txt
    python -m unittest discover -s scraper/tests -t .

## Run the dashboard locally

    cd airfare-dashboard
    npm install
    npm run dev

With no environment variables it runs on bundled sample data. Set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` for live figures. See `.env.example`. Never commit real keys or tokens.

## Run the pipeline

    cd etl-python
    python -m scraper.run_pipeline --target google_flights --top 20 --dry-run

`--dry-run` never writes to the database.

## Documents

Also in the `docs/` folder: methodology, architecture and data model, verification and test evidence, roadmap, sources, and the 325-route basket (CSV).

