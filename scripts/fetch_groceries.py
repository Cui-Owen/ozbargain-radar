#!/usr/bin/env python3
"""
OzBargain Grocery & Supermarket Specials Fetcher
Fetches and aggregates Coles, Woolworths, and Groceries deals,
identifies half-price specials, and calculates unit pricing.
"""
import argparse
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from deal_status import deal_status

try:
    from price_inspector import inspect_deal_pricing
except ImportError:
    from scripts.price_inspector import inspect_deal_pricing

GROCERY_FEEDS = [
    ("https://www.ozbargain.com.au/deals/coles.com.au/feed", "Coles"),
    ("https://www.ozbargain.com.au/deals/woolworths.com.au/feed", "Woolworths"),
    ("https://www.ozbargain.com.au/cat/groceries/feed", "General"),
]

OZB_NS = "{https://www.ozbargain.com.au}"

def clean_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    text = re.sub(r'<[^>]+>', ' ', raw_html)
    text = html.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()

def detect_store(title: str, default_store: str = "General") -> str:
    lower_t = title.lower()
    if "@ coles" in lower_t or "coles online" in lower_t or "coles" in lower_t:
        return "Coles"
    if "@ woolworths" in lower_t or "woolworths" in lower_t or "everyday rewards" in lower_t:
        return "Woolworths"
    if "@ amazon" in lower_t or "amazon au" in lower_t:
        return "Amazon AU"
    if "@ aldi" in lower_t or "aldi" in lower_t:
        return "ALDI"
    if "@ iga" in lower_t or "iga" in lower_t:
        return "IGA"
    return default_store

def estimate_unit_price(title: str) -> str:
    """
    Attempts to calculate unit price based on price and weight/quantity in the title.
    Example: 'KB\'s Raw Prawns Tail On Large 500g $12.00' -> '$24.00/kg'
    """
    price_match = re.search(r'\$(\d+(?:\.\d{1,2})?)', title)
    if not price_match:
        return ""
    
    price = float(price_match.group(1))
    if re.search(r"\b\d+\s*[x×]\s*\d", title, re.IGNORECASE):
        return ""

    # Weight in grams (e.g., 500g, 250g)
    g_match = re.search(r'(\d+(?:\.\d+)?)\s*g\b', title, re.IGNORECASE)
    if g_match:
        grams = float(g_match.group(1))
        if grams > 0:
            price_per_kg = (price / grams) * 1000
            return f"${price_per_kg:.2f}/kg"

    # Weight in kg (e.g., 1.5kg, 2kg)
    kg_match = re.search(r'(\d+(?:\.\d+)?)\s*kg\b', title, re.IGNORECASE)
    if kg_match:
        kg = float(kg_match.group(1))
        if kg > 0:
            price_per_kg = price / kg
            return f"${price_per_kg:.2f}/kg"

    # Volume in ml
    ml_match = re.search(r'(\d+(?:\.\d+)?)\s*ml\b', title, re.IGNORECASE)
    if ml_match:
        ml = float(ml_match.group(1))
        if ml > 0:
            price_per_l = (price / ml) * 1000
            return f"${price_per_l:.2f}/L"

    # Volume in L
    l_match = re.search(r'(\d+(?:\.\d+)?)\s*l\b', title, re.IGNORECASE)
    if l_match:
        litres = float(l_match.group(1))
        if litres > 0:
            price_per_l = price / litres
            return f"${price_per_l:.2f}/L"

    # Rolls or packs (e.g., 48 rolls, 12pk)
    pack_match = re.search(r'(\d+)\s*(?:rolls?|pk|pack|cans)\b', title, re.IGNORECASE)
    if pack_match:
        qty = float(pack_match.group(1))
        if qty > 0:
            price_per_unit = price / qty
            return f"${price_per_unit:.2f}/unit"

    return ""

def fetch_groceries(store_filter="all", only_half_price=False, min_votes=None, limit=0):
    if limit < 0:
        raise ValueError("limit must be 0 (all returned RSS items) or positive")
    now = datetime.now(timezone.utc)
    seen_ids = set()
    items = []
    successful_feeds = 0

    for feed_url, feed_store in GROCERY_FEEDS:
        try:
            req = urllib.request.Request(
                feed_url,
                headers={"User-Agent": "Mozilla/5.0 (OzBargainRadar/1.0)"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                xml_data = resp.read()
            root = ET.fromstring(xml_data)
            successful_feeds += 1
        except Exception as e:
            print(f"Unable to read RSS {feed_url}: {e}", file=sys.stderr)
            continue

        for item in root.findall(".//item"):
            link = item.findtext("link", "").strip()
            node_id_m = re.search(r'/node/(\d+)', link)
            node_id = node_id_m.group(1) if node_id_m else link

            if node_id in seen_ids:
                continue
            seen_ids.add(node_id)

            title = item.findtext("title", "").strip()
            pub_date = item.findtext("pubDate", "").strip()
            raw_desc = item.findtext("description", "")
            desc_clean = clean_html(raw_desc)

            meta_elem = item.find(f"{OZB_NS}meta")
            votes_pos = 0
            votes_neg = 0
            expiry_str = None
            merchant_url = None
            comment_count = 0

            if meta_elem is not None:
                votes_pos = int(meta_elem.attrib.get("votes-pos", 0))
                votes_neg = int(meta_elem.attrib.get("votes-neg", 0))
                expiry_str = meta_elem.attrib.get("expiry")
                merchant_url = meta_elem.attrib.get("url")
                comment_count = int(meta_elem.attrib.get("comment-count", 0))

            net_votes = votes_pos - votes_neg

            if min_votes is not None and net_votes < min_votes:
                continue

            status = deal_status(meta_elem.attrib if meta_elem is not None else {}, title, now)
            if status in ("expired", "out_of_stock", "upcoming"):
                continue

            store = detect_store(title, feed_store)

            # Store filter
            if store_filter != "all":
                if store_filter.lower() not in store.lower():
                    continue

            # Check half price
            pricing_info = inspect_deal_pricing(title, desc_clean, merchant_url or "")
            is_half = pricing_info["is_half_price"]

            if only_half_price and not is_half:
                continue

            unit_price = estimate_unit_price(title)

            items.append({
                "node_id": node_id,
                "title": title,
                "store": store,
                "is_half_price": is_half,
                "unit_price_estimate": unit_price,
                "link": link,
                "merchant_url": merchant_url,
                "net_votes": net_votes,
                "published": pub_date,
                "comment_count": comment_count,
                "expiry": expiry_str,
                "status": status,
                "price_intelligence": pricing_info,
                "snippet": desc_clean[:180] + ("..." if len(desc_clean) > 180 else "")
            })

            if limit and len(items) >= limit:
                break

        if limit and len(items) >= limit:
            break

    if successful_feeds == 0:
        raise RuntimeError("No grocery RSS sources could be read")

    # Sort items: Half-price items with higher votes first
    items.sort(key=lambda x: (x["is_half_price"], x["net_votes"]), reverse=True)
    return items

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Fetch Coles & Woolies Grocery Specials")
    parser.add_argument("--store", default="all", help="all, coles, woolworths, amazon")
    parser.add_argument("--half-price-only", action="store_true", help="Only half-price specials")
    parser.add_argument("--min-votes", type=int, default=None, help="Minimum net positive votes (default: no threshold)")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of items; 0 (default) includes all returned RSS items")
    args = parser.parse_args()

    results = fetch_groceries(
        store_filter=args.store,
        only_half_price=args.half_price_only,
        min_votes=args.min_votes,
        limit=args.limit
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))
