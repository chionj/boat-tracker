# Boat Search — Price Tracker

Tracks 20–30 ft ocean fishing boats under $60k around San Diego, CA.

## Files

- **dashboard.html** — open this in your browser. Sortable/searchable table of every tracked boat with current price, price change since first seen, price history sparkline, and status (new / price drop / gone-sold?). Regenerated on every scan.
- **boat_tracker/listings.json** — master database with full price history per boat.
- **boat_tracker/price_log.csv** — flat log of every price observation (opens in Excel).
- **boat_tracker/config.json** — search settings (region, price cap, length range, search URLs). Edit to change criteria.
- **boat_tracker/update_listings.py** — merge script run by each scan.

## How it updates

A scheduled task runs daily at 8 AM (while the Claude app is open; if closed, it runs on next launch). Each run:

1. Searches San Diego Craigslist (always works).
2. Searches BoatTrader and BoatMart via the Chrome browser extension — these sites block direct fetching, so they're only scanned when Chrome with the Claude extension is connected. Otherwise they're skipped that day.
3. Logs prices, flags new listings and price changes, and rebuilds the dashboard.

Boats not seen for 14+ days are marked "gone/sold?".
