# Configuration for News Agent

## Environment Variables
```bash
export GEMINI_API_KEY="your-api-key-here"
```

## GitHub Secrets
Add these to Settings → Secrets and variables → Actions:
- `GEMINI_API_KEY` - Get from https://makersuite.google.com/app/apikey

## Optional Email Setup
For email digests, add to GitHub Secrets:
- `SMTP_SERVER` - e.g., smtp.gmail.com
- `SMTP_PORT` - e.g., 587
- `SENDER_EMAIL` - Your email address
- `SENDER_PASSWORD` - App-specific password

## Database
- `news_history.db` - SQLite database (auto-created, added to .gitignore)

## Cache & Temporary
- `.profiles/` - User preference profiles (added to .gitignore)
- `/history/` - Timestamped snapshots (keep last 100)
