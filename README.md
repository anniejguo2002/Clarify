# Clarify

**Every webpage, rewritten for the way you read.**

Clarify turns hard-to-read online text — articles, essays, dense pages — into
a personalized, easier-to-read version, without cutting any of the
substance. Paste a link or paste text, click **"Make it easier to read,"**
and get back the same information in clearer language and a calmer layout.

## The problem

Most reading tools on the web either leave text exactly as written (hard for
people with dyslexia and other reading difficulties) or summarize it (which
throws information away). Neither solves the actual problem: the same page
should be readable by everyone, without losing what it says.

## How Clarify works

1. **Extract** — if you paste a URL, Clarify fetches the page and extracts
   the main article text server-side, stripping navigation, ads, menus, and
   boilerplate (via `readability-lxml`). If you paste text directly, that
   text is used as-is — this is the guaranteed-to-work fallback.
2. **Transform** — the extracted text is sent to an LLM with instructions to
   preserve every fact, name, number, and argument while: shortening
   overly long sentences, breaking up dense paragraphs, simplifying
   unnecessary vocabulary, explaining hard terms inline, and adding
   headings/bullets only where they genuinely help.
3. **Read** — the result is shown in a calm, minimal reading interface with
   controls to adjust how it's presented.

Both the "Clear" and "Simpler" rewrites are generated in a single request,
so switching between reading modes afterward is instant — no re-fetching.

## Core features

- **Input**: paste a URL or paste text directly (always works, never blocks
  the demo on extraction failure).
- **Reading modes**: Original (untouched extracted text) / Clear (light
  cleanup) / Simpler (more aggressive simplification) — switch instantly.
- **Reader controls**: adjustable text size, line spacing (Normal/Wide), and
  a Focus mode that dims everything except the paragraph you're reading.
- **No information loss**: this is not a summarizer — the transformed
  output preserves the substance of the source.

## Tech stack

- **Backend**: Python, Flask
- **Extraction**: `readability-lxml` + `BeautifulSoup` (server-side, no
  external extraction service or extra API key)
- **AI rewriting**: OpenAI Chat Completions API (`gpt-4o-mini` by default),
  one call returns both reading-mode versions as structured JSON
- **Frontend**: plain HTML/CSS/JS — no framework, no build step
- **Deployment target**: Render (or any platform that runs a Python/WSGI app)

This stack was chosen deliberately for a hackathon timeline: no build
pipeline, no bundler, no extra infrastructure — just a server and static
files.

## Running it locally

**Requirements**: Python 3.9+

```bash
# 1. Install dependencies
pip3 install -r requirements.txt

# 2. Set your OpenAI API key (never commit this — see Environment variables below)
export OPENAI_API_KEY=your-key-here

# 3. Run the app
python3 app.py
```

The app will be available at `http://localhost:5001`.

## Environment variables

| Variable          | Required | Description                                             |
|--------------------|----------|----------------------------------------------------------|
| `OPENAI_API_KEY`   | Yes      | Your OpenAI API key. Used server-side only — never sent to the browser. |
| `CLARIFY_MODEL`    | No       | OpenAI model to use for rewriting (default: `gpt-4o-mini`). |
| `PORT`             | No       | Port to run the server on (default: `5001`; most PaaS platforms set this automatically). |
| `FLASK_DEBUG`      | No       | Set to `1` to enable Flask debug mode locally. Leave unset in production. |

No `.env` file is included or required to be committed — set these as
environment variables in your shell or on your deployment platform.

## How AdaL acted as the AI co-founder

AdaL (this project's AI technical co-founder) made and executed the
following decisions under the hackathon time constraint:

- **Chose the stack**: detected that the target machine had no Node/npm/
  Vercel CLI available, and pivoted from a JS-framework plan to a
  Flask + vanilla HTML/CSS/JS architecture — no build step, fastest path to
  a working demo, same "simplest reliable stack" principle the brief asked
  for.
- **Designed the extraction/transform/read pipeline**: picked
  `readability-lxml` for server-side article extraction (no extra API key,
  no external service dependency) and designed a single LLM call that
  returns both "Clear" and "Simpler" versions at once, so mode-switching in
  the UI is instant.
- **Wrote the product-preservation prompt**: the core instruction to the
  LLM explicitly forbids summarizing or dropping facts, and requires
  explaining rather than deleting difficult terms — directly encoding the
  product's "not a summarizer" principle into the AI behavior.
- **Built and implemented** the Flask backend, the reading UI (reader
  modes, text size, line spacing, focus mode via `IntersectionObserver`),
  and all styling.
- **Tested end-to-end** before and after billing was enabled on the OpenAI
  account: text input, URL extraction against a live page, both reading
  modes, and error paths (empty input, unreachable URL, malformed request)
  — confirming graceful degradation in every failure case.
- **Ran a security pass**: confirmed the API key is read server-side only
  and never appears in any client-side file or API response, verified
  `.gitignore` excludes `.env`/secrets, and scanned the repo for
  accidentally committed credentials before the first commit.
- **Prepared deployment**: added `requirements.txt`, `Procfile`, and
  confirmed the exact build/start commands and required environment
  variables for a Render deployment.
