# Configuration for News Agent

Everything except `GEMINI_API_KEY` is optional — each feature switches itself on
when its settings are present and is skipped quietly otherwise.

## GitHub Secrets (Settings → Secrets and variables → Actions → Secrets)
| Secret | Enables |
|---|---|
| `GEMINI_API_KEY` | AI impact analysis, summaries, categories, translations. Get one at https://aistudio.google.com/apikey |
| `GOOGLE_FACTCHECK_KEY` | Looks flagged stories up in the Google Fact Check Tools API (enable the API in Google Cloud Console) |
| `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` | Reliable Reddit access via OAuth. Reddit often blocks anonymous requests from GitHub's servers; without these the agent falls back to Reddit RSS, which may also be blocked. Create a "script" app at https://www.reddit.com/prefs/apps |
| `SMTP_SERVER`, `SMTP_PORT`, `SENDER_EMAIL`, `SENDER_PASSWORD` | Email digest (e.g. `smtp.gmail.com`, `587`, your address, an app password) |

## GitHub Variables (same page → Variables tab)
| Variable | Purpose |
|---|---|
| `GEMINI_MODEL` | Pin a model. By default the agent tries `gemini-flash-latest`, then `gemini-flash-lite-latest`, then the newest other Flash models your key can use (discovered automatically), skipping any that are overloaded |
| `TRANSLATE_LANGS` | Comma-separated language codes for headline translation, e.g. `es,fr,hi`. Adds a language picker to the dashboard |

## Email digest
Add addresses to `emails` in `subscribers.json`. `settings.frequency` is `daily` or `weekly`
(`weekday`: 0 = Monday), and `time` + `timezone` set when it goes out. The workflow runs every
10 minutes and sends once per period after that time; `digest_state.json` records the last send.
Preview locally with `python email_digest.py --preview`.

## Local run
```bash
pip install -r requirements.txt
export GEMINI_API_KEY="your-api-key-here"
python news_agent.py
python -m http.server 8000   # then open http://localhost:8000
```

## Generated files
- `news.json` — the dashboard feed
- `history/` — timestamped snapshots (last 100) and `history_index.json` (summary used by the History tab)
- `source_health.json` — per-feed success/failure counts, persisted between runs
- `daily_quiz.json` — the day's quiz (also embedded in `news.json`)
- `fact_check_report.json` — stories flagged for fact-checking
- `news_history.db` — local SQLite archive (gitignored, so it only grows on machines where you run the agent yourself)
