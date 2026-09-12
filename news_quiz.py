"""
News Quiz Generator - Auto-generate daily trivia from news feed
"""
import json
import random
from datetime import datetime, timezone

def generate_quiz(num_questions=5):
    """Generate quiz questions from today's news"""
    try:
        with open("news.json") as f:
            data = json.load(f)
            items = data.get("items", [])
    except:
        return []
    
    if not items:
        return []
    
    # Select random high-impact articles
    high_impact = [i for i in items if "🔴" in i.get("impact", "")]
    articles = random.sample(high_impact or items, min(num_questions, len(items)))
    
    quiz = []
    for article in articles:
        title = article.get("title", "")
        sector = article.get("sector", "")
        impact = article.get("impact", "")
        why = article.get("why", "")
        
        # Create multiple choice question
        question = {
            "question": f"What sector is this news about: \"{title[:50]}...\"?",
            "options": [
                sector,
                random.choice(["World", "Markets", "Tech/AI", "Crypto", "Science", "Health"]),
                random.choice(["World", "Markets", "Tech/AI", "Crypto", "Science", "Health"]),
            ],
            "answer": sector,
            "difficulty": "easy"
        }
        
        random.shuffle(question["options"])
        quiz.append(question)
    
    return {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "questions": quiz,
        "total": len(quiz)
    }

def save_quiz(quiz):
    """Save quiz to file"""
    with open("daily_quiz.json", "w") as f:
        json.dump(quiz, f, indent=2)
    print(f"✓ Quiz saved: {quiz['total']} questions")

if __name__ == "__main__":
    quiz = generate_quiz(5)
    if quiz:
        save_quiz(quiz)
        for i, q in enumerate(quiz["questions"], 1):
            print(f"\n{i}. {q['question']}")
            for j, opt in enumerate(q["options"], 1):
                print(f"   {j}) {opt}")
