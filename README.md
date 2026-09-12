# News Agent - AI-Powered News Aggregator

An intelligent news aggregation system that fetches, analyzes, and visualizes news from multiple sources using AI and machine learning.

## 🌟 Features

### Data Collection
- **30+ RSS Feeds** from BBC, Reuters, Bloomberg, Al Jazeera, TechCrunch, The Verge, and more
- **Reddit Integration** - Captures rising posts from relevant subreddits before mainstream media (30-60 min faster)
- **Social Sources** - Hacker News, Product Hunt trending
- **Automatic Updates** - Runs every 10 minutes via GitHub Actions

### AI-Powered Analysis
- **Impact Scoring** - Uses Google Gemini API to classify articles as High/Medium/Low impact
- **Sentiment Analysis** - Detects positive, neutral, and negative tones with confidence scores
- **Auto-Summarization** - Generates concise summaries and categorized insights
- **Keyword Extraction** - Identifies key topics from each article

### Smart Deduplication
- **Semantic Similarity Detection** - Uses TF-IDF vectorization to find near-duplicate stories
- **Content Hashing** - Prevents exact duplicate entries
- **Cross-sector Tracking** - Identifies same story reported across sectors

### Trend Detection
- **Trending Keywords** - Real-time trending topic extraction
- **Multi-sector Trends** - Shows which keywords span multiple news categories
- **Frequency Analysis** - Tracks keyword momentum over time

### Historical Tracking
- **Time-series Database** - SQLite stores all articles with analysis metadata
- **Snapshot Archive** - Timestamped JSON snapshots in `/history/` (keeps last 100)
- **Historical Analytics** - Track how impact/sentiment evolve

### Source Health Monitoring
- **Reliability Tracking** - Monitors success/failure rates for each RSS feed
- **Automatic Alerts** - Logs when sources become unavailable
- **Health Dashboard** - Visual indicator of source reliability

### Interactive Dashboard
- **Dark Mode** - Theme toggle with localStorage persistence
- **Advanced Filtering** - By sector, source, impact, sentiment, and free text search
- **Analytics Dashboard** - Charts for impact distribution, sentiment analysis, sector breakdown, source breakdown
- **Prediction Voting** - Users can validate AI predictions
- **Real-time Refresh** - Auto-updates every minute
- **Responsive Design** - Mobile-friendly interface

### Predictions & Voting
- **Impact Predictions** - AI predicts which stories will be most significant
- **User Validation** - Community voting on prediction accuracy
- **Accuracy Tracking** - Measures model performance over time

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- GitHub account with Actions enabled
- Google Gemini API key (free tier available at https://makersuite.google.com/app/apikey)

### Setup

1. **Clone or Fork the Repository**
   ```bash
   git clone https://github.com/wvub/news-agent.git
   cd news-agent
   ```

2. **Add Gemini API Secret**
   - Go to your repo Settings → Secrets and variables → Actions
   - Add `GEMINI_API_KEY` with your API key from https://makersuite.google.com/app/apikey

3. **Enable GitHub Pages**
   - Go to Settings → Pages
   - Source: Deploy from a branch
   - Branch: `main` / folder: `/ (root)`

4. **Run Locally (Optional)**
   ```bash
   pip install -r requirements.txt
   export GEMINI_API_KEY="your-key-here"
   python news_agent.py
   ```

5. **Access Your News Dashboard**
   - Visit `https://<your-username>.github.io/news-agent/`
   - Updates every 10 minutes automatically

## 📊 Data Structure

### `news.json` (Main Feed)
```json
{
  "updated": "2026-09-12 12:30 UTC",
  "count": 150,
  "stats": {
    "rss": 50,
    "reddit": 40,
    "social": 10,
    "duplicates_found": 5,
    "trends_detected": 12
  },
  "trends": [
    {
      "keyword": "AI",
      "frequency": 25,
      "sectors": ["Tech/AI", "Markets"],
      "article_count": 15
    }
  ],
  "source_health": [...],
  "items": [
    {
      "id": "hash123",
      "title": "Article Title",
      "sector": "Tech/AI",
      "source": "rss",
      "impact": "🔴 High",
      "why": "Affects millions of developers",
      "effect": "Tech sector: recruitment, hiring practices",
      "sentiment_label": "Positive 😊",
      "sentiment_score": 0.72,
      "keywords": ["AI", "regulation", "policy"],
      "summary_short": "New AI regulation announced..."
    }
  ]
}
```

### `news_history.db` (SQLite Database)
Stores full article history with:
- Sentiment analysis results
- Impact scores
- Keywords
- Timestamps
- Source reliability metrics

### `/history/` Directory
Timestamped snapshots: `news_2026-09-12_12-30-45.json`
- Keeps last 100 snapshots (≈16 hours of data at 10-min intervals)
- Enables time-series analysis and trend tracking

## 📈 Analytics Available

1. **Impact Distribution** - Doughnut chart of High/Medium/Low stories
2. **Sentiment Analysis** - Bar chart of positive/neutral/negative articles
3. **Sector Breakdown** - Articles per news category
4. **Source Distribution** - Pie chart showing contribution by source
5. **Trend Timeline** - Top keywords with mention frequency
6. **Source Health** - Success/failure rates for each feed
7. **Prediction Accuracy** - How well AI predictions match actual impact

## 🔧 Configuration

Edit `news_agent.py` to customize:

```python
SECTORS = {
    "World": [...],        # Add/remove RSS feeds
    "Markets": [...],
    # etc.
}

REDDIT_SUBS = {...}       # Add subreddits to monitor

MAX_PER_SECTOR = 8        # Articles per sector (default: 8)
REDDIT_MIN_SCORE = 20     # Min Reddit score to include
```

## 🌐 Supported News Sectors

- **World** - BBC, Al Jazeera, Reuters
- **Markets** - MarketWatch, Yahoo Finance, Bloomberg
- **Tech/AI** - TechCrunch, The Verge, Ars Technica
- **Crypto** - CoinDesk, Cointelegraph
- **Science** - ScienceDaily, Space.com, Nature
- **Health** - WHO, Medical News Today, NIH

## 🔐 Privacy & Security

- All news data is **public** (hosted on GitHub Pages)
- Gemini API key stored in **GitHub Secrets** (not in code)
- No user data collected or stored
- Open source — audit the code yourself

## 📚 Use Cases

- **Investment Research** - Track market/crypto trends in real-time
- **Competitive Intelligence** - Monitor competitor mentions
- **Risk Management** - Identify emerging threats early
- **Content Curation** - Auto-generated news digest for your website
- **Academic Research** - Historical database of tagged articles
- **AI Training Data** - Labeled dataset of news with sentiment/impact

## 🛠️ Troubleshooting

### Workflow not updating
- Check GitHub Actions under "Actions" tab
- Verify `GEMINI_API_KEY` secret is set
- Check for Python or dependency errors in workflow logs

### No impact analysis showing
- Ensure `GEMINI_API_KEY` is valid and has quota remaining
- Check Gemini API console at https://makersuite.google.com/app/apikey

### Dashboard not loading
- Wait 5 minutes after first setup (for workflow to run)
- Clear browser cache
- Verify GitHub Pages is enabled

### Database errors
- Delete `news_history.db` to reset
- Re-run workflow manually via "Run workflow" button

## 📈 Performance Stats

- **Fetch Time**: ~30 seconds (30+ RSS feeds + Reddit)
- **Analysis Time**: ~20 seconds (Gemini API calls)
- **Total Run Time**: ~60 seconds per 10-minute cycle
- **Data Size**: ~5-10 MB per 24 hours (100 snapshots)
- **API Costs**: Free (Gemini free tier, GitHub Actions free for public repos)

## 🎓 Learning Resources

- [Feedparser Docs](https://pythonhosted.org/feedparser/)
- [Google Gemini API](https://ai.google.dev/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [GitHub Pages Setup](https://docs.github.com/en/pages/getting-started-with-github-pages)

## 📝 License

MIT License - Use freely for personal or commercial projects

## 🤝 Contributing

Contributions welcome! Ideas:
- Add more RSS feeds
- Integrate new data sources (Twitter API, news APIs, etc.)
- Improve sentiment analysis
- Add email digest functionality
- Create mobile app
- Build recommendation engine

## 📞 Support

Open an issue on GitHub for bugs, feature requests, or questions!

---

**Made with ❤️ by Armaan**
