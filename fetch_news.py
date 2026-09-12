import feedparser, json, os, re, requests, pathlib
from datetime import datetime, timezone

# ========== CONFIG ==========
SECTORS = {
    "World": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.aljazeera.com/xml/rss/all.xml",
    ],
    "Markets": [
        "https://feeds.marketwatch.com/marketwatch/topstories/",
        "https://finance.yahoo.com/news/rssindex",
    ],
    "Tech/AI": [
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
    ],
    "Crypto": [
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
    ],
    "Science": [
        "https://www.sciencedaily.com/rss/top/science.xml",
        "https://www.space.com/feeds/all",
    ],
    "Health": [
        "https://www.who.int/rss-feeds/news-english.xml",
        "https://www.medicalnewstoday.com/rss",
    ],
}

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

# ========== REDDIT SPEED LAYER ==========
# Rising posts here often break news 30-60 min before mainstream media.
# Reddit's .json API is FREE - no key needed. Just a custom User-Agent.
REDDIT_SUBS = {
    "World":     ["worldnews", "geopolitics"],
    "Markets":   ["stocks", "investing"],
    "Tech/AI":   ["technology", "artificial"],
    "Crypto":    ["CryptoCurrency"],
    "Science":   ["science", "space"],
}
REDDIT_HEADERS = {"User-Agent": "personal-news-agent/1.0 (by /u/your_username)"}
REDDIT_PER_SUB = 5
REDDIT_MIN_SCORE = 20   # filter out tiny noise posts
MAX_PER_SECTOR = 5

def fetch_items():
    items = []
    seen = set()
    for sector, urls in SECTORS.items():
        count = 0
        for url in urls:
            if count >= MAX_PER_SECTOR:
                break
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:MAX_PER_SECTOR]:
                    title = entry.get("title", "").strip()
                    link = entry.get("link", "")
                    key = re.sub(r"\W+", "", title.lower())[:60]
                    if not title or key in seen:
                        continue
                    seen.add(key)
                    summary = re.sub(r"<[^>]+>", "", entry.get("summary", ""))[:500]
                    items.append({
                        "sector": sector,
                        "title": title,
                        "link": link,
                        "summary": summary,
                        "published": entry.get("published", ""),
                        "source": "rss",
                    })
                    count += 1
            except Exception as e:
                print(f"Feed error {url}: {e}")
    return items

def fetch_reddit_items():
    items = []
    seen = set()
    for sector, subs in REDDIT_SUBS.items():
        for sub in subs:
            try:
                url = f"https://www.reddit.com/r/{sub}/rising.json?limit={REDDIT_PER_SUB}"
                r = requests.get(url, headers=REDDIT_HEADERS, timeout=20)
                posts = r.json().get("data", {}).get("children", [])
                for p in posts:
                    d = p.get("data", {})
                    if d.get("stickied") or d.get("is_video") or d.get("over_18"):
                        continue
                    score = d.get("score", 0)
                    if score < REDDIT_MIN_SCORE:
                        continue
                    title = d.get("title", "").strip()
                    if not title:
                        continue
                    key = re.sub(r"\W+", "", title.lower())[:60]
                    if key in seen:
                        continue
                    seen.add(key)
                    link = "https://www.reddit.com" + d.get("permalink", "")
                    selftext = re.sub(r"\s+", " ", d.get("selftext", ""))[:400]
                    flair = d.get("link_flair_text") or ""
                    summary = f"[Reddit r/{sub} | score {score}] {flair} {selftext}".strip()
                    items.append({
                        "sector": sector,
                        "title": title,
                        "link": link,
                        "summary": summary,
                        "published": "",
                        "source": "reddit",
                    })
            except Exception as e:
                print(f"Reddit error r/{sub}: {e}")
    return items

def analyze_with_ai(items):
    if not GEMINI_KEY or not items:
        for it in items:
            it.update(impact="🟡 Medium",
                      why="AI key not set - add GEMINI_API_KEY secret in GitHub.",
                      effect="Add your free Gemini API key to enable impact analysis.")
        return items

    batch = [{"title": i["title"], "sector": i["sector"], "summary": i["summary"]} for i in items[:30]]
    prompt = """For each news item in this JSON array, analyze it.
Return ONLY a JSON array (no markdown, no explanation) where each object has:
- "title": the exact same title from input
- "impact": one of "🔴 High", "🟡 Medium", "🟢 Low" (based on how many people/markets it affects)
- "why": one short sentence (max 25 words) explaining WHY it happened
- "effect": one short sentence (max 25 words) explaining WHO/WHAT it affects and HOW

News items: """ + json.dumps(batch)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={GEMINI_KEY}"
    r = requests.post(url, json={
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }, timeout=90)
    try:
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        analyses = json.loads(text)
        amap = {a["title"]: a for a in analyses}
        for it in items:
            a = amap.get(it["title"])
            if a:
                it.update(impact=a.get("impact", "🟡 Medium"),
                          why=a.get("why", ""), effect=a.get("effect", ""))
    except Exception as e:
        print(f"AI error: {e} | status: {r.status_code} | body: {r.text[:300]}")
    return items

if __name__ == "__main__":
    items = fetch_items()
    reddit_items = fetch_reddit_items()
    print(f"Fetched {len(items)} RSS items, {len(reddit_items)} Reddit items")
    items = items + reddit_items
    items = analyze_with_ai(items)
    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "count": len(items),
        "items": items,
    }
    with open("news.json", "w") as f:
        json.dump(out, f, indent=1)
    pathlib.Path(".nojekyll").touch()   # speeds up deploy, avoids Jekyll errors
    print("Wrote news.json")
