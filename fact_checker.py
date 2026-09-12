"""
Fact-checking integration for News Agent
Checks articles against fact-check APIs
"""
import json
import requests
from datetime import datetime

def check_with_google_factcheck(claim):
    """Check claim against Google Fact Check API"""
    try:
        url = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
        params = {
            "query": claim[:200],
            "languageCode": "en-US",
            "key": "YOUR_GOOGLE_FACTCHECK_KEY"  # Get from Google Cloud Console
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if data.get("claims"):
            return {
                "status": "found",
                "claims": data["claims"][:3],
                "source": "Google Fact Check API"
            }
        return {"status": "not_found", "claims": []}
    except Exception as e:
        print(f"Fact-check error: {e}")
        return {"status": "error", "error": str(e)}

def flag_disputed_claims(items):
    """Flag items that mention disputed claims"""
    for item in items:
        title = item.get("title", "")
        summary = item.get("summary", "")
        
        # Simple keyword matching for common disputed topics
        disputed_keywords = [
            "election fraud", "vaccine", "climate", "moon landing", 
            "5g coronavirus", "jewish space laser", "flat earth"
        ]
        
        for keyword in disputed_keywords:
            if keyword.lower() in title.lower() or keyword.lower() in summary.lower():
                item["fact_check_needed"] = True
                item["disputed_topic"] = keyword
                break
    
    return items

def generate_fact_check_report(items):
    """Generate report of items needing fact-checking"""
    disputed = [i for i in items if i.get("fact_check_needed")]
    
    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "total_articles": len(items),
        "disputed_articles": len(disputed),
        "disputed_items": [
            {
                "title": i.get("title"),
                "topic": i.get("disputed_topic"),
                "source": i.get("source"),
                "link": i.get("link")
            }
            for i in disputed
        ]
    }
    
    return report

if __name__ == "__main__":
    try:
        with open("news.json") as f:
            data = json.load(f)
            items = data.get("items", [])
    except:
        items = []
    
    flagged = flag_disputed_claims(items)
    report = generate_fact_check_report(flagged)
    
    with open("fact_check_report.json", "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"✓ Fact-check report: {report['disputed_articles']} disputed items found")
