"""
Personalization engine for News Agent
Tracks user preferences and recommends articles
"""
import json
import os
from datetime import datetime

def load_user_profile(user_id="default"):
    """Load user preferences"""
    profile_file = f".profiles/{user_id}.json"
    
    if os.path.exists(profile_file):
        with open(profile_file) as f:
            return json.load(f)
    
    return {
        "user_id": user_id,
        "preferred_sectors": [],
        "preferred_sources": [],
        "read_history": [],
        "liked_articles": [],
        "disliked_articles": [],
        "created_at": datetime.utcnow().isoformat(),
    }

def save_user_profile(profile, user_id="default"):
    """Save user preferences"""
    os.makedirs(".profiles", exist_ok=True)
    
    profile_file = f".profiles/{user_id}.json"
    with open(profile_file, "w") as f:
        json.dump(profile, f, indent=2)

def track_click(user_id, article_id, article_title, sector):
    """Track article click"""
    profile = load_user_profile(user_id)
    
    profile["read_history"].append({
        "article_id": article_id,
        "title": article_title,
        "sector": sector,
        "clicked_at": datetime.utcnow().isoformat()
    })
    
    # Update preferred sectors (simple frequency)
    if sector not in profile["preferred_sectors"]:
        profile["preferred_sectors"].append(sector)
    
    save_user_profile(profile, user_id)
    return profile

def get_recommendations(user_id, all_articles, num_recommendations=10):
    """Get personalized article recommendations"""
    profile = load_user_profile(user_id)
    
    if not profile["preferred_sectors"]:
        # Return top articles if no preference yet
        return sorted(
            all_articles,
            key=lambda x: (x.get("impact", "").count("🔴"), x.get("published", "")),
            reverse=True
        )[:num_recommendations]
    
    # Recommend articles from preferred sectors
    recommended = [
        a for a in all_articles
        if a.get("sector") in profile["preferred_sectors"]
    ]
    
    # Sort by impact and newness
    recommended = sorted(
        recommended,
        key=lambda x: (x.get("impact", "").count("🔴"), x.get("published", "")),
        reverse=True
    )
    
    return recommended[:num_recommendations]

def similar_articles(article, all_articles, num_similar=5):
    """Find similar articles to a given article"""
    article_keywords = set(article.get("keywords", []))
    article_sector = article.get("sector", "")
    
    similar = []
    for other in all_articles:
        if other.get("id") == article.get("id"):
            continue
        
        other_keywords = set(other.get("keywords", []))
        
        # Calculate similarity score
        keyword_overlap = len(article_keywords & other_keywords)
        sector_match = 1 if other.get("sector") == article_sector else 0
        
        score = keyword_overlap * 2 + sector_match
        
        if score > 0:
            similar.append({
                "article": other,
                "similarity_score": score
            })
    
    return sorted(similar, key=lambda x: x["similarity_score"], reverse=True)[:num_similar]

if __name__ == "__main__":
    # Example usage
    profile = track_click("user123", "art-001", "AI Breakthrough", "Tech/AI")
    print(f"✓ Tracked click for user: {profile['user_id']}")
