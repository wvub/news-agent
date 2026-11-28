"""
Email digest for News Agent.

Sends a digest to everyone in subscribers.json once per day (or week) at the
configured time. Needs these environment variables / GitHub secrets:
    SMTP_SERVER, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD
Optional: DASHBOARD_URL (defaults to the GitHub Pages URL of this repo).
Run `python email_digest.py --preview` to write digest_preview.html without sending.
"""
import json
import os
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

SUBSCRIBERS_FILE = "subscribers.json"
STATE_FILE = "digest_state.json"
IMPACT_RANK = {"🔴": 0, "🟡": 1, "🟢": 2}


def dashboard_url():
    if os.environ.get("DASHBOARD_URL"):
        return os.environ["DASHBOARD_URL"]
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner}.github.io/{name}/"
    return "index.html"


def load_subscribers():
    try:
        with open(SUBSCRIBERS_FILE) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"  subscribers.json unreadable ({e}); no digest sent")
        return {"emails": [], "settings": {}}
    data.setdefault("emails", [])
    data.setdefault("settings", {})
    return data


def save_subscribers(subscribers):
    with open(SUBSCRIBERS_FILE, "w") as f:
        json.dump(subscribers, f, indent=2)


def get_top_articles(items=None, limit=10):
    if items is None:
        try:
            with open("news.json") as f:
                items = json.load(f).get("items", [])
        except (FileNotFoundError, json.JSONDecodeError):
            return []
    return sorted(items, key=lambda x: (IMPACT_RANK.get((x.get("impact") or "🟡")[0], 1),
                                        -(abs(x.get("sentiment_score") or 0))))[:limit]


def generate_html_digest(articles, digest_type="daily"):
    high = [a for a in articles if "🔴" in (a.get("impact") or "")]
    rest = [a for a in articles if a not in high]

    def card(a, full=True):
        e = lambda k, d="": escape(str(a.get(k) or d))
        body = ""
        if full:
            body = (f'<p style="color:#555;margin:8px 0">{e("summary_short", a.get("summary", "")[:200])}</p>'
                    f'<p style="margin:4px 0"><b>Why:</b> {e("why")}</p>'
                    f'<p style="margin:4px 0"><b>Effect:</b> {e("effect")}</p>')
        return (f'<div style="border-left:4px solid #3b82f6;padding:12px 15px;margin:10px 0;background:#f9fafb">'
                f'<div style="font-weight:bold">{e("impact")} {e("title")}</div>{body}'
                f'<div><span style="display:inline-block;padding:3px 8px;background:#dbeafe;color:#1e40af;'
                f'border-radius:3px;font-size:.85em;margin:6px 6px 6px 0">{e("sector")}</span>'
                f'<span style="display:inline-block;padding:3px 8px;background:#eee;border-radius:3px;'
                f'font-size:.85em">{e("source_name", a.get("source", ""))}</span></div>'
                f'<a href="{escape(a.get("link") or "#", quote=True)}" style="color:#3b82f6">Read full article →</a></div>')

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<html><body style="font-family:Arial,sans-serif;color:#333;margin:0">
<div style="background:linear-gradient(135deg,#3b82f6,#10b981);color:#fff;padding:20px;text-align:center">
<h1 style="margin:0">📰 Xynex News — {digest_type.title()} Digest</h1><p>Your AI-curated news summary</p></div>
<div style="max-width:600px;margin:0 auto;padding:20px">
<h2>🔴 High Impact Stories ({len(high)})</h2>{''.join(card(a) for a in high[:5]) or '<p>No high-impact stories right now.</p>'}
<h2>📰 Other Top Stories</h2>{''.join(card(a, False) for a in rest[:max(0, 10 - len(high[:5]))])}
<div style="text-align:center;color:#999;padding:20px;border-top:1px solid #e5e7eb;margin-top:20px">
<p>📊 <a href="{escape(dashboard_url(), quote=True)}">View full dashboard</a></p>
<p style="font-size:.85em">Reply "unsubscribe" to stop receiving this digest • Generated {now}</p>
</div></div></body></html>"""


def generate_text_digest(articles, digest_type="daily"):
    lines = [f"📰 XYNEX NEWS - {digest_type.upper()} DIGEST", "=" * 50, ""]
    for i, a in enumerate(articles[:10], 1):
        lines += [f"{i}. {a.get('impact', '')} {a.get('title', '')}",
                  f"   Sector: {a.get('sector', '')} | Source: {a.get('source_name', a.get('source', ''))}",
                  f"   Why: {a.get('why', '')}", f"   Link: {a.get('link', '#')}", ""]
    lines += ["=" * 50, f"Dashboard: {dashboard_url()}",
              f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"]
    return "\n".join(lines)


def send_digest(smtp_server, smtp_port, sender_email, sender_password, recipients,
                digest_html, digest_text, digest_type="daily"):
    try:
        port = int(smtp_port)
        server = smtplib.SMTP_SSL(smtp_server, port, timeout=30) if port == 465 else smtplib.SMTP(smtp_server, port, timeout=30)
        if port != 465:
            server.starttls()
        server.login(sender_email, sender_password)
        sent = 0
        for recipient in recipients:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"📰 Xynex News — {digest_type.title()} Digest"
            msg["From"] = sender_email
            msg["To"] = recipient
            msg.attach(MIMEText(digest_text, "plain", "utf-8"))
            msg.attach(MIMEText(digest_html, "html", "utf-8"))
            try:
                server.sendmail(sender_email, recipient, msg.as_string())
                sent += 1
            except smtplib.SMTPException as e:
                print(f"  ✗ Failed to send to a subscriber: {e}")
        server.quit()
        print(f"  ✓ Digest sent to {sent}/{len(recipients)} subscribers")
        return sent > 0
    except Exception as e:
        print(f"  ✗ Email error: {e}")
        return False


def _tz(name):
    if not name or name.upper() == "UTC":
        return timezone.utc
    if name.upper() == "IST":
        return timezone(timedelta(hours=5, minutes=30))
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        return timezone.utc


def digest_due(settings, state, now=None):
    """True when the scheduled time has passed and no digest was sent for this period."""
    tz = _tz(settings.get("timezone", "UTC"))
    now = (now or datetime.now(timezone.utc)).astimezone(tz)
    frequency = settings.get("frequency", "daily")
    period = now.strftime("%G-W%V") if frequency == "weekly" else now.strftime("%Y-%m-%d")
    hh, mm = (int(x) for x in str(settings.get("time", "08:00")).split(":")[:2])
    if now < now.replace(hour=hh, minute=mm, second=0, microsecond=0):
        return False, period
    if frequency == "weekly" and now.weekday() != int(settings.get("weekday", 0)):
        return False, period
    return state.get("last_period") != period, period


def maybe_send_digest(items, force=False):
    subs = load_subscribers()
    emails = [e for e in subs["emails"] if isinstance(e, str) and "@" in e]
    if not emails:
        print("  No subscribers — skipping digest")
        return False
    cfg = {k: os.environ.get(k, "") for k in ("SMTP_SERVER", "SMTP_PORT", "SENDER_EMAIL", "SENDER_PASSWORD")}
    if not all(cfg[k] for k in ("SMTP_SERVER", "SENDER_EMAIL", "SENDER_PASSWORD")):
        print("  SMTP secrets not set — skipping digest")
        return False
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}
    settings = subs["settings"]
    due, period = digest_due(settings, state)
    if not (due or force):
        print("  Digest not due yet")
        return False
    kind = settings.get("frequency", "daily")
    articles = get_top_articles(items, int(settings.get("max_articles", 10)))
    ok = send_digest(cfg["SMTP_SERVER"], cfg["SMTP_PORT"] or 587, cfg["SENDER_EMAIL"], cfg["SENDER_PASSWORD"],
                     emails, generate_html_digest(articles, kind), generate_text_digest(articles, kind), kind)
    if ok:
        with open(STATE_FILE, "w") as f:
            json.dump({"last_period": period, "sent_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "recipients": len(emails)}, f, indent=2)
    return ok


if __name__ == "__main__":
    articles = get_top_articles(None, 10)
    if "--preview" in sys.argv or not articles:
        with open("digest_preview.html", "w") as f:
            f.write(generate_html_digest(articles))
        print(generate_text_digest(articles))
        print("\n✓ Wrote digest_preview.html")
    else:
        maybe_send_digest(articles, force="--force" in sys.argv)
