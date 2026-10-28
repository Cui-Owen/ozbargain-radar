#!/usr/bin/env python3
"""
OzBargain Deal Fetcher
Pulls deals from OzBargain RSS feeds, evaluates net votes, checks expiry,
and enriches each deal with price intelligence.
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

CATEGORIES = {
    "computing": "computing",
    "pc": "computing",
    "electronics": "electrical-electronics",
    "electrical-electronics": "electrical-electronics",
    "gaming": "gaming",
    "games": "gaming",
    "groceries": "groceries",
    "supermarket": "groceries",
    "fashion": "fashion-apparel",
    "apparel": "fashion-apparel",
    "clothing": "fashion-apparel",
    "fashion-apparel": "fashion-apparel",
    "home": "home-garden",
    "garden": "home-garden",
    "home-garden": "home-garden",
    "mobile": "mobile",
    "phones": "mobile",
    "internet": "internet",
    "broadband": "internet",
    "automotive": "automotive",
    "auto": "automotive",
    "cars": "automotive",
    "entertainment": "entertainment",
    "dining": "dining-takeaway",
    "takeaway": "dining-takeaway",
    "food": "dining-takeaway",
    "dining-takeaway": "dining-takeaway",
    "travel": "travel",
    "flights": "travel",
    "other": "other",
}

CORE_CATEGORIES = [
    "computing",
    "electrical-electronics",
    "gaming",
    "groceries",
    "fashion-apparel",
    "home-garden",
    "mobile",
    "internet",
    "automotive",
    "entertainment",
    "dining-takeaway",
    "travel",
    "other"
]

OZB_NS = "{https://www.ozbargain.com.au}"

def clean_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    text = re.sub(r'<[^>]+>', ' ', raw_html)
    text = html.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()

def extract_node_id(link: str) -> str:
    m = re.search(r'/node/(\d+)', link)
    return m.group(1) if m else ""

def resolve_feed_url(feed_key: str, mode: str = "latest") -> str:
    if feed_key.startswith("http://") or feed_key.startswith("https://"):
        return feed_key
    
    feed_clean = feed_key.lower().strip()

    # All-deals site-wide
    if feed_clean in ("all", "deals", "latest"):
        if mode == "popular":
            return "https://www.ozbargain.com.au/feed"
        return "https://www.ozbargain.com.au/deals/feed"
    
    if feed_clean == "popular":
        return "https://www.ozbargain.com.au/feed"

    # Category matching
    slug = CATEGORIES.get(feed_clean, feed_clean)
    if mode == "popular":
        return f"https://www.ozbargain.com.au/cat/{slug}/feed"
    else:
        # Default latest mode uses /deals/feed for the category (chronological real-time stream)
        return f"https://www.ozbargain.com.au/cat/{slug}/deals/feed"

def is_supermarket_half_price(title, merchant_url=""):
    store = re.search(r"\b(coles|woolworths|woolies|wws)\b", title + " " + merchant_url, re.I)
    half_price = re.search(r"half[\s-]*price|half[\s-]*off|(?:1/2|½)[\s-]*price|50\s*%\s*(?:off|discount)|半价", title, re.I)
    return bool(store and half_price)


def fetch_feed_deals(url: str, min_votes=None, limit: int = 0, only_active: bool = True, atl_only: bool = False, exclude_supermarket_half_price: bool = False):
    if limit < 0:
        raise ValueError("limit must be 0 (all returned RSS items) or positive")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) OzBargainRadar/1.1"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            xml_data = response.read()
    except Exception as e:
        raise RuntimeError(f"Unable to read RSS {url}: {e}") from e

    root = ET.fromstring(xml_data)
    now = datetime.now(timezone.utc)
    results = []

    for item in root.findall(".//item"):
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        pub_date = item.findtext("pubDate", "").strip()
        raw_desc = item.findtext("description", "")
        desc_clean = clean_html(raw_desc)
        node_id = extract_node_id(link)

        categories = [elem.text for elem in item.findall("category") if elem.text]
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

        # 1. Minimum net votes filter
        if min_votes is not None and net_votes < min_votes:
            continue

        if exclude_supermarket_half_price and is_supermarket_half_price(title, merchant_url or ""):
            continue

        status = deal_status(meta_elem.attrib if meta_elem is not None else {}, title, now)
        is_expired = status in ("expired", "out_of_stock")
        if only_active and status in ("expired", "out_of_stock", "upcoming"):
            continue

        # 3. Price History Intelligence
        pricing_info = inspect_deal_pricing(title, desc_clean, merchant_url or "")

        if atl_only and not pricing_info["is_atl"]:
            continue

        results.append({
            "node_id": node_id,
            "title": title,
            "link": link,
            "merchant_url": merchant_url,
            "net_votes": net_votes,
            "votes_pos": votes_pos,
            "votes_neg": votes_neg,
            "comment_count": comment_count,
            "categories": categories,
            "expiry": expiry_str,
            "is_expired": is_expired,
            "status": status,
            "published": pub_date,
            "description_snippet": desc_clean[:220] + ("..." if len(desc_clean) > 220 else ""),
            "price_intelligence": pricing_info
        })

        if limit and len(results) >= limit:
            break

    return results

def fetch_deals(feed_key="deals", mode="latest", min_votes=None, limit=0, only_active=True, atl_only=False, exclude_supermarket_half_price=False):
    # Set default min_votes based on mode
    if min_votes is None:
        min_votes = 10 if mode == "popular" else None

    url = resolve_feed_url(feed_key, mode=mode)
    return fetch_feed_deals(url, min_votes=min_votes, limit=limit, only_active=only_active, atl_only=atl_only, exclude_supermarket_half_price=exclude_supermarket_half_price)

def fetch_multiple_categories(categories, mode="latest", min_votes=None, limit_per_cat=0, only_active=True, atl_only=False, exclude_supermarket_half_price=False):
    import concurrent.futures
    category_results = {}
    if min_votes is None and mode == "popular":
        min_votes = 10

    def _fetch_single(cat):
        url = resolve_feed_url(cat, mode=mode)
        deals = fetch_feed_deals(url, min_votes=min_votes, limit=limit_per_cat, only_active=only_active, atl_only=atl_only, exclude_supermarket_half_price=exclude_supermarket_half_price)
        return cat, deals

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(_fetch_single, c) for c in categories]
        for f in concurrent.futures.as_completed(futures):
            cat_name, deals = f.result()
            category_results[cat_name] = deals

    return category_results

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Fetch OzBargain deals (Latest chronological or Popular) with price intelligence")
    parser.add_argument("--feed", default="deals", help="deals (site-wide), or category slug: computing, electronics, gaming, fashion, groceries, etc. Can be comma-separated.")
    parser.add_argument("--mode", choices=["latest", "popular"], default=None, help="Mode: 'latest' (comprehensive real-time deals) or 'popular' (frontpage/high-vote deals).")
    parser.add_argument("--latest", action="store_true", help="Force latest mode (all new deals, no vote threshold by default)")
    parser.add_argument("--popular", action="store_true", help="Force popular mode (top-voted deals, min-votes defaults to 10)")
    parser.add_argument("--all-categories", action="store_true", help="Fetch comprehensive latest deals across all major categories simultaneously")
    parser.add_argument("--min-votes", type=int, default=None, help="Minimum net positive votes (default: no threshold for latest, 10 for popular)")
    parser.add_argument("--limit", type=int, default=None, help="Max number of items to return (default: 0 = all items returned by each RSS feed; positive values cap each feed)")
    parser.add_argument("--exclude-supermarket-half-price", action="store_true", help="Exclude Coles/Woolworths half-price posts from general scans")
    parser.add_argument("--include-expired", action="store_true", help="Include expired deals")
    parser.add_argument("--atl-only", action="store_true", help="Filter strictly to All-Time Low deals")
    args = parser.parse_args()

    # Determine mode
    if args.latest:
        mode = "latest"
    elif args.popular:
        mode = "popular"
    elif args.mode:
        mode = args.mode
    else:
        # Default to latest if user is asking for specific categories or deals without explicitly requesting popular
        mode = "latest"

    # Default min_votes
    if args.min_votes is not None:
        min_votes = args.min_votes
    else:
        min_votes = 10 if mode == "popular" else None

    if args.all_categories:
        limit_per_cat = args.limit if args.limit is not None else 0
        deals = fetch_multiple_categories(
            CORE_CATEGORIES,
            mode=mode,
            min_votes=min_votes,
            limit_per_cat=limit_per_cat,
            only_active=not args.include_expired,
            atl_only=args.atl_only,
            exclude_supermarket_half_price=args.exclude_supermarket_half_price
        )
    elif "," in args.feed:
        cats = [c.strip() for c in args.feed.split(",") if c.strip()]
        limit_per_cat = args.limit if args.limit is not None else 0
        deals = fetch_multiple_categories(
            cats,
            mode=mode,
            min_votes=min_votes,
            limit_per_cat=limit_per_cat,
            only_active=not args.include_expired,
            atl_only=args.atl_only,
            exclude_supermarket_half_price=args.exclude_supermarket_half_price
        )
    else:
        limit = args.limit if args.limit is not None else 0
        deals = fetch_deals(
            feed_key=args.feed,
            mode=mode,
            min_votes=min_votes,
            limit=limit,
            only_active=not args.include_expired,
            atl_only=args.atl_only,
            exclude_supermarket_half_price=args.exclude_supermarket_half_price
        )

    print(json.dumps(deals, ensure_ascii=False, indent=2))
