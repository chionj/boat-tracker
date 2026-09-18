#!/usr/bin/env python3
"""Fetch the latest Craigslist boat listings and write boat_tracker/new_scan.json.

This restores the missing internet fetch step that the project expects before
merging listings into the tracking database.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

HERE = Path(__file__).resolve().parent
SCAN_PATH = HERE / "new_scan.json"
CONFIG_PATH = HERE / "config.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def extract_listing_id(url: str) -> str:
    try:
        path = urlparse(url).path
    except Exception:
        return ""
    m = re.search(r"/([0-9]{8,})\.html$|/([0-9]{8,})/?$|/([A-Za-z0-9]+)$", path)
    if not m:
        return ""
    return next(g for g in m.groups() if g)


def normalize_price(raw: str) -> int | None:
    if raw is None:
        return None
    digits = re.sub(r"[^0-9]", "", raw)
    if not digits:
        return None
    return int(digits)


def infer_year(title: str) -> int | None:
    m = re.search(r"\b(19[0-9]{2}|20[0-9]{2}|21[0-9]{2})\b", title or "")
    if not m:
        return None
    year = int(m.group(1))
    if 1950 <= year <= 2035:
        return year
    return None


def infer_length(title: str, fallback: str | None = None) -> float | None:
    text = (title + " " + (fallback or "")).strip()
    m = re.search(r"(\d{2,3}(?:\.\d+)?)\s*(?:ft|'|feet|foot|FT)", text, re.I)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d{2,3}(?:\.\d+)?)\s*(?:\"|in\s*length)", text, re.I)
    if m:
        return float(m.group(1)) / 12.0
    return None


def parse_cl_results(html: str) -> list[dict[str, Any]]:
    rows = re.findall(r'<li[^>]*class="[^"]*result-row[^"]*"[^>]*>(.*?)</li>', html, re.S | re.I)
    items: list[dict[str, Any]] = []
    for row in rows:
        if "result-info" not in row:
            continue
        href_match = re.search(r'<a[^>]*href="([^"]+)"[^>]*class="[^"]*result-title[^"]*"[^>]*>(.*?)</a>', row, re.S | re.I)
        if not href_match:
            href_match = re.search(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', row, re.S | re.I)
        if not href_match:
            continue
        url = href_match.group(1).strip()
        title = re.sub(r"<.*?>", "", href_match.group(2)).strip()
        if not title:
            continue
        price = None
        m = re.search(r'<span[^>]*class="[^"]*result-price[^"]*"[^>]*>(.*?)</span>', row, re.S | re.I)
        if m:
            price_text = re.sub(r"<.*?>", "", m.group(1)).strip()
            price = normalize_price(price_text)
        location = ""
        m = re.search(r'<span[^>]*class="[^"]*result-hood[^"]*"[^>]*>(.*?)</span>', row, re.S | re.I)
        if m:
            location = re.sub(r"<.*?>", "", m.group(1)).strip().strip("() ")
        item_id = f"cl-{extract_listing_id(url)}"
        if not item_id.endswith("-") and item_id != "cl-":
            items.append(
                {
                    "id": item_id,
                    "source": "craigslist",
                    "title": title,
                    "price": price,
                    "location": location,
                    "url": url,
                    "length_ft": infer_length(title),
                    "year": infer_year(title),
                }
            )
    # de-dupe by id
    dedup: dict[str, dict[str, Any]] = {}
    for item in items:
        dedup.setdefault(item["id"], item)
    return list(dedup.values())


def fetch_craigslist() -> list[dict[str, Any]]:
    cfg = load_config()
    url = cfg.get("craigslist_url") or "https://sandiego.craigslist.org/search/boo?min_price=3000&max_price=60000"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    html = resp.text
    return parse_cl_results(html)


def main() -> None:
    try:
        listings = fetch_craigslist()
    except Exception as exc:  # pragma: no cover - explicit user-facing failure
        raise SystemExit(f"Failed to fetch Craigslist listings: {exc}")

    with SCAN_PATH.open("w", encoding="utf-8") as f:
        json.dump(listings, f, indent=2)

    print(f"Fetched {len(listings)} Craigslist listings -> {SCAN_PATH}")


if __name__ == "__main__":
    main()
