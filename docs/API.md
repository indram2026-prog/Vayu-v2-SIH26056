# API reference

One public, read-only endpoint is deployed with the dashboard.

## GET /api/index-data

Returns the airfare index series and the latest per-route detail.

Query parameters

| Name | Meaning |
|---|---|
| `fresh=1` | Bypass the 5-minute cache (used by the dashboard Refresh button). |

Response (`IndexPayload`)

| Field | Type | Meaning |
|---|---|---|
| `index_timeseries` | array of `{observation_date, index_value, base_date}` | Daily index. |
| `latest_date` | string | Most recent observation date. |
| `route_detail_latest` | array | Per route: `route_id`, `weight`, `latest_price`, `price_relative`, `source` (`scraped` or `sample`), `airlines`, `origin_name`, `destination_name`. `base_price` is null on the live path. |
| `data_quality` | object | Currently the bundled sample values. |
| `reviewed_dates` | string[] | Dates an analyst has signed off. |
| `served_from` | `supabase` or `sample` | Live data or the built-in fallback. |
| `coverage_weight_pct` | number | Share of basket weight in the latest day's index from freshly scraped routes. |
| `routes_used`, `routes_total` | number | Routes counted vs routes in the basket. |

Caching: `Cache-Control: public, s-maxage=300, stale-while-revalidate=600`; `no-store` with `fresh=1`; a shorter TTL when serving the sample fallback.

## Known gaps for NSO/RBI consumption

- No authentication or API keys; the data is public.
- No versioned path (for example `/api/v1/...`) or date-range filter.
- No endpoint for the chained index, lead-time curve or fare components yet; the tables for them are in `etl-python/migrations/001_fare_components.sql`.
- Always check `served_from`: `sample` means the figures are not live.
