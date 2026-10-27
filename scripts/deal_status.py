"""Interpret explicit OzBargain RSS availability without inferring missing data."""
from datetime import datetime, timezone
import re


def parse_time(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except ValueError:
        return None


def deal_status(meta, title="", now=None):
    now = now or datetime.now(timezone.utc)
    flags = " ".join((title, meta.get("title-msg", ""))).lower()
    if re.search(r"expired|out of stock|sold out", flags):
        return "out_of_stock" if re.search(r"out of stock|sold out", flags) else "expired"
    expiry = parse_time(meta.get("expiry"))
    if expiry and expiry <= now:
        return "expired"
    starting = parse_time(meta.get("starting"))
    if (starting and starting > now) or re.search(r"upcoming|not yet available", flags):
        return "upcoming"
    return "active" if expiry or starting else "unknown"
