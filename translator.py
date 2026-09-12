"""
Translation module for News Agent
Provides multi-language support
"""
import json
import os
import requests

SUPPORTED_LANGUAGES = {
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ru": "Russian",
    "ja": "Japanese",
    "zh": "Chinese",
    "ko": "Korean",
    "ar": "Arabic",
}

def translate_with_gemini(text, target_language, gemini_key=None):
    """Translate text using Google Gemini API"""
    if not gemini_key:
        return None
    
    try:
        import google.generativeai as genai
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        
        prompt = f"Translate this to {target_language} (return only the translation, no explanation):\n\n{text[:500]}"
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Translation error: {e}")
        return None

def translate_articles(items, target_languages=["es", "fr"], gemini_key=None):
    """Translate articles to multiple languages"""
    if not gemini_key:
        return items
    
    for item in items:
        item["translations"] = {}
        
        for lang_code in target_languages:
            title_trans = translate_with_gemini(
                item.get("title", ""),
                SUPPORTED_LANGUAGES.get(lang_code, "English"),
                gemini_key
            )
            
            if title_trans:
                item["translations"][lang_code] = {
                    "title": title_trans,
                    "language": SUPPORTED_LANGUAGES.get(lang_code, "Unknown")
                }
    
    return items

def generate_multilingual_feed(news_data, target_languages=["es", "fr"]):
    """Generate news feed with translations"""
    gemini_key = os.environ.get("GEMINI_API_KEY")
    
    items = news_data.get("items", [])
    translated_items = translate_articles(items[:10], target_languages, gemini_key)
    
    multilingual_feed = {
        "updated": news_data.get("updated"),
        "languages": target_languages,
        "items": translated_items,
    }
    
    return multilingual_feed

if __name__ == "__main__":
    try:
        with open("news.json") as f:
            data = json.load(f)
    except:
        data = {"items": []}
    
    multilingual = generate_multilingual_feed(data, ["es", "fr", "de"])
    
    with open("news_multilingual.json", "w") as f:
        json.dump(multilingual, f, indent=2)
    
    print("✓ Multilingual feed generated")
