"""
News Quiz Generator - daily trivia built from the news feed.
The quiz is stable for a whole (UTC) day and refreshed the next day.
"""
import json
import random
from datetime import datetime, timezone

QUIZ_FILE = "daily_quiz.json"


def _load_existing():
    try:
        with open(QUIZ_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def generate_quiz(items=None, num_questions=5, force=False):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    existing = _load_existing()
    if not force and existing and existing.get("date") == today and existing.get("questions"):
        return existing

    if items is None:
        try:
            with open("news.json") as f:
                items = json.load(f).get("items", [])
        except (FileNotFoundError, json.JSONDecodeError):
            items = []
    if not items:
        return {"date": today, "questions": [], "total": 0}

    rng = random.Random(today)  # deterministic per day
    sectors = sorted({i["sector"] for i in items if i.get("sector")})
    pool = [i for i in items if "🔴" in (i.get("impact") or "")] or items
    if len(pool) < num_questions:
        pool = items
    picks = rng.sample(pool, min(num_questions, len(pool)))
    all_titles = [i["title"] for i in items]

    questions = []
    for n, art in enumerate(picks):
        title, sector = art["title"], art["sector"]
        if n % 2 == 0 or len(all_titles) < 4:
            options = [sector] + rng.sample([s for s in sectors if s != sector], min(3, len(sectors) - 1))
            q = {"question": f'Which sector does this story belong to: "{title[:90]}"?', "answer": sector}
        else:
            others = [i for i in items if i["sector"] != sector] or [i for i in items if i is not art]
            wrong = [o["title"] for o in rng.sample(others, min(3, len(others)))]
            options = [title] + wrong
            q = {"question": f"Which of these was a {sector} headline today?", "answer": title}
        rng.shuffle(options)
        q.update(options=options, explanation=art.get("why") or art.get("summary_short") or "",
                 link=art.get("link", ""), difficulty="easy" if n % 2 == 0 else "medium")
        questions.append(q)

    return {"date": today, "questions": questions, "total": len(questions)}


def save_quiz(quiz):
    with open(QUIZ_FILE, "w") as f:
        json.dump(quiz, f, indent=2, ensure_ascii=False)
    print(f"✓ Quiz saved: {quiz['total']} questions")


if __name__ == "__main__":
    quiz = generate_quiz(force=True)
    save_quiz(quiz)
    for i, q in enumerate(quiz["questions"], 1):
        print(f"\n{i}. {q['question']}")
        for j, opt in enumerate(q["options"], 1):
            print(f"   {j}) {opt}")
