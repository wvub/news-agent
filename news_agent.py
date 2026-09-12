#!/usr/bin/env python3
"""
Comprehensive News Agent - Fetches, analyzes, and serves curated news
"""
import feedparser
import json
import os
import re
import requests
import pathlib
import sqlite3
import hashlib
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import google.generativeai as genai
from textblob import TextBlob
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ========== TIMEZONE CONFIG ==========
IST = timezone(timedelta(hours=5, minutes=30))  # Indian Standard Time (UTC+5:30)

def get_ist_time():
    """Get current time in Indian Standard Time"""
    return datetime.now(IST)

# ========== CONFIG ==========
SECTORS = {
    "World": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://feeds.reuters.com/reuters/worldNews",
    ],
    "Markets": [
        "https://feeds.marketwatch.com/marketwatch/topstories/",
        "https://finance.yahoo.com/news/rssindex",
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
    ],
    "Science": [
        "https://www.sciencedaily.com/rss/top/science.xml",
        "https://www.space.com/feeds/all",
        "https://feeds.nature.com/nature/rss/current",
    ],
    "Health": [
        "https://www.who.int/rss-feeds/news-english.xml",
        "https://www.medicalnewstoday.com/rss",
        "https://feeds.nih.gov/news/news-rss/",
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

SOCIAL_SOURCES = {
    "hacker_news": "https://news.ycombinator.com/rss",
    "producthunt": "https://www.producthunt.com/feed.xml",
}

REDDIT_HEADERS = {"User-Agent": "personal-news-agent/2.0 (by Armaan)"}
REDDIT_PER_SUB = 5
REDDIT_MIN_SCORE = 20
MAX_PER_SECTOR = 8
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

# Configure Gemini
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

# ========== DATABASE SETUP ==========
DB_PATH = "news_history.db"

def init_db():
    """Initialize SQLite database for historical tracking"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS articles (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        link TEXT,
        sector TEXT,
        source TEXT,
        summary TEXT,
        published TEXT,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        sentiment_score REAL,
        sentiment_label TEXT,
        impact TEXT,
        why TEXT,
        effect TEXT,
        content_hash TEXT,
        keywords TEXT,
        related_articles TEXT,
        embedding TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS trends (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        keyword TEXT,
        frequency INTEGER,
        sector TEXT,
        first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        articles TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS source_health (
        source TEXT PRIMARY KEY,
        last_success TIMESTAMP,
        last_failure TIMESTAMP,
        failure_count INTEGER DEFAULT 0,
        success_count INTEGER DEFAULT 0
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        article_id TEXT,
        predicted_impact TEXT,
        user_votes INTEGER DEFAULT 0,
        actual_impact TEXT,
        accuracy REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    conn.commit()
    conn.close()

# ========== SENTIMENT ANALYSIS ==========
def analyze_sentiment(text):
    """Analyze sentiment of text using TextBlob"""
    try:
        blob = TextBlob(text[:500])
        polarity = blob.sentiment.polarity
        
        if polarity > 0.1:
            label = "Positive 😊"
        elif polarity < -0.1:
            label = "Negative 😞"
        else:
            label = "Neutral 😐"
        
        return polarity, label
    except:
        return 0.0, "Neutral 😐"

# ========== DUPLICATE & SIMILARITY DETECTION ==========
def compute_content_hash(text):
    """Compute hash of content for deduplication"""
    return hashlib.md5(text.lower().encode()).hexdigest()

def find_similar_articles(new_items, threshold=0.7):
    """Find semantically similar articles using TF-IDF"""
    if len(new_items) < 2:
        return defaultdict(list)
    
    texts = [f"{item['title']} {item['summary']}" for item in new_items]
    try:
        vectorizer = TfidfVectorizer(stop_words='english', max_features=100)
        tfidf_matrix = vectorizer.fit_transform(texts)
        similarity_matrix = cosine_similarity(tfidf_matrix)
        
        similar_groups = defaultdict(list)
        for i in range(len(similarity_matrix)):
            for j in range(i + 1, len(similarity_matrix)):
                if similarity_matrix[i][j] > threshold:
                    similar_groups[i].append(j)
        
        return similar_groups
    except:
        return defaultdict(list)

# ========== TREND DETECTION ==========
def extract_keywords(text, max_keywords=5):
    """Extract keywords from text"""
    words = re.findall(r'\b[a-z]{4,}\b', text.lower())
    freq = defaultdict(int)
    for word in words:
        if word not in ['that', 'this', 'from', 'with', 'have', 'been', 'said', 'will']:
            freq[word] += 1
    return sorted(freq.items(), key=lambda x: x[1], reverse=True)[:max_keywords]

def detect_trends(items):
    """Detect trending keywords and topics"""
    all_keywords = defaultdict(lambda: {'count': 0, 'sectors': set(), 'articles': []})
    
    for idx, item in enumerate(items):
        keywords = extract_keywords(f"{item['title']} {item['summary']}")
        for keyword, freq in keywords:
            all_keywords[keyword]['count'] += freq
            all_keywords[keyword]['sectors'].add(item['sector'])
            all_keywords[keyword]['articles'].append(idx)
    
    trends = sorted(
        [(k, v['count'], len(v['sectors']), v['articles']) 
         for k, v in all_keywords.items() if v['count'] > 2],
        key=lambda x: x[1],
        reverse=True
    )[:15]
    
    return trends

# ========== RSS FETCHING ==========
def fetch_items():
    """Fetch news from RSS feeds"""
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
                    sentiment_score, sentiment_label = analyze_sentiment(f"{title} {summary}")
                    
                    items.append({
                        "id": compute_content_hash(title + link),
                        "sector": sector,
                        "title": title,
                        "link": link,
                        "summary": summary,
                        "published": entry.get("published", ""),
                        "source": "rss",
                        "sentiment_score": sentiment_score,
                        "sentiment_label": sentiment_label,
                        "keywords": [kw[0] for kw in extract_keywords(f"{title} {summary}")],
                    })
                    count += 1
            except Exception as e:
                log_source_failure(url, sector, str(e))
    
    return items

# ========== REDDIT FETCHING ==========
def fetch_reddit_items():
    """Fetch rising posts from Reddit"""
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
                    
                    sentiment_score, sentiment_label = analyze_sentiment(f"{title} {summary}")
                    
                    items.append({
                        "id": compute_content_hash(title + link),
                        "sector": sector,
                        "title": title,
                        "link": link,
                        "summary": summary,
                        "published": "",
                        "source": "reddit",
                        "sentiment_score": sentiment_score,
                        "sentiment_label": sentiment_label,
                        "keywords": [kw[0] for kw in extract_keywords(f"{title} {summary}")],
                    })
                
                log_source_success(f"r/{sub}", sector)
            except Exception as e:
                log_source_failure(f"r/{sub}", sector, str(e))
    
    return items

# ========== SOCIAL & TRENDING SOURCES ==========
def fetch_social_items():
    """Fetch from Hacker News and Product Hunt"""
    items = []
    
    try:
        # Hacker News
        feed = feedparser.parse(SOCIAL_SOURCES["hacker_news"])
        for entry in feed.entries[:5]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "")
            summary = entry.get("summary", "")[:300]
            
            sentiment_score, sentiment_label = analyze_sentiment(f"{title} {summary}")
            
            items.append({
                "id": compute_content_hash(title + link),
                "sector": "Tech/AI",
                "title": title,
                "link": link,
                "summary": f"[Hacker News] {summary}",
                "published": entry.get("published", ""),
                "source": "hacker_news",
                "sentiment_score": sentiment_score,
                "sentiment_label": sentiment_label,
                "keywords": [kw[0] for kw in extract_keywords(f"{title} {summary}")],
            })
        
        # Product Hunt
        feed = feedparser.parse(SOCIAL_SOURCES["producthunt"])
        for entry in feed.entries[:5]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "")
            summary = entry.get("summary", "")[:300]
            
            sentiment_score, sentiment_label = analyze_sentiment(f"{title} {summary}")
            
            items.append({
                "id": compute_content_hash(title + link),
                "sector": "Tech/AI",
                "title": title,
                "link": link,
                "summary": f"[Product Hunt] {summary}",
                "published": entry.get("published", ""),
                "source": "producthunt",
                "sentiment_score": sentiment_score,
                "sentiment_label": sentiment_label,
                "keywords": [kw[0] for kw in extract_keywords(f"{title} {summary}")],
            })
    except Exception as e:
        print(f"Social sources error: {e}")
    
    return items

# ========== AI ANALYSIS ==========
def analyze_with_ai(items):
    """Use Gemini API for impact analysis and summarization"""
    if not GEMINI_KEY or not items:
        for it in items:
            it.update(
                impact="🟡 Medium",
                why="AI key not set",
                effect="Add GEMINI_API_KEY to enable analysis",
                summary_short=it.get("summary", "")[:100]
            )
        return items
    
    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        
        batch = [
            {
                "title": i["title"],
                "sector": i["sector"],
                "summary": i["summary"][:200]
            }
            for i in items[:50]
        ]
        
        prompt = f"""Analyze these {len(batch)} news items. Return ONLY a JSON array with no markdown or explanation.
Each object must have exactly:
- "title": exact title from input
- "impact": one of "🔴 High", "🟡 Medium", "🟢 Low"
- "why": max 20 words
- "effect": max 20 words
- "summary_short": 1-2 sentence summary
- "category": specific category (e.g., "Market Crash", "AI Breakthrough", "Geopolitical Tension")

News items: {json.dumps(batch)}"""
        
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        # Clean up markdown
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        analyses = json.loads(text)
        amap = {a["title"]: a for a in analyses}
        
        for it in items:
            a = amap.get(it["title"])
            if a:
                it.update(
                    impact=a.get("impact", "🟡 Medium"),
                    why=a.get("why", ""),
                    effect=a.get("effect", ""),
                    summary_short=a.get("summary_short", ""),
                    category=a.get("category", "News")
                )
            else:
                it.update(
                    impact="🟡 Medium",
                    why="Analysis pending",
                    effect="",
                    summary_short=it.get("summary", "")[:100],
                    category="News"
                )
    except Exception as e:
        print(f"AI error: {e}")
        for it in items:
            it.update(
                impact="🟡 Medium",
                why="Error",
                effect="",
                summary_short=it.get("summary", "")[:100],
                category="News"
            )
    
    return items

# ========== DATABASE OPERATIONS ==========
def save_to_db(items):
    """Save articles to database"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    for item in items:
        try:
            c.execute('''INSERT OR REPLACE INTO articles 
                        (id, title, link, sector, source, summary, published, 
                         sentiment_score, sentiment_label, impact, why, effect, 
                         content_hash, keywords)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                     (item.get("id"),
                      item.get("title"),
                      item.get("link"),
                      item.get("sector"),
                      item.get("source"),
                      item.get("summary"),
                      item.get("published"),
                      item.get("sentiment_score", 0.0),
                      item.get("sentiment_label", "Neutral"),
                      item.get("impact"),
                      item.get("why"),
                      item.get("effect"),
                      compute_content_hash(item.get("title", "")),
                      json.dumps(item.get("keywords", []))))
        except Exception as e:
            print(f"DB save error: {e}")
    
    conn.commit()
    conn.close()

def log_source_success(source, sector):
    """Log successful source fetch"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO source_health 
                (source, last_success, success_count)
                VALUES (?, ?, 
                       COALESCE((SELECT success_count FROM source_health WHERE source=?), 0) + 1)''',
             (source, datetime.now(timezone.utc), source))
    conn.commit()
    conn.close()

def log_source_failure(source, sector, error):
    """Log failed source fetch"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO source_health 
                (source, last_failure, failure_count)
                VALUES (?, ?, 
                       COALESCE((SELECT failure_count FROM source_health WHERE source=?), 0) + 1)''',
             (source, datetime.now(timezone.utc), source))
    print(f"Source error {source}: {error}")
    conn.commit()
    conn.close()

def get_source_health():
    """Get health status of all sources"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT source, last_success, last_failure, success_count, failure_count FROM source_health ORDER BY last_success DESC')
    results = c.fetchall()
    conn.close()
    return results

# ========== HISTORICAL SNAPSHOTS ==========
def save_snapshot(data):
    """Save timestamped snapshot of news data"""
    history_dir = pathlib.Path("history")
    history_dir.mkdir(exist_ok=True)
    
    timestamp = get_ist_time().strftime("%Y-%m-%d_%H-%M-%S")
    snapshot_file = history_dir / f"news_{timestamp}.json"
    
    with open(snapshot_file, "w") as f:
        json.dump(data, f, indent=1)
    
    # Keep only last 100 snapshots
    snapshots = sorted(history_dir.glob("news_*.json"))
    for old_snapshot in snapshots[:-100]:
        old_snapshot.unlink()

# ========== MAIN EXECUTION ==========
def main():
    print("[News Agent] Starting update cycle...")
    init_db()
    
    # Fetch from all sources
    print("[Fetch] RSS feeds...")
    rss_items = fetch_items()
    print(f"  ✓ Got {len(rss_items)} RSS items")
    
    print("[Fetch] Reddit...")
    reddit_items = fetch_reddit_items()
    print(f"  ✓ Got {len(reddit_items)} Reddit items")
    
    print("[Fetch] Social sources...")
    social_items = fetch_social_items()
    print(f"  ✓ Got {len(social_items)} social items")
    
    items = rss_items + reddit_items + social_items
    
    # Analyze sentiment
    print(f"[Process] Analyzing sentiment...")
    
    # Find similar articles
    print("[Process] Detecting duplicates...")
    similar = find_similar_articles(items, threshold=0.75)
    print(f"  ✓ Found {len(similar)} duplicate groups")
    
    # Detect trends
    print("[Process] Detecting trends...")
    trends = detect_trends(items)
    print(f"  ✓ Top {len(trends)} trends detected")
    
    # AI analysis
    print("[AI] Analyzing impact with Gemini...")
    items = analyze_with_ai(items)
    
    # Save to database
    print("[DB] Saving to history database...")
    save_to_db(items)
    
    # Prepare output with IST timestamp
    ist_time = get_ist_time()
    output = {
        "updated": ist_time.strftime("%Y-%m-%d %H:%M IST"),
        "count": len(items),
        "stats": {
            "rss": len(rss_items),
            "reddit": len(reddit_items),
            "social": len(social_items),
            "duplicates_found": len(similar),
            "trends_detected": len(trends),
        },
        "trends": [
            {
                "keyword": t[0],
                "frequency": t[1],
                "sectors": list(t[2]) if isinstance(t[2], set) else t[2],
                "article_count": len(t[3])
            }
            for t in trends
        ],
        "source_health": [
            {
                "source": h[0],
                "last_success": str(h[1]),
                "last_failure": str(h[2]),
                "success_count": h[3],
                "failure_count": h[4]
            }
            for h in get_source_health()
        ],
        "items": items,
    }
    
    # Save main file
    with open("news.json", "w") as f:
        json.dump(output, f, indent=1)
    
    # Save snapshot
    save_snapshot(output)
    
    # Create .nojekyll
    pathlib.Path(".nojekyll").touch()
    
    print(f"[Complete] ✓ Updated news.json with {len(items)} items")
    print(f"[Complete] ✓ Snapshots saved to history/ directory")
    print(f"[Complete] ✓ Timestamp: {ist_time.strftime('%Y-%m-%d %H:%M:%S IST')}")

if __name__ == "__main__":
    main()
