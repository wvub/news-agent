"""
Fact-checking integration for News Agent.

1. Flags articles touching topics that are frequent targets of misinformation.
2. If GOOGLE_FACTCHECK_KEY is set, looks flagged articles up in the Google
   Fact Check Tools API and attaches any published fact-checks (cached per
   article so each one is only looked up once).
"""
import json
import os
import re
from datetime import datetime, timezone

import requests

FACTCHECK_KEY = os.environ.get("GOOGLE_FACTCHECK_KEY", "").strip()
MAX_LOOKUPS_PER_RUN = 15

SENSITIVE_TOPICS = [
    "election fraud", "rigged election", "stolen election", "vaccine", "vaccines", "vaccination",
    "climate change", "global warming", "moon landing", "5g", "flat earth", "chemtrail",
    "conspiracy", "hoax", "misinformation", "disinformation", "deepfake", "fake news",
    "miracle cure", "cure for cancer", "ivermectin", "hydroxychloroquine", "voter fraud",
    "false claim", "debunked", "fact check", "fact-check", "rumor", "rumour", "viral claim",
]
_TOPIC_RE = [(t, re.compile(r"\b" + re.escape(t) + r"\b", re.I)) for t in SENSITIVE_TOPICS]


def check_with_google_factcheck(claim):
    """Search the Google Fact Check Tools API for published reviews of a claim."""
    if not FACTCHECK_KEY:
        return {"status": "disabled", "claims": []}
    try:
        r = requests.get("https://factchecktools.googleapis.com/v1alpha1/claims:search",
                         params={"query": claim[:200], "languageCode": "en", "pageSize": 3,
                                 "key": FACTCHECK_KEY}, timeout=10)
        r.raise_for_status()
        claims = []
        for c in r.json().get("claims", [])[:3]:
            review = (c.get("claimReview") or [{}])[0]
            claims.append({
                "text": c.get("text", "")[:200],
                "claimant": c.get("claimant", ""),
                "rating": review.get("textualRating", ""),
                "publisher": (review.get("publisher") or {}).get("name", ""),
                "url": review.get("url", ""),
            })
        return {"status": "found" if claims else "not_found", "claims": claims}
    except Exception as e:
        print(f"  Fact-check error: {e}")
        return {"status": "error", "claims": []}


def flag_disputed_claims(items, cache=None):
    """Mark items that mention sensitive topics; attach fact-checks when available."""
    cache = cache or {}
    lookups = 0
    for item in items:
        text = f"{item.get('title', '')} {item.get('summary', '')}"
        topic = next((t for t, rx in _TOPIC_RE if rx.search(text)), None)
        item["fact_check_needed"] = bool(topic)
        item["disputed_topic"] = topic
        if not topic:
            continue
        prev = cache.get(item.get("id"), {})
        if prev.get("fact_checks") is not None:
            item["fact_checks"] = prev["fact_checks"]
        elif FACTCHECK_KEY and lookups < MAX_LOOKUPS_PER_RUN:
            result = check_with_google_factcheck(item.get("title", ""))
            lookups += 1
            if result["status"] in ("found", "not_found"):
                item["fact_checks"] = result["claims"]
    return items


def generate_fact_check_report(items):
    disputed = [i for i in items if i.get("fact_check_needed")]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_articles": len(items),
        "disputed_articles": len(disputed),
        "api_enabled": bool(FACTCHECK_KEY),
        "disputed_items": [
            {"title": i.get("title"), "topic": i.get("disputed_topic"), "source": i.get("source"),
             "link": i.get("link"), "fact_checks": i.get("fact_checks", [])}
            for i in disputed
        ],
    }


if __name__ == "__main__":
    try:
        with open("news.json") as f:
            items = json.load(f).get("items", [])
    except (FileNotFoundError, json.JSONDecodeError):
        items = []
    report = generate_fact_check_report(flag_disputed_claims(items))
    with open("fact_check_report.json", "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"✓ Fact-check report: {report['disputed_articles']} flagged items")
