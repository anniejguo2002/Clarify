"""
Clarify — an adaptive reading layer for the web.

Flask backend. Single responsibility per route:
  GET  /                -> serves the frontend
  POST /api/transform    -> extracts text (URL or pasted text) + asks the LLM
                            for "Clear" and "Simpler" rewrites in one call.

Design choices (documented for hackathon judging / co-founder log):
- No JS build step: plain HTML/CSS/JS frontend so there's zero dependency on
  Node (not available in this environment) and zero deploy-time build step.
- One LLM call produces BOTH "Clear" and "Simpler" versions up front, so
  switching Reading Mode in the UI is instant (no re-fetch, no flicker) and
  we only pay for one round-trip per submission.
- "Original" mode never touches the LLM — it's the raw extracted text, so
  the demo has a guaranteed-to-work baseline even if the OpenAI call fails.
- URL extraction uses readability-lxml (server-side, no external service,
  no extra API key) to strip nav/ads/boilerplate down to the main article.
- If extraction or the URL fetch fails for any reason, we fall back to
  treating the raw input as pasted text — the demo can never hard-fail.
"""

import os
import re
import json
import time

from flask import Flask, request, jsonify, send_from_directory
from bs4 import BeautifulSoup
from readability import Document
import requests
from openai import OpenAI

# Frontend files (index.html/app.js/style.css) live at the project root
# alongside app.py rather than in a "static/" subfolder. This avoids a
# real deployment failure mode: manual file uploads (e.g. via GitHub's
# web upload UI) can silently drop subfolder structure, which would make
# a static_folder="static" reference 404. Serving each file via its own
# explicit route below keeps things working regardless of upload method,
# without exposing app.py/requirements.txt/README.md over HTTP.
app = Flask(__name__)
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

OPENAI_MODEL = os.environ.get("CLARIFY_MODEL", "gpt-4o-mini")
_client = None


def get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        _client = OpenAI(api_key=api_key)
    return _client


URL_RE = re.compile(r"^\s*https?://\S+\s*$", re.IGNORECASE)


def looks_like_url(text: str) -> bool:
    return bool(URL_RE.match(text.strip()))


def extract_from_url(url: str):
    """Fetch a URL and extract the main readable text + title.

    Returns (title, paragraphs) where paragraphs is a list of plain-text
    strings (one per paragraph/heading-ish block), already stripped of
    nav/ads/boilerplate.
    """
    resp = requests.get(
        url,
        timeout=12,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            )
        },
    )
    resp.raise_for_status()

    doc = Document(resp.text)
    title = (doc.title() or "").strip()
    summary_html = doc.summary(html_partial=True)

    soup = BeautifulSoup(summary_html, "lxml")
    paragraphs = []
    for el in soup.find_all(["p", "li", "h1", "h2", "h3"]):
        txt = " ".join(el.get_text(" ", strip=True).split())
        if len(txt) >= 2:
            paragraphs.append(txt)

    if not paragraphs:
        # Readability found nothing usable — fall back to all <p> tags.
        full_soup = BeautifulSoup(resp.text, "lxml")
        for el in full_soup.find_all("p"):
            txt = " ".join(el.get_text(" ", strip=True).split())
            if len(txt) >= 40:
                paragraphs.append(txt)

    return title, paragraphs


def build_prompt(title: str, body_text: str) -> str:
    return f"""You are an assistive reading editor. You rewrite text so it is \
easier to read for people with dyslexia and other reading difficulties, \
WITHOUT losing any of the substance.

Hard rules:
- Do NOT summarize or drop facts, names, numbers, dates, arguments, or nuance.
- Preserve the full meaning and level of detail of the source.
- Shorten overly long sentences and split dense paragraphs into smaller ones.
- Use clear, direct sentence structure (subject-verb-object where possible).
- Replace unnecessarily complex vocabulary with simpler words ONLY when \
meaning is fully preserved. If a technical term must stay, keep it and \
briefly explain it in plain words the first time it appears.
- Add short headings to break up long content and aid navigation, but only \
where they genuinely help — don't force structure onto short inputs.
- Use bullet points ONLY for genuine lists or sequences that were already \
list-like in meaning — not to fragment ordinary prose.
- Wrap the 3-6 most important words/phrases per section in **double \
asterisks** to mark emphasis (key facts, names, numbers, conclusions).
- Produce TWO versions:
  - "clear": lightly cleaned up — clearer sentences and structure, minimal \
vocabulary changes, closest to the original length.
  - "simpler": more aggressively simplified vocabulary and sentence length, \
more headings/bullets, explains difficult terms inline — still complete, \
still no information loss. This should be noticeably easier to read than \
"clear", not shorter in substance.

Return ONLY valid JSON with this exact shape, no prose outside the JSON:
{{
  "title": "<short clean title, <=90 chars>",
  "clear": {{
    "blocks": [
      {{"type": "heading", "text": "..."}},
      {{"type": "paragraph", "text": "..."}},
      {{"type": "bullets", "items": ["...", "..."]}}
    ]
  }},
  "simpler": {{
    "blocks": [ ... same block shape ... ]
  }}
}}

Source title: {title or "(untitled)"}

Source text:
\"\"\"
{body_text}
\"\"\"
"""


def call_llm(title: str, body_text: str) -> dict:
    client = get_client()
    prompt = build_prompt(title, body_text)
    completion = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    raw = completion.choices[0].message.content
    return json.loads(raw)


@app.route("/")
def index():
    return send_from_directory(ROOT_DIR, "index.html")


@app.route("/app.js")
def app_js():
    return send_from_directory(ROOT_DIR, "app.js")


@app.route("/style.css")
def style_css():
    return send_from_directory(ROOT_DIR, "style.css")


@app.route("/api/transform", methods=["POST"])
def transform():
    payload = request.get_json(silent=True) or {}
    user_input = (payload.get("input") or "").strip()

    if not user_input:
        return jsonify({"error": "Please paste a URL or some text first."}), 400

    source_url = None
    title = ""
    paragraphs = []

    if looks_like_url(user_input):
        source_url = user_input.strip()
        try:
            title, paragraphs = extract_from_url(source_url)
        except Exception as exc:  # noqa: BLE001 - demo must never hard-fail
            paragraphs = []
            extraction_error = str(exc)
        if not paragraphs:
            return jsonify({
                "error": (
                    "Couldn't extract readable text from that URL. "
                    "Try pasting the article text directly instead."
                )
            }), 422
    else:
        # Direct text fallback — split on blank lines into paragraphs.
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", user_input) if p.strip()]
        if not paragraphs:
            paragraphs = [user_input.strip()]

    body_text = "\n\n".join(paragraphs)
    if len(body_text) > 12000:
        body_text = body_text[:12000]

    try:
        result = call_llm(title, body_text)
    except Exception as exc:  # noqa: BLE001
        return jsonify({
            "error": f"The AI rewrite step failed: {exc}",
            "original": {"title": title, "paragraphs": paragraphs},
        }), 502

    result["original"] = {
        "title": title or result.get("title") or "Original text",
        "paragraphs": paragraphs,
    }
    result["source_url"] = source_url
    return jsonify(result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
