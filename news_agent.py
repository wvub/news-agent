#!/usr/bin/env python3
"""
Comprehensive News Agent - Fetches, analyzes, and serves curated news.

Pipeline:  fetch (RSS + Reddit + social) -> sentiment -> dedup/similarity ->
           trends -> Gemini impact analysis (cached) -> fact-check flags ->
           optional translations -> outputs (news.json, snapshots, quiz,
           history index, source health) -> optional email digest.
"""
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html import unescape

import feedparser
import requests
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from textblob import TextBlob

import email_digest
import fact_checker
import news_quiz
import translator

# ========== TIMEZONE CONFIG ==========
IST = timezone(timedelta(hours=5, minutes=30))  # Indian Standard Time (UTC+5:30)


def get_ist_time():
    """Get current time in Indian Standard Time"""
    return datetime.now(IST)


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ========== CONFIG ==========
SECTORS = {
    "World": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://feeds.npr.org/1004/rss.xml",
    ],
    "Markets": [
        "https://feeds.marketwatch.com/marketwatch/topstories/",
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "https://feeds.bloomberg.com/markets/news.rss",
    ],
    "Tech/AI": [
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
        "https://feeds.arstechnica.com/arstechnica/index",
    ],
    "Crypto": [
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
        "https://decrypt.co/feed",
    ],
    "Science": [
        "https://www.sciencedaily.com/rss/top/science.xml",
        "https://www.space.com/feeds/all",
        "https://www.nature.com/nature.rss",
        "https://phys.org/rss-feed/",
    ],
    "Health": [
        "https://www.who.int/rss-feeds/news-english.xml",
        "https://www.statnews.com/feed/",
        "https://www.sciencedaily.com/rss/health_medicine.xml",
    ],
}

REDDIT_SUBS = {
    "World": ["worldnews", "geopolitics", "news"],
    "Markets": ["stocks", "investing", "wallstreetbets"],
    "Tech/AI": ["technology", "artificial", "MachineLearning"],
    "Crypto": ["CryptoCurrency", "Bitcoin"],
    "Science": ["science", "space", "astronomy"],
    "Health": ["Health", "Medicine"],
}

# Short display names by domain (falls back to the feed's own title)
FEED_NAMES = {
    "bbci.co.uk": "BBC", "aljazeera.com": "Al Jazeera", "theguardian.com": "The Guardian", "npr.org": "NPR",
    "marketwatch.com": "MarketWatch", "cnbc.com": "CNBC", "bloomberg.com": "Bloomberg",
    "techcrunch.com": "TechCrunch", "theverge.com": "The Verge", "arstechnica.com": "Ars Technica",
    "coindesk.com": "CoinDesk", "cointelegraph.com": "Cointelegraph", "decrypt.co": "Decrypt",
    "sciencedaily.com": "ScienceDaily", "space.com": "Space.com", "nature.com": "Nature",
    "phys.org": "Phys.org", "who.int": "WHO", "statnews.com": "STAT",
}


def feed_display_name(url, title):
    host = url.split("/")[2]
    for domain, name in FEED_NAMES.items():
        if host == domain or host.endswith("." + domain):
            return name
    return clean_html(title)[:30] or host


SOCIAL_SOURCES = {
    "hacker_news": ("Hacker News", "https://hnrss.org/frontpage"),
    "producthunt": ("Product Hunt", "https://www.producthunt.com/feed"),
}

BROWSER_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
REDDIT_UA = os.environ.get("REDDIT_USER_AGENT", "python:news-agent:v3.0 (personal news dashboard)")
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")
REDDIT_PER_SUB = 5
REDDIT_MIN_SCORE = 20
MAX_PER_SECTOR = 12      # articles per sector
MAX_PER_FEED = 4         # cap per feed so every source in a sector gets a share
SOCIAL_PER_SOURCE = 5
HTTP_TIMEOUT = 20

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
# Tried in order; the first model that exists for this key is used.
# Preferred models, tried in order. Models the key can't use are skipped, and
# any other available Flash models are discovered at runtime (see gemini_models()).
GEMINI_PREFERRED = [m for m in [os.environ.get("GEMINI_MODEL", "").strip(),
                                "gemini-flash-latest", "gemini-flash-lite-latest"] if m]
GEMINI_BATCH = 20
GEMINI_TIMEOUT = 60
AI_TIME_BUDGET = 240  # seconds per run; unfinished items are retried next run
AI_MAX_NEW_ITEMS = int(os.environ.get("AI_MAX_NEW_ITEMS", "100"))

TRANSLATE_LANGS = [l.strip() for l in os.environ.get("TRANSLATE_LANGS", "").split(",") if l.strip()]

DB_PATH = "news_history.db"
NEWS_FILE = "news.json"
HEALTH_FILE = "source_health.json"
HISTORY_DIR = pathlib.Path("history")
HISTORY_INDEX_FILE = "history_index.json"
MAX_SNAPSHOTS = 100

STOPWORDS = set("""
a about above after again against all also am an and any are aren as at be because been before
being below between both but by can cannot could did didn do does doesn doing don down during each
few for from further had has have having he her here hers herself him himself his how i if in into
is isn it its itself just let me more most my myself new news no nor not now of off on once only or
other our ours ourselves out over own said same says say she should so some such than that the their
theirs them themselves then there these they this those through to too under until up very was
wasn we were what when where which while who whom why will with would you your yours yourself
yourselves year years week weeks today first last could after over than more most many much
make makes made like just into been being their there these those what when where which while
amid back still well even every here time times report reports according people week months
best already ahead against across another around because before between during through under
whether without within become becomes biggest big next show shows told year's latest update
reddit score comments article link hacker product hunt https http www html
discussion discussions thread launch launched
""".split())


# ========== HTTP ==========
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": BROWSER_UA,
                        "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"})


def fetch_feed(url):
    """Download and parse a feed with a real timeout. Raises on failure / empty feed."""
    r = SESSION.get(url, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    if not feed.entries:
        reason = getattr(feed, "bozo_exception", None) or "no entries"
        raise ValueError(f"empty feed ({reason})")
    return feed


def clean_html(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", unescape(text)).strip()


# ========== SOURCE HEALTH (persisted in git as JSON) ==========
_HEALTH = {}


def load_health():
    global _HEALTH
    try:
        with open(HEALTH_FILE) as f:
            _HEALTH = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _HEALTH = {}


def _health_entry(source, sector):
    h = _HEALTH.setdefault(source, {"source": source, "sector": sector, "last_success": None,
                                    "last_failure": None, "success_count": 0, "failure_count": 0,
                                    "last_error": None, "last_items": 0})
    h["sector"] = sector
    return h


def log_source_success(source, sector, n_items=0):
    h = _health_entry(source, sector)
    h["last_success"] = utc_now_iso()
    h["success_count"] += 1
    h["last_items"] = n_items


def log_source_failure(source, sector, error):
    h = _health_entry(source, sector)
    h["last_failure"] = utc_now_iso()
    h["failure_count"] += 1
    h["last_error"] = str(error)[:200]
    print(f"  ✗ Source error {source}: {str(error)[:150]}")


def configured_sources():
    names = {url for urls in SECTORS.values() for url in urls}
    names |= {f"r/{sub}" for subs in REDDIT_SUBS.values() for sub in subs}
    names |= {name for name, _ in SOCIAL_SOURCES.values()}
    return names


def save_health():
    for source in set(_HEALTH) - configured_sources():
        del _HEALTH[source]  # feed was removed from the config
    with open(HEALTH_FILE, "w") as f:
        json.dump(_HEALTH, f, indent=1, sort_keys=True)


def health_list():
    rows = list(_HEALTH.values())
    for h in rows:
        h["healthy"] = bool(h["last_success"]) and (not h["last_failure"] or h["last_success"] >= h["last_failure"])
    return sorted(rows, key=lambda h: (h["healthy"], h["source"]))


# ========== DATABASE (local history; gitignored) ==========
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS articles (
        id TEXT PRIMARY KEY, title TEXT NOT NULL, link TEXT, sector TEXT, source TEXT,
        summary TEXT, published TEXT, fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        sentiment_score REAL, sentiment_label TEXT, impact TEXT, why TEXT, effect TEXT,
        content_hash TEXT, keywords TEXT, related_articles TEXT, embedding TEXT)''')
    conn.commit()
    conn.close()


def save_to_db(items):
    conn = sqlite3.connect(DB_PATH)
    for item in items:
        try:
            conn.execute('''INSERT INTO articles
                (id, title, link, sector, source, summary, published, sentiment_score,
                 sentiment_label, impact, why, effect, content_hash, keywords, related_articles)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET impact=excluded.impact, why=excluded.why,
                  effect=excluded.effect, sentiment_score=excluded.sentiment_score,
                  sentiment_label=excluded.sentiment_label, related_articles=excluded.related_articles''',
                (item.get("id"), item.get("title"), item.get("link"), item.get("sector"),
                 item.get("source"), item.get("summary"), item.get("published"),
                 item.get("sentiment_score", 0.0), item.get("sentiment_label", "Neutral 😐"),
                 item.get("impact"), item.get("why"), item.get("effect"),
                 compute_content_hash(item.get("title", "")), json.dumps(item.get("keywords", [])),
                 json.dumps(item.get("related", []))))
        except Exception as e:
            print(f"DB save error: {e}")
    conn.commit()
    conn.close()


# ========== SENTIMENT ==========
def analyze_sentiment(text):
    try:
        polarity = float(TextBlob(text[:500]).sentiment.polarity)
    except Exception:
        polarity = 0.0
    if polarity > 0.1:
        label = "Positive 😊"
    elif polarity < -0.1:
        label = "Negative 😞"
    else:
        label = "Neutral 😐"
    return round(polarity, 3), label


# ========== DEDUP & SIMILARITY ==========
def compute_content_hash(text):
    return hashlib.md5(text.lower().encode()).hexdigest()


def title_key(title):
    return re.sub(r"\W+", "", title.lower())[:60]


def find_similar_articles(items, threshold=0.4):
    """Return list of (i, j, score) pairs of near-duplicate stories (TF-IDF cosine)."""
    if len(items) < 2:
        return []
    texts = [f"{it['title']} {it['title']} {it['summary'][:300]}" for it in items]
    try:
        matrix = TfidfVectorizer(stop_words="english", max_features=5000).fit_transform(texts)
        sim = cosine_similarity(matrix)
    except ValueError:
        return []
    pairs = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if sim[i][j] >= threshold:
                pairs.append((i, j, float(sim[i][j])))
    return pairs


def attach_related(items, pairs):
    related = defaultdict(set)
    for i, j, _ in pairs:
        related[i].add(j)
        related[j].add(i)
    for idx, it in enumerate(items):
        it["related"] = [items[j]["id"] for j in sorted(related.get(idx, []))]
        it["cross_sector"] = len({items[j]["sector"] for j in related.get(idx, [])} - {it["sector"]}) > 0


# ========== KEYWORDS & TRENDS ==========
def extract_keywords(text, max_keywords=5):
    words = re.findall(r"\b[a-zA-Z][a-zA-Z\-]{3,}\b", text)
    freq = defaultdict(int)
    for w in words:
        lw = w.lower().strip("-")
        if lw in STOPWORDS or len(lw) < 4:
            continue
        freq[lw] += 1
    return sorted(freq.items(), key=lambda x: (-x[1], x[0]))[:max_keywords]


def detect_trends(items, top_n=15):
    """Trending keywords: counted once per article, ranked by article spread."""
    kw = defaultdict(lambda: {"count": 0, "sectors": set(), "articles": []})
    for idx, it in enumerate(items):
        for word in set(it.get("keywords", [])):
            kw[word]["count"] += 1
            kw[word]["sectors"].add(it["sector"])
            kw[word]["articles"].append(it["id"])
    trends = [
        {"keyword": k, "frequency": v["count"], "sectors": sorted(v["sectors"]),
         "article_count": len(v["articles"]), "articles": v["articles"][:20]}
        for k, v in kw.items() if v["count"] >= 2
    ]
    trends.sort(key=lambda t: (-t["frequency"], -len(t["sectors"]), t["keyword"]))
    return trends[:top_n]


def make_item(sector, title, link, summary, published, source, source_name):
    title = clean_html(title)
    summary = clean_html(summary)[:500]
    score, label = analyze_sentiment(f"{title} {summary}")
    return {
        "id": compute_content_hash(title + link),
        "sector": sector,
        "title": title,
        "link": link,
        "summary": summary,
        "published": published,
        "source": source,
        "source_name": source_name,
        "sentiment_score": score,
        "sentiment_label": label,
        "keywords": [k for k, _ in extract_keywords(f"{title} {title} {summary}")],
    }


# ========== RSS ==========
def fetch_items(seen):
    items = []
    for sector, urls in SECTORS.items():
        per_feed = {}
        for url in urls:
            try:
                feed = fetch_feed(url)
                per_feed[url] = (feed_display_name(url, feed.feed.get("title", "")), feed.entries)
                log_source_success(url, sector, len(feed.entries))
            except Exception as e:
                log_source_failure(url, sector, e)
        # round-robin across feeds so one source can't fill the whole sector
        count, depth = 0, 0
        while count < MAX_PER_SECTOR and depth < MAX_PER_FEED:
            added_this_round = False
            for url, (name, entries) in per_feed.items():
                if count >= MAX_PER_SECTOR or depth >= len(entries):
                    continue
                e = entries[depth]
                title = (e.get("title") or "").strip()
                key = title_key(title)
                if not title or key in seen:
                    continue
                seen.add(key)
                items.append(make_item(sector, title, e.get("link", ""), e.get("summary", ""),
                                       e.get("published", e.get("updated", "")), "rss", name))
                count += 1
                added_this_round = True
            depth += 1
            if not added_this_round and all(depth >= len(en) for _, en in per_feed.values()):
                break
    return items


# ========== REDDIT ==========
def reddit_token():
    if not (REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET):
        return None
    try:
        r = requests.post("https://www.reddit.com/api/v1/access_token",
                          auth=(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET),
                          data={"grant_type": "client_credentials"},
                          headers={"User-Agent": REDDIT_UA}, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        return r.json().get("access_token")
    except Exception as e:
        print(f"  ✗ Reddit OAuth failed: {e}")
        return None


def _reddit_json(sub, token):
    if token:
        url = f"https://oauth.reddit.com/r/{sub}/rising?limit={REDDIT_PER_SUB * 2}&raw_json=1"
        headers = {"User-Agent": REDDIT_UA, "Authorization": f"bearer {token}"}
    else:
        url = f"https://www.reddit.com/r/{sub}/rising.json?limit={REDDIT_PER_SUB * 2}&raw_json=1"
        headers = {"User-Agent": REDDIT_UA}
    r = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return [p.get("data", {}) for p in r.json().get("data", {}).get("children", [])]


def _reddit_rss(sub):
    """Fallback when the JSON API is blocked (common on cloud IPs). No scores available."""
    r = requests.get(f"https://old.reddit.com/r/{sub}/rising/.rss", headers={"User-Agent": REDDIT_UA},
                     timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    if not feed.entries:
        raise ValueError("empty RSS")
    return [{"title": e.get("title", ""), "permalink": e.get("link", "").replace("https://old.reddit.com", ""),
             "selftext": clean_html(e.get("summary", ""))[:400], "score": None,
             "created_utc": None} for e in feed.entries]


def fetch_reddit_items(seen):
    items = []
    token = reddit_token()
    for sector, subs in REDDIT_SUBS.items():
        for sub in subs:
            name = f"r/{sub}"
            try:
                try:
                    posts = _reddit_json(sub, token)
                except Exception as json_err:
                    try:
                        posts = _reddit_rss(sub)
                    except Exception as rss_err:
                        raise RuntimeError(f"json: {json_err}; rss: {rss_err}")
                added = 0
                for d in posts:
                    if added >= REDDIT_PER_SUB:
                        break
                    if d.get("stickied") or d.get("is_video") or d.get("over_18"):
                        continue
                    score = d.get("score")
                    if score is not None and score < REDDIT_MIN_SCORE:
                        continue
                    title = (d.get("title") or "").strip()
                    key = title_key(title)
                    if not title or key in seen:
                        continue
                    seen.add(key)
                    link = d.get("permalink", "")
                    if link.startswith("/"):
                        link = "https://www.reddit.com" + link
                    flair = d.get("link_flair_text") or ""
                    score_txt = f" | score {score}" if score is not None else ""
                    summary = f"[Reddit {name}{score_txt}] {flair} {d.get('selftext', '')[:400]}".strip()
                    published = ""
                    if d.get("created_utc"):
                        published = datetime.fromtimestamp(d["created_utc"], timezone.utc).strftime(
                            "%a, %d %b %Y %H:%M:%S GMT")
                    items.append(make_item(sector, title, link, summary, published, "reddit", name))
                    added += 1
                log_source_success(name, sector, added)
            except Exception as e:
                log_source_failure(name, sector, e)
            time.sleep(0.5 if token else 1.0)  # stay well under Reddit rate limits
    return items


# ========== SOCIAL ==========
def fetch_social_items(seen):
    items = []
    for source, (name, url) in SOCIAL_SOURCES.items():
        try:
            feed = fetch_feed(url)
            added = 0
            for e in feed.entries:
                if added >= SOCIAL_PER_SOURCE:
                    break
                title = (e.get("title") or "").strip()
                key = title_key(title)
                if not title or key in seen:
                    continue
                seen.add(key)
                summary = clean_html(e.get("summary", ""))
                if source == "hacker_news":
                    summary = ""  # HN RSS summary is just a "Comments" link
                items.append(make_item("Tech/AI", title, e.get("link", ""), f"[{name}] {summary}".strip(),
                                       e.get("published", e.get("updated", "")), source, name))
                added += 1
            log_source_success(name, "Tech/AI", added)
        except Exception as e:
            log_source_failure(name, "Tech/AI", e)
    return items


# ========== AI ANALYSIS (Gemini REST API, cached per article) ==========
VALID_IMPACTS = {"high": "🔴 High", "medium": "🟡 Medium", "low": "🟢 Low"}
AI_FIELDS = ("impact", "why", "effect", "summary_short", "category")


def normalize_impact(value):
    v = (value or "").lower()
    for k, label in VALID_IMPACTS.items():
        if k in v:
            return label
    return "🟡 Medium"


_working_model = None
_model_list = None
_struggling = set()  # models that timed out / were overloaded this run: tried last


def _model_sort_key(name):
    nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)", name)[:1]] or [0.0]
    return (-nums[0], "lite" in name, "preview" in name or "exp" in name, name)


def gemini_models():
    """Preferred models that exist for this key, then other Flash models newest-first."""
    global _model_list
    if _model_list is not None:
        return _model_list
    available = []
    try:
        r = requests.get("https://generativelanguage.googleapis.com/v1beta/models", params={"pageSize": 1000},
                         headers={"x-goog-api-key": GEMINI_KEY}, timeout=20)
        r.raise_for_status()
        for m in r.json().get("models", []):
            name = m.get("name", "").removeprefix("models/")
            if "generateContent" not in m.get("supportedGenerationMethods", []):
                continue
            if "flash" not in name or re.search(r"image|tts|audio|live|embed|thinking|vision", name):
                continue
            available.append(name)
    except Exception as e:
        print(f"  (could not list Gemini models: {e}; using defaults)")
        _model_list = GEMINI_PREFERRED
        return _model_list
    preferred = [m for m in GEMINI_PREFERRED if m in available or m == os.environ.get("GEMINI_MODEL", "").strip()]
    others = sorted((m for m in available if m not in preferred), key=_model_sort_key)
    _model_list = (preferred + others)[:5] or GEMINI_PREFERRED
    print(f"  Gemini models: {', '.join(_model_list)}")
    return _model_list


def gemini_generate(prompt, json_mode=True, temperature=0.2):
    """Call Gemini. A model that is missing (404), overloaded (429/5xx) or slow
    falls through to the next one from gemini_models()."""
    global _working_model
    models = ([_working_model] if _working_model else []) + [m for m in gemini_models() if m != _working_model]
    models = [m for m in models if m not in _struggling] + [m for m in models if m in _struggling]
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": temperature}}
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    errors = []
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for attempt in range(2):
            try:
                r = requests.post(url, json=body, headers={"x-goog-api-key": GEMINI_KEY}, timeout=GEMINI_TIMEOUT)
            except requests.RequestException as e:
                errors.append(f"{model}: {type(e).__name__}")
                _struggling.add(model)
                if _working_model == model:
                    _working_model = None
                break  # slow/unreachable: move on to the next model
            if r.status_code == 200:
                data = r.json()
                try:
                    text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
                except (KeyError, IndexError):
                    errors.append(f"{model}: empty response")
                    break
                _working_model = model
                return text
            errors.append(f"{model}: {r.status_code}")
            if r.status_code in (429, 500, 503):
                if attempt == 0:
                    time.sleep(5)
                    continue
                _struggling.add(model)
                if _working_model == model:
                    _working_model = None
            if r.status_code in (400, 401, 403):
                raise RuntimeError(f"Gemini {r.status_code}: {r.text[:200]}")  # bad key: no point retrying
            break
    raise RuntimeError("All Gemini models failed: " + "; ".join(errors))


def parse_json_response(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise


def fallback_analysis(it, reason):
    it.update(impact=it.get("impact") or "🟡 Medium", why=it.get("why") or reason, effect=it.get("effect") or "",
              summary_short=it.get("summary_short") or it.get("summary", "")[:160],
              category=it.get("category") or "News", ai_analyzed=False)


def analyze_with_ai(items, cache):
    """cache: {article_id: previous item dict}. Only new articles hit the API."""
    pending = []
    for it in items:
        prev = cache.get(it["id"])
        if prev and prev.get("ai_analyzed"):
            for f in AI_FIELDS:
                it[f] = prev.get(f)
            it["ai_analyzed"] = True
        else:
            pending.append(it)

    if not items:
        return items
    if not GEMINI_KEY:
        for it in pending:
            fallback_analysis(it, "AI analysis off — add the GEMINI_API_KEY secret to enable it.")
        return items

    print(f"  {len(items) - len(pending)} cached, {len(pending)} new to analyze")
    to_analyze = pending[:AI_MAX_NEW_ITEMS]
    started = time.monotonic()
    for start in range(0, len(to_analyze), GEMINI_BATCH):
        batch = to_analyze[start:start + GEMINI_BATCH]
        if time.monotonic() - started > AI_TIME_BUDGET:
            print(f"  … time budget reached, {len(to_analyze) - start} items deferred to next run")
            for it in to_analyze[start:]:
                fallback_analysis(it, "AI analysis pending — will retry next run.")
            break
        payload = [{"id": n, "title": i["title"], "sector": i["sector"], "summary": i["summary"][:300]}
                   for n, i in enumerate(batch)]
        prompt = f"""You are a news analyst. Analyze each of these {len(payload)} news items.
Return ONLY a JSON array with one object per item, each with exactly these keys:
- "id": the same integer id as the input item
- "impact": "High", "Medium" or "Low" (how many people / how much money / how lasting the consequences are)
- "why": why it matters, max 20 words
- "effect": who or what it affects and how, max 20 words
- "summary_short": a 1-2 sentence neutral summary
- "category": a specific 1-3 word category (e.g. "Market Crash", "AI Breakthrough", "Geopolitical Tension")

News items: {json.dumps(payload, ensure_ascii=False)}"""
        try:
            analyses = parse_json_response(gemini_generate(prompt))
            by_id = {}
            for a in analyses if isinstance(analyses, list) else []:
                try:
                    by_id[int(a.get("id"))] = a
                except (TypeError, ValueError):
                    continue
            for n, it in enumerate(batch):
                a = by_id.get(n)
                if not a:
                    fallback_analysis(it, "AI analysis pending — will retry next run.")
                    continue
                it.update(impact=normalize_impact(a.get("impact")), why=str(a.get("why", ""))[:200],
                          effect=str(a.get("effect", ""))[:200],
                          summary_short=str(a.get("summary_short", ""))[:400] or it["summary"][:160],
                          category=str(a.get("category", "News"))[:40] or "News", ai_analyzed=True)
            print(f"  ✓ Batch {start // GEMINI_BATCH + 1}: analyzed {len(by_id)}/{len(batch)} ({_working_model})")
        except Exception as e:
            print(f"  ✗ AI error: {e}")
            for it in batch:
                fallback_analysis(it, "AI analysis pending — will retry next run.")
    for it in pending[AI_MAX_NEW_ITEMS:]:
        fallback_analysis(it, "AI analysis pending — will retry next run.")
    return items


# ========== SNAPSHOTS & HISTORY ==========
def save_snapshot(data):
    HISTORY_DIR.mkdir(exist_ok=True)
    stamp = get_ist_time().strftime("%Y-%m-%d_%H-%M-%S")
    with open(HISTORY_DIR / f"news_{stamp}.json", "w") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    snapshots = sorted(HISTORY_DIR.glob("news_*.json"))
    for old in snapshots[:-MAX_SNAPSHOTS]:
        old.unlink()


def build_history_index():
    """Summarize every snapshot so the dashboard can chart impact/sentiment over time."""
    points = []
    for path in sorted(HISTORY_DIR.glob("news_*.json")):
        try:
            with open(path) as f:
                d = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        its = d.get("items", [])
        if not its:
            continue
        imp = defaultdict(int)
        sectors = defaultdict(int)
        for i in its:
            imp[normalize_impact(i.get("impact")).split()[-1]] += 1
            sectors[i.get("sector", "Unknown")] += 1
        scores = [i.get("sentiment_score") or 0 for i in its]
        points.append({
            "time": path.stem.replace("news_", ""),
            "count": len(its),
            "high": imp["High"], "medium": imp["Medium"], "low": imp["Low"],
            "avg_sentiment": round(sum(scores) / len(scores), 4),
            "positive": sum(1 for s in scores if s > 0.1),
            "negative": sum(1 for s in scores if s < -0.1),
            "sectors": dict(sectors),
        })
    with open(HISTORY_INDEX_FILE, "w") as f:
        json.dump({"generated": utc_now_iso(), "points": points}, f, indent=1)
    return points


def load_previous_items():
    try:
        with open(NEWS_FILE) as f:
            return {i["id"]: i for i in json.load(f).get("items", []) if i.get("id")}
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return {}


# ========== MAIN ==========
def main():
    print("[News Agent] Starting update cycle...")
    init_db()
    load_health()
    cache = load_previous_items()
    seen = set()

    print("[Fetch] RSS feeds...")
    rss_items = fetch_items(seen)
    print(f"  ✓ Got {len(rss_items)} RSS items")

    print("[Fetch] Reddit...")
    reddit_items = fetch_reddit_items(seen)
    print(f"  ✓ Got {len(reddit_items)} Reddit items")

    print("[Fetch] Social sources...")
    social_items = fetch_social_items(seen)
    print(f"  ✓ Got {len(social_items)} social items")

    items = rss_items + reddit_items + social_items
    save_health()

    if not items and cache:
        print("[Abort] No items fetched (network problem?) — keeping previous news.json")
        return

    print("[Process] Detecting near-duplicate stories...")
    pairs = find_similar_articles(items)
    attach_related(items, pairs)
    print(f"  ✓ Found {len(pairs)} similar-story pairs")

    print("[Process] Detecting trends...")
    trends = detect_trends(items)
    print(f"  ✓ Top {len(trends)} trends detected")

    print("[AI] Analyzing impact with Gemini...")
    items = analyze_with_ai(items, cache)

    print("[Fact-check] Flagging sensitive claims...")
    items = fact_checker.flag_disputed_claims(items, cache)
    fact_report = fact_checker.generate_fact_check_report(items)
    with open("fact_check_report.json", "w") as f:
        json.dump(fact_report, f, indent=2, ensure_ascii=False)
    print(f"  ✓ {fact_report['disputed_articles']} items flagged")

    if TRANSLATE_LANGS and GEMINI_KEY:
        print(f"[Translate] {', '.join(TRANSLATE_LANGS)}...")
        items = translator.translate_articles(items, TRANSLATE_LANGS, cache, gemini_generate)

    print("[DB] Saving to history database...")
    save_to_db(items)

    sector_order = {s: n for n, s in enumerate(SECTORS)}
    items.sort(key=lambda i: ({"🔴": 0, "🟡": 1, "🟢": 2}.get((i.get("impact") or "🟡")[0], 1),
                              sector_order.get(i["sector"], 99)))

    ist_time = get_ist_time()
    quiz = news_quiz.generate_quiz(items, 5)
    output = {
        "updated": ist_time.strftime("%Y-%m-%d %H:%M IST"),
        "updated_iso": utc_now_iso(),
        "count": len(items),
        "ai_model": _working_model if GEMINI_KEY else None,
        "translations": TRANSLATE_LANGS if GEMINI_KEY else [],
        "stats": {
            "rss": len(rss_items),
            "reddit": len(reddit_items),
            "social": len(social_items),
            "duplicates_found": len(pairs),
            "trends_detected": len(trends),
            "ai_analyzed": sum(1 for i in items if i.get("ai_analyzed")),
            "fact_check_flags": fact_report["disputed_articles"],
        },
        "trends": trends,
        "source_health": health_list(),
        "quiz": quiz,
        "items": items,
    }

    with open(NEWS_FILE, "w") as f:
        json.dump(output, f, indent=1, ensure_ascii=False)
    news_quiz.save_quiz(quiz)
    save_snapshot(output)
    points = build_history_index()
    pathlib.Path(".nojekyll").touch()

    print("[Email] Checking digest schedule...")
    email_digest.maybe_send_digest(items)

    print(f"[Complete] ✓ Updated news.json with {len(items)} items")
    print(f"[Complete] ✓ {len(points)} snapshots in history/")
    print(f"[Complete] ✓ Timestamp: {ist_time.strftime('%Y-%m-%d %H:%M:%S IST')}")


if __name__ == "__main__":
    main()
