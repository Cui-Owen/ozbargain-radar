#!/usr/bin/env python3
"""
OzBargain Comment Fetcher & Cleaner
Extracts substantive user feedback, reviews, and pitfall warnings for a given deal.
Filters out pleasantries, bot responses, and trivial 'thanks' messages.
"""
import argparse
import html
import json
import re
import sys
import urllib.request

TRIVIAL_PATTERNS = [
    r'^\s*thanks\b',
    r'^\s*thank\s*you\b',
    r'^\s*cheers\b',
    r'^\s*nice\s*find\b',
    r'^\s*good\s*morning\b',
    r'^\s*great\s*find\b',
    r'^\s*voted\b',
    r'^\s*\+1\b',
    r'^\s*bought\s*one\b',
    r'^\s*ordered\b',
    r'^\s*in\s*for\s*one\b',
    r'^\s*repost\b',
]

def clean_html_text(raw_html: str) -> str:
    if not raw_html:
        return ""
    # Remove blockquotes (quoted replies to avoid repetitive bloat)
    text = re.sub(r'<blockquote[^>]*>.*?</blockquote>', ' ', raw_html, flags=re.DOTALL)
    # Remove html tags
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()

def is_substantive_comment(comment_text: str) -> bool:
    """Filters out trivial short pleasantries."""
    if len(comment_text) < 15:
        return False
    lower_t = comment_text.lower()
    for pat in TRIVIAL_PATTERNS:
        if re.search(pat, lower_t):
            if len(comment_text) < 45:
                return False
    return True

def fetch_deal_comments(node_or_url: str, limit: int = 25):
    # Normalize URL
    if str(node_or_url).isdigit():
        url = f"https://www.ozbargain.com.au/node/{node_or_url}"
        node_id = str(node_or_url)
    else:
        url = str(node_or_url)
        m = re.search(r'/node/(\d+)', url)
        node_id = m.group(1) if m else ""

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) OzBargainRadar/1.0"}
    )

    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            page_html = resp.read().decode('utf-8', errors='ignore')
    except Exception as e:
        return {
            "error": f"Failed to fetch {url}: {e}",
            "node_id": node_id,
            "url": url,
            "comments": []
        }

    # Extract deal title
    title_m = re.search(r'<h1[^>]*id=\"title\d*\"[^>]*>(.*?)</h1>', page_html, re.DOTALL)
    if not title_m:
        title_m = re.search(r'<title>(.*?)</title>', page_html)
    deal_title = clean_html_text(title_m.group(1)) if title_m else ""
    deal_title = re.sub(r'\s*-\s*OzBargain$', '', deal_title)

    # Each comment wrapper is distinct from the deal and referral descriptions.
    # Metadata may contain a closing div between submitted and content.
    blocks = re.split(r'<div\b(?=[^>]*\bclass="[^"]*\bcomment-wrap\b)[^>]*>', page_html)[1:]
    comment_pairs = []
    for block in blocks:
        submitted = re.search(r'<div class="submitted">(.*?)</div>', block, re.DOTALL)
        content = re.search(r'<div class="content">(.*?)</div>', block, re.DOTALL)
        if submitted and content:
            comment_pairs.append((submitted.group(1), content.group(1)))

    substantive_comments = []
    for sub, cont in comment_pairs:
        author_m = re.search(r'<strong>(?:<a[^>]*>)?([^<]+)(?:</a>)?</strong>', sub)
        author = author_m.group(1).strip() if author_m else "Community Member"

        cleaned_text = clean_html_text(cont)
        if is_substantive_comment(cleaned_text):
            substantive_comments.append({
                "author": author,
                "text": cleaned_text
            })
            if len(substantive_comments) >= limit:
                break

    return {
        "node_id": node_id,
        "url": url,
        "deal_title": deal_title,
        "total_extracted": len(comment_pairs),
        "substantive_count": len(substantive_comments),
        "coverage": "Current page only; filtered substantive comments, no pagination",
        "comments": substantive_comments
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch comments and reviews for an OzBargain deal")
    parser.add_argument("target", help="Node ID (e.g. 977982) or OzBargain URL")
    parser.add_argument("--limit", type=int, default=20, help="Maximum number of substantive comments")
    args = parser.parse_args()

    data = fetch_deal_comments(args.target, limit=args.limit)
    print(json.dumps(data, ensure_ascii=False, indent=2))
