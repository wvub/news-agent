"""
Translation module for News Agent.

Enabled by setting TRANSLATE_LANGS (e.g. "es,fr,hi") alongside GEMINI_API_KEY.
Titles and short summaries are translated in batches with Gemini; results are
cached per article so each article is translated only once.
"""
import json
import os
import re

SUPPORTED_LANGUAGES = {
    "es": "Spanish", "fr": "French", "de": "German", "it": "Italian", "pt": "Portuguese",
    "ru": "Russian", "ja": "Japanese", "zh": "Chinese (Simplified)", "ko": "Korean",
    "ar": "Arabic", "hi": "Hindi", "bn": "Bengali", "ur": "Urdu", "ta": "Tamil",
}
BATCH = 20
MAX_NEW_PER_RUN = 60  # per language, to protect API quota


def translate_articles(items, target_languages, cache, generate):
    """generate(prompt) -> str is the Gemini caller from news_agent."""
    langs = [l for l in target_languages if l in SUPPORTED_LANGUAGES]
    for item in items:
        prev = (cache.get(item["id"]) or {}).get("translations") or {}
        item["translations"] = {l: prev[l] for l in langs if l in prev}

    for lang in langs:
        todo = [i for i in items if lang not in i["translations"]][:MAX_NEW_PER_RUN]
        for start in range(0, len(todo), BATCH):
            batch = todo[start:start + BATCH]
            payload = [{"id": n, "title": i["title"], "summary": i.get("summary_short") or i["summary"][:200]}
                       for n, i in enumerate(batch)]
            prompt = (f"Translate the title and summary of each item into {SUPPORTED_LANGUAGES[lang]}. "
                      'Return ONLY a JSON array of objects with keys "id", "title", "summary".\n\n'
                      + json.dumps(payload, ensure_ascii=False))
            try:
                for t in parse_json_response(generate(prompt)):
                    n = int(t.get("id", -1))
                    if 0 <= n < len(batch) and t.get("title"):
                        batch[n]["translations"][lang] = {"title": t["title"], "summary": t.get("summary", "")}
            except Exception as e:
                print(f"  ✗ Translation error ({lang}): {e}")
    return items


def parse_json_response(text):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def generate_multilingual_feed(news_data, target_languages):
    """Standalone helper: build news_multilingual.json from an existing news.json."""
    from news_agent import gemini_generate
    items = news_data.get("items", [])
    cache = {i["id"]: i for i in items}
    return {
        "updated": news_data.get("updated"),
        "languages": target_languages,
        "items": translate_articles(items, target_languages, cache, gemini_generate),
    }


if __name__ == "__main__":
    if not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("Set GEMINI_API_KEY first")
    with open("news.json") as f:
        data = json.load(f)
    langs = [l for l in os.environ.get("TRANSLATE_LANGS", "es,fr,de").split(",") if l]
    with open("news_multilingual.json", "w") as f:
        json.dump(generate_multilingual_feed(data, langs), f, indent=2, ensure_ascii=False)
    print("✓ Multilingual feed generated")
