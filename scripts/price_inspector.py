#!/usr/bin/env python3
"""
Price Inspector - Price History & True Discount Intelligence
Detects ATL (All-Time Low), cyclical half-price discounts, and generates validation links.
"""
import re
import urllib.parse

def clean_product_query(title: str) -> str:
    """
    Strips store names, prices, discounts, and common tags to get a clean search query.
    Example: "KB's Raw Prawns Tail On Large 500g $12.00 (Was $24.00, 50% off) @ Coles"
             -> "KB's Raw Prawns Tail On Large 500g"
    """
    cleaned = title
    # Remove "@ Store" suffix
    cleaned = re.sub(r'\s*@\s*[\w\.\s\-\']+$', '', cleaned, flags=re.IGNORECASE)
    # Remove leading tags like [PC, Steam], [NSW], [Refurb], etc.
    cleaned = re.sub(r'^\s*\[[^\]]+\]\s*', '', cleaned)
    # Remove parenthetical notes containing price terms (e.g. (Was $24.00, 50% off))
    cleaned = re.sub(r'\([^)]*?(?:was|\$|off|save|prime|spend|subscribe|c&c)[^)]*?\)', '', cleaned, flags=re.IGNORECASE)
    # Remove standalone prices and percentages
    cleaned = re.sub(r'\$\d+(?:\.\d+)?|\b\d+%\s*off\b|\b½\s*Price:?\b|\b1/2\s*Price:?\b', '', cleaned, flags=re.IGNORECASE)
    # Clean up empty brackets and dangling punctuation
    cleaned = re.sub(r'[\(\)\[\]\{\}]', ' ', cleaned)
    cleaned = re.sub(r'[,:\-]\s*$', '', cleaned.strip())
    cleaned = re.sub(r'^\s*[,:\-]', '', cleaned.strip())
    # Remove multiple spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    # Fallback if over-cleaned
    return cleaned if len(cleaned) >= 3 else title.strip()

def inspect_deal_pricing(title: str, description: str = "", store_url: str = "") -> dict:
    """
    Analyzes title and description to detect price history indicators and generate verification links.
    """
    text_corpus = f"{title} {description}"
    
    # 1. Detect ATL (All-Time Low)
    is_atl = bool(re.search(r'\bATL\b|all[\s\-]time[\s\-]low|cheapest[\s\-]ever|lowest[\s\-]ever|record[\s\-]low|追踪史低', text_corpus, re.IGNORECASE))
    is_matches_atl = bool(re.search(r'matches?[\s\-](?:previous[\s\-])?ATL|平史低', text_corpus, re.IGNORECASE))
    
    # 2. Detect Half-Price / 50% Off
    is_half_price = bool(re.search(r'½\s*price|1/2\s*price|half\s*price|50%\s*off|半价', text_corpus, re.IGNORECASE))
    
    # 3. Detect Repost / Recurring deal
    is_repost = bool(re.search(r'\bRepost\b|back\s*in\s*stock|down\s*to\s*\$\d+\s*again', text_corpus, re.IGNORECASE))

    # Determine status badge
    if is_atl and not is_matches_atl:
        status_badge = "帖子声称史低 (ATL claim)"
        price_tier = "ATL"
    elif is_matches_atl:
        status_badge = "帖子声称平史低 (Matches ATL claim)"
        price_tier = "MATCHES_ATL"
    elif is_half_price:
        status_badge = "半价标签 (Half Price)"
        price_tier = "HALF_PRICE"
    elif is_repost:
        status_badge = "重复活动标签 (Recurring Deal)"
        price_tier = "RECURRING"
    else:
        status_badge = "⚪ 普通特惠 (Standard Deal)"
        price_tier = "STANDARD"

    # Extract Coupon Code if present
    coupon_code = None
    coupon_match = re.search(r'(?:code|coupon|promocode|promo\s*code|折扣码|优惠码)[:\s]+([A-Z0-9\-_]{4,16})\b', text_corpus, re.IGNORECASE)
    if coupon_match:
        coupon_code = coupon_match.group(1).strip()

    # Generate verification links
    clean_query = clean_product_query(title)
    encoded_q = urllib.parse.quote_plus(clean_query)
    
    external_links = {
        "price_hipster": f"https://pricehipster.com/?q={encoded_q}",
        "google_shopping": f"https://www.google.com.au/search?tbm=shop&q={encoded_q}",
    }
    
    if "amazon.com.au" in (store_url or "").lower() or "amazon" in title.lower():
        external_links["camelcamelcamel"] = f"https://au.camelcamelcamel.com/search?sq={encoded_q}"

    return {
        "clean_query": clean_query,
        "status_badge": status_badge,
        "price_tier": price_tier,
        "is_atl": is_atl,
        "history_verified": False,
        "is_matches_atl": is_matches_atl,
        "is_half_price": is_half_price,
        "coupon_code": coupon_code,
        "verification_links": external_links
    }

if __name__ == "__main__":
    sample_title = "KB's Raw Prawns Tail On Large 500g $12.00 (Was $24.00, 50% off) @ Coles"
    sample_desc = "Cheapest ever since tracking. Specials for this have been around 30% mark and this is the first time it has been to 50% ATL"
    print(inspect_deal_pricing(sample_title, sample_desc))
