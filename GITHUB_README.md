# Boat Search — Price Tracker

A self-updating price tracker for used **ocean-fishing boats** for sale in Southern California. It scans listings daily, records every price observation, flags new boats and price changes, fits a simple fair-value model, and renders an interactive dashboard.

**Search criteria:** 20–30 ft · ≤ $60,000 · ocean-fishing types (center consoles, walkarounds, cuddy/pilothouse/sportfishers, pangas, power cats, and known offshore brands) · San Diego / Orange County / LA / Inland Empire.

---

## Features

- Daily scan of San Diego Craigslist (and optionally BoatTrader / BoatMart when a browser extension is connected).
- Stable per-listing IDs so the same boat is tracked across days, building real price history.
- Automatic flagging of **new** listings, **price drops/rises**, and **gone/sold?** boats (not seen for 14+ days).
- A fair-value model (regression of log price on year + length) that highlights boats priced 15%+ under expected.
- A single self-contained `dashboard.html` — sortable, searchable, with price-history sparklines and scatter charts. No server required; open it in any browser.

---

## Repository structure

```
.
├── dashboard.html              # Generated dashboard — open in a browser
├── README.md                   # This file
└── boat_tracker/
    ├── config.json             # Search settings (region, price cap, length range, URLs)
    ├── listings.json           # Master database: one record per boat, with full price history
    ├── price_log.csv           # Flat append-only log of every price observation (opens in Excel)
    ├── new_scan.json           # The latest scan's raw results (input to the merge step)
    └── update_listings.py      # Merge script: updates DB, logs prices, rebuilds dashboard
```

---

## Requirements

- Python 3.8+
- No third-party packages required for the merge script (standard library only).

---

## How a scan works

Each daily run performs these steps:

1. **Fetch** the configured Craigslist search results.
2. **Filter** to qualifying ocean-fishing boats (by type/brand, length, price, and location), inferring length and year from titles/model numbers (e.g. `Trophy 2352` → 23.5 ft, `Parker 2310` → 23 ft).
3. **Write** the qualifying listings to `boat_tracker/new_scan.json` as an array of objects:

   ```json
   {
     "id": "cl-7937269874",
     "source": "craigslist",
     "title": "2002 Striper Fishing boat",
     "price": 48000,
     "location": "Marina Del Rey",
     "url": "https://sandiego.craigslist.org/...",
     "length_ft": 20.0,
     "year": 2002
   }
   ```

   IDs are stable: `cl-` + the numeric Craigslist post ID (`bt-` / `bm-` for BoatTrader / BoatMart).

4. **Merge** by running the update script:

   ```bash
   python3 boat_tracker/update_listings.py
   ```

   This updates `listings.json`, appends to `price_log.csv`, recomputes the fair-value model, and rebuilds `dashboard.html`. It prints a one-line summary, e.g.:

   ```
   Scan 2026-06-16: 74 scanned | 0 new | 0 price changes | 82 active | 82 total tracked
   ```

---

## Configuration

Edit `boat_tracker/config.json` to change the search:

| Key | Meaning |
| --- | --- |
| `craigslist_url` | Search URL to scan |
| `min_length_ft` / `max_length_ft` | Length bounds (ft) |
| `max_price` | Price cap (USD) |
| `area` | Human-readable target region |
| `stale_days` | Days without being seen before a listing is marked `gone` (default 14) |

---

## Data model

Each record in `listings.json`:

| Field | Description |
| --- | --- |
| `id` | Stable unique ID |
| `source` | `craigslist` / `boattrader` / `boatmart` |
| `title`, `location`, `url` | Listing details |
| `length_ft`, `year` | Inferred specs (`null` if unknown) |
| `first_seen`, `last_seen` | Dates (ISO) |
| `price_history` | Array of `{date, price}` observations |
| `status` | `new` / `active` / `rise` / `drop` / `gone` |
| `expected_price`, `value_pct`, `price_pctile` | Fair-value model outputs |

---

## Fair-value model

For boats with both a known year and length, the script fits an ordinary least-squares regression of `log(price)` on `year` and `length_ft` across the active fleet, then reports each boat's `expected_price` and `value_pct` (percent above/below expected). Boats 15%+ under expected are surfaced as "good deals." Boats missing year or length fall back to a simple fleet price percentile.

> The model is a rough heuristic on a small sample — it does not account for condition, hours, engine, electronics, or trailer. Treat it as a sorting aid, not an appraisal.

---

## Running manually

```bash
# 1. Produce boat_tracker/new_scan.json (from your scan step)
# 2. Merge + rebuild the dashboard
python3 boat_tracker/update_listings.py
# 3. Open dashboard.html in a browser
```

---

## Notes & limitations

- BoatTrader and BoatMart block direct fetching, so they are only scanned when a browser automation extension is connected; otherwise those sources are skipped for that run.
- Craigslist occasionally serves a slightly stale cached page; a listing missed on one run is simply not re-confirmed that day and ages out only after `stale_days`.
- Listing prices are seller asking prices, not sale prices.
