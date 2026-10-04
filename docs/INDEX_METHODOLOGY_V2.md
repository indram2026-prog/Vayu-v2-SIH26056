# Index methodology v2 (additions)

These modules are additive. Nothing in the existing scrape -> normalise -> filter -> index pipeline imports them, so the scheduled run behaves exactly as before. They can be adopted one at a time.

## 1. Matched-model chained index (`scraper/chained_index.py`)

**Problem.** The current engine averages only the routes scraped on the day and renormalises their weights. When coverage changes between days the covered basket changes, so the headline moves because of composition and not prices.

**Fix.** Compare like with like. For consecutive observation dates, only items priced on both dates (the matched set) contribute to the day-over-day link, using a weighted geometric mean (the Jevons-type elementary formula used for CPI), and the links are chained from base 100:

    link_t = exp( sum w_i * ln(p_i,t / p_i,t-1) / sum w_i )     over matched i
    I_t    = I_(t-1) * link_t

An item can be a route (`DEL-BOM`) or a route at one lead window (`DEL-BOM|T+7`), so lead windows chain separately. Each point reports `matched_weight_pct`, and days with no overlap or too little coverage are carried forward and flagged rather than trusted. A test shows flat prices with a different subset scraped each day leave the index at exactly 100.

## 2. Lead-time curve (`scraper/lead_time.py`)

Lead days are derived from observation date and travel date, bucketed to the T+1, 7, 15, 30, 45 windows. Each route's price at a window is divided by its own price at the reference window (T+30), and the curve is the median across routes, which removes route-mix effects. `log_slope_per_day` gives the approximate percent fare change per extra advance-booking day.

Note: the scheduled run currently collects one lead window (T+21). The curve needs quotes at several windows.

## 3. Fare breakdown (`scraper/fare_components.py`, `etl-python/migrations/001_fare_components.sql`)

`FareBreakdown` holds total, base fare, taxes, user-development fee, convenience fee and other charges. Unknown parts stay `None`. Inconsistent breakdowns are rejected. `price_for("total" | "ex_convenience" | "base")` picks the price to index. The migration adds `fare_quotes` (with `lead_days` and the components) and `daily_index_chained`. It does not alter existing tables.

## 4. DGCA weights (`scraper/dgca_weights.py`)

    python -m scraper.dgca_weights dgca_traffic.csv

Reads a CSV you supply (`origin,destination,passengers`), combines both directions, and writes `shared/routes_dgca.json` without touching `routes.json`. Routes found in the file get weight proportional to passengers; the rest keep their gravity weight and their share; all weights still sum to 1. Each route records `weight_source`. No traffic numbers are included in the repo.

## 5. Back-test (`scraper/backtest.py`)

    python -m scraper.backtest index.csv dgca.csv

Inputs: `date,index_value` and `month,avg_fare` (YYYY-MM). Both are rebased to the first shared month. The report gives mean absolute error of the rebased levels, correlation (3+ months), month-over-month direction agreement, and whether 30 days of index data exist. With one shared month it says so and reports no statistic. No DGCA numbers are included.

## Honest limits

- Needs data you supply: DGCA traffic and DGCA monthly average fares.
- The back-test needs a daily index history of 30 or more days; DGCA is monthly, so a meaningful comparison needs at least two months.
- Base prices in the current index are still modelled; the chained index avoids relying on them for day-to-day change.
