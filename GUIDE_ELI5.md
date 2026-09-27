# SIH26056 — ELI5 Guide: The Scrapling Scraper (now 2-for-4 airlines)

This guide explains, in plain words, what's in this zip and exactly what
buttons to press to try it. It assumes zero background — if you know what
a terminal is, you're already ahead.

---

## 1. What even is "Scrapling"? (the 5-year-old version)

Imagine you send a robot to a website to copy down flight prices for you,
the way you'd send a kid to read prices off a shop's price board.

- **A normal scraper** memorizes exactly *where* the price is written on
  the board — "3rd line, red text." The day the shop repaints the board
  and moves things around, the kid keeps staring at the same empty spot
  and reports nothing.
- **Scrapling** is a kid who remembers *what a price looks like* (a number,
  near a currency symbol, next to an airline logo), not just its exact
  position. If the board gets repainted, the kid still finds the price by
  recognizing it, not by its old coordinates.

Scrapling also knows how to sneak past bouncers (the anti-bot walls sites
like Cloudflare put up) and — the clever trick we're using here — it can
peek at the note the website's own app writes for itself before drawing
the page. Most modern websites don't hand-draw prices; they fetch a small
JSON "note" with the numbers, then draw the page from that note. Reading
the note directly is more reliable than reading the drawing.

## 2. What changed since last time, in one paragraph

Last round, the scraper was freshly rebuilt on Scrapling but had never
touched a real website — everything was reviewed code, zero live proof.
Since then, two airlines went from "guess" to "we have actually seen the
real numbers": **IndiGo** (verified first, via a live Scrapling run on
your machine) and now **Air India** (verified this round, via you manually
hunting through Chrome's Network tab and pasting the real response back).
Both real captures turned into a dedicated parser, a real test fixture,
and passing tests — not just a hope that the generic parser would cope.
SpiceJet and Akasa are still unverified guesses, same as before.

## 3. What's actually in the box

```
sih26056-updates/
  shared/                    <- unchanged: the 325-route basket
  airfare-dashboard/         <- unchanged: the Next.js demo site
  etl-python/
    route_weights.py         <- unchanged
    scraper/
      models.py                        <- the shape one scraped fare takes
      xhr_parser.py                    <- reads a site's own JSON "note" (§1 above)
                                           now has 3 parsers: generic heuristic,
                                           IndiGo fare-radar, Air India air-bounds
      html_parser.py                   <- fallback: reads the drawn page directly
      targets.py                       <- which sites, which patterns to look for
      fare_scraper.py                  <- runs the whole scrape, retries, rate-limits
      run_scraper.py                   <- the command you actually type
      requirements.txt
      tests/
        test_models.py                 <- unchanged
        test_xhr_parser.py             <- unchanged
        test_indigo_fare_radar.py      <- unchanged
        test_airindia_air_bounds.py    <- NEW — 8 tests against real Air India data
        fixtures/
          real_indigo_fare_radar_...json
          real_airindia_air_bounds_...json  <- NEW — real captured response
```

## 4. How we actually found these two real endpoints (do this yourself for SpiceJet/Akasa)

This is the exact click-by-click recipe that found both IndiGo's and Air
India's real data. It works because almost every modern airline site is
secretly a "fetch a small JSON note, then draw the page from it" app (§1) —
you just have to catch the note.

1. Go to the airline's website and open **Chrome DevTools** (right-click →
   "Inspect", or F12).
2. Click the **Network** tab, then make sure it's recording (a red dot,
   usually on by default).
3. Do one real, normal search — pick any two cities and a date, click
   Search — the way an actual customer would.
4. The Network tab now fills up with anywhere from 50 to 300+ requests.
   Don't open them one by one — that's what took forever the first time.
   Instead, click the little **search icon (🔍)** in the Network panel's
   toolbar (it sits right next to the filter funnel icon). This opens a
   box that searches the *contents* of every response, not just the
   request names.
5. Type something you can actually see on the results page — a fare
   number, like `6423` if the screen shows "₹6,423" somewhere. Hit enter.
6. Chrome now shows you only the handful of requests whose response
   actually contains that number. That's almost always the real one — out
   of hundreds of requests, you now have 1-3 real candidates.
7. Click one, then its **Response** or **Preview** tab to see the real
   JSON. Click **Headers** to copy the full request URL (you'll need it to
   tell Scrapling's `capture_xhr` what pattern to look for).
8. Send both — the response JSON and the URL — back to me (or, if you're
   doing this yourself, paste them straight into `targets.py`'s
   `xhr_pattern` and a new fixture file next to
   `real_airindia_air_bounds_2026-09-27.json`).

That's genuinely the whole trick. No special tools, no reverse-engineering
minified JavaScript — just knowing where to look and how to search inside
what you find.

## 5. What's proven to work right now, vs. what still needs your machine

Same rule as always: I say what I actually checked, not what I hope is
true.

| Piece | Status |
|---|---|
| `models.py`, `xhr_parser.py` (all 3 parsers) | ✅ 32 automated tests in this sandbox, all pass. |
| IndiGo (`indigo` target) | ✅✅ Fully verified — real JSON captured **and** a live Scrapling run on your machine actually caught it (`fares_found=6`, all real). |
| Air India (`air_india` target) | ✅⚠️ Real JSON captured and parsed correctly (8 passing tests against the real response) — but a live Scrapling run against the real site has **not** been done yet. Very likely to work (same single-airline-site pattern as IndiGo), but "very likely" isn't "confirmed." |
| SpiceJet, Akasa | ❌ Still pure guesses — nobody's done the §4 hunt on these sites yet. |
| MakeMyTrip | 🚫 Confirmed actively blocked (bot defense) — deprioritized, see `CHANGES.md`. |
| `run_scraper.py` argument parsing, route selection | ✅ Runs cleanly with zero `scrapling` installed, picks correct routes from the real 325-route file. |

## 6. Step by step: try it on your own machine

### Step 1 — Get the code onto your computer
Unzip this file into your project folder, next to your existing
`airfare-dashboard/` and `shared/` folders (`shared/` and `etl-python/`
must be siblings — see `CHANGES.md` for why).

### Step 2 — Check you have Python
```
python3 --version
```
You need 3.9 or newer. If that command fails, install Python from
[python.org](https://python.org) first.

### Step 3 — Install Scrapling
```
cd etl-python/scraper
pip install -r requirements.txt
scrapling install
```
That last command is one-time — it downloads a real Chromium browser for
Scrapling to drive. It needs internet access and a few minutes.

### Step 4 — Run the automated tests first (safe, no internet needed)
```
cd ..
python3 -m unittest scraper.tests.test_xhr_parser scraper.tests.test_models scraper.tests.test_indigo_fare_radar scraper.tests.test_airindia_air_bounds -v
```
You should see `OK` at the bottom with **32 tests** passed. This checks
all three "reading the JSON note" parsers without touching the internet
at all — if this fails on your machine, something's wrong with the Python
environment, not with the scraper's understanding of any website.

### Step 5 — Run a real scrape against the verified targets
IndiGo (already confirmed end-to-end):
```
python3 -m scraper.run_scraper --target indigo --routes DEL-BOM
```
Air India (real data confirmed, but this specific live-capture step is
the untested part — this run either confirms it works or tells us exactly
what to fix):
```
python3 -m scraper.run_scraper --target air_india --routes DEL-BOM
```
Watch the terminal. It will either:
- **Find fares** → check `fares_out.jsonl` (one fare per line, readable
  JSON) — and if Air India works, that target can be marked fully
  verified just like IndiGo.
- **Find nothing** → check `scrape_report.json` and any
  `debug_air_india_DEL-BOM.html`/`.diag.txt` files written alongside it.
  Send me those and I'll fix `targets.py`'s pattern, not guess again —
  most likely fix is the `xhr_pattern` needing to be widened back if the
  narrowed one doesn't fire.

### Step 6 — Scale up once a target works
```
python3 -m scraper.run_scraper --target indigo --top 20
```
This scrapes the 20 highest-weight routes instead of the whole 325 —
kinder to the website and to you while you're still trusting the numbers.

### Step 7 — Try the §4 hunt yourself on SpiceJet or Akasa
This is genuinely the most useful next thing you can do: repeat the
DevTools recipe in §4 above on `spicejet.com` or `akasaair.com`. Send me
whatever JSON and URL turns up (even if you're not sure it's the right
one) and I'll write the dedicated parser + tests the same way this round
did for Air India.

## 7. "What do the automated tests actually check?"

**The original heuristic-parser tests** feed a fake (but realistic) JSON
note with a duplicate flight, a fare written as `"₹7,540"`, a mislabeled
baggage-weight field, and an unrealistic ₹45 "fare," and check the parser
correctly reads the currency string, dedupes the duplicate, and throws out
the two fakes.

**The IndiGo tests** run against the real captured `fare-radar` response
and check the 6 real destinations, real fares, and the real (surprising!)
fact that IndiGo's `travelDate` field ignored the date actually requested.

**The new Air India tests** run against a trimmed copy of the real
`air-bounds` response and check two things that are genuinely tricky
about this specific site, explained simply:

1. **One flight, many price tags.** Air India doesn't show you one fare
   per flight — it shows Economy Saver, Economy Flex, Premium Economy,
   and Business as separate real bookable prices for the *same* flight,
   sometimes 8 of them at once. A parser that only grabbed "the first
   price it saw" would throw away 7 real, correct fares per flight. The
   test checks that all of them come through.
2. **Mumbai has two airports, real ones.** The response includes flights
   landing at both "BOM" (the main Mumbai airport) and "NMI" (Navi
   Mumbai's newer airport) — but both are still just "a flight to
   Mumbai." The test checks the parser correctly treats both as the same
   `DEL-BOM` route instead of accidentally inventing a "DEL-NMI" route
   that doesn't exist anywhere else in the whole project.

Running these caught real, useful facts before they became bugs — not
hypothetical ones. See `CHANGES.md` §6 and §8 for the full technical
write-ups if you want them.

## 8. If someone asks "does this really pull live fares?"

Honest answer, same policy as always: the pipeline math (routes, weights,
index, dashboard) is real and demoed on computed numbers. For the scraper
specifically: **IndiGo is the one target proven start-to-finish** — real
site, real Scrapling run, real fares landed in a file. **Air India has
real, verified data and a parser proven against it**, but the
"Scrapling-actually-hits-the-live-site" step for this specific target
hasn't happened yet — that's Step 5 above, waiting on a real run.
SpiceJet, Akasa, and MakeMyTrip remain exactly what they were: an
untested guess, an untested guess, and a confirmed dead end, respectively.

## 9. If it breaks on Step 5

Send me:
1. The exact command you ran.
2. The contents of `scrape_report.json`.
3. Any `debug_*.html` / `debug_*.diag.txt` files it wrote.
4. Any error text printed in the terminal.

That's normally a five-minute fix (usually: the site's real request path
or JSON field names differ slightly from what's in `targets.py`), not a
redo — exactly what happened when the IndiGo pattern first needed
narrowing, and the same fix this round narrowed Air India's pattern too.
