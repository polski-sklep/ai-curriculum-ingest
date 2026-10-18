# AI Curriculum Ingest

A Telegram bot that takes AI/ML material — a tweet, a URL, pasted text, or a screenshot — and appends a structured entry to a markdown learning log, `curriculum.md`.

You run it yourself. `bot.py` long-polls Telegram (`app.run_polling()`), so the machine does not need a public URL. Apart from `/start`, every handler checks the sender against `TELEGRAM_ALLOWED_USER_ID`.

Claude (`claude-sonnet-4-20250514`) writes a title, a short summary, learning components, a level, and a section. The section name comes from `CURRICULUM_SECTIONS` in `ingest.py`. The entry is inserted under the matching `##` heading in `curriculum.md`. A 12-character SHA-256 prefix of the extracted text is stored in the manifest table in that file, and the same hash is used to skip duplicates.

## Stack

- Python. Nothing in the repo pins a version. `bot.py` and `ingest.py` use built-in generics such as `tuple[str, str]` and `list[dict]`, which require Python 3.9 or newer.
- `python-telegram-bot` — long polling in `bot.py` (`ApplicationBuilder`, `run_polling`).
- `anthropic` — classification and image reading in `ingest.py`. The client is `anthropic.Anthropic()` with no arguments.
- `playwright` — headless Chromium for ordinary URLs, and as a fallback when a tweet comes back short.
- `pdfplumber` — listed in `requirements.txt`. Neither `bot.py` nor `ingest.py` imports it.
- fxtwitter — `extract_twitter` requests `https://api.fxtwitter.com` plus the tweet path, with `User-Agent: CurriculumIngest/1.0`. No Twitter API key is read.

The curriculum is the markdown file next to the scripts (`CURRICULUM_PATH` in `ingest.py`). There is no database client in the repo.

## Layout

| Path | What it is |
|---|---|
| `bot.py` | Telegram handlers and the long-polling process |
| `ingest.py` | Classify, extract, call Claude, read and write `curriculum.md` |
| `requirements.txt` | `anthropic`, `python-telegram-bot`, `playwright`, `pdfplumber` (no version pins) |
| `.env.example` | Names of the three environment variables |
| `SECURITY.md` | How to report a vulnerability, and the project's secret and access notes |
| `LICENSE` | MIT, copyright 2026 Jacob Kowalewski |
| `curriculum.md` | Created by you at runtime. Listed in `.gitignore`, not in this repo |

`.gitignore` also ignores `.env`, virtualenvs, and `test.png`. A comment there mentions `curriculum_template.md`. That file is not in the repository.

## Setup

### Prerequisites

- Python 3.9 or newer (see above; the repo does not pin a version)
- A Telegram bot token from @BotFather
- The numeric Telegram user id that may use the bot (`.env.example` points at @userinfobot)
- An Anthropic API key

URL ingest and the short-tweet fallback launch Chromium through Playwright, so the browser build has to be installed as well.

### Install

```bash
git clone https://github.com/polski-sklep/ai-curriculum-ingest
cd ai-curriculum-ingest
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### Configure

```bash
cp .env.example .env
```

Edit `.env`, then load it into the environment. Neither script reads the file. `bot.py` only calls `os.environ.get`.

```bash
set -a
source .env
set +a
```

### Create `curriculum.md`

`ingest.py` reads and writes `curriculum.md` in the same directory as itself. The file has to exist before a command or an ingest runs.

Section headings must match the keys of `CURRICULUM_SECTIONS` exactly (`## 3. RAG Architecture`, and so on). `append_to_curriculum` looks for that heading, then a line `### Ingested Resources` within the next 10 lines. A following `_None yet._` on one of the next three lines is replaced by the entry; otherwise the entry is inserted on the next line. If the heading is missing, the entry is written under `## Uncategorised` instead. `/status` and `/sections` skip `## Learner Profile` and `## Manifest`.

A file that satisfies the parser:

```markdown
# AI Learning Curriculum

## Learner Profile
Free-text notes. This heading is ignored by /status and /sections.

---

## 3. RAG Architecture
**Status:** NOT STARTED
**Covers:** Retrieval-augmented generation.

### Ingested Resources
_None yet._

---

## Uncategorised
**Status:** ALWAYS ACTIVE
**Covers:** Anything that does not match a section heading.

### Ingested Resources
_None yet._

---

## Manifest
| Hash | Source Type | Source | Title | Section | Date |
|---|---|---|---|---|---|
```

Add a block like the RAG one for each section you want entries to land in. The names already in `CURRICULUM_SECTIONS` are:

- 0. Multi-Agent Simulation
- 1. Vibetunnel
- 2. LangChain
- 2a. Anthropic Complete Guide to Building Skills for Claude
- 3. RAG Architecture
- 4. Vector Database Implementation
- 5. Embedding Pipelines
- 6. Agent Memory Systems
- 7. Context Window Optimisation
- 8. Structured Output Pipelines
- 9. Model Routing Logic
- 10. Local Model Deployment
- 11. AI Guardrails & Validation
- 12. MCP Integration
- 13. Batch Processing Architecture
- 14. LLM Observability & Logging
- 15. Cursor
- 16. ClayLead
- 17. Agent-Assisted Development
- 18. Synthetic Discourse
- Uncategorised

`/add_section` and `/rename` update `curriculum.md` on disk and the in-memory `CURRICULUM_SECTIONS` dict for the current process. A restart loads the dict from `ingest.py` again. To keep a new or renamed section in classification after a restart, edit that dict.

The classification prompt in `process_with_claude` also includes a fixed learner blurb: about nine months of AI/ML building, Vibetunnel and LangChain done, a multi-agent system underway (Python, FastAPI, the Claude API, pgvector), with RAG, vector databases, and embeddings next. Change that string in `ingest.py` if it does not describe you.

## Environment variables

Names only. Values belong in `.env` (gitignored) or the process environment. See `.env.example`.

| Name | Where it is read | Role |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | `bot.py`, `os.environ.get("TELEGRAM_BOT_TOKEN")` | Telegram bot token. If it is missing, `main()` prints an error and returns. |
| `TELEGRAM_ALLOWED_USER_ID` | `bot.py`, `int(os.environ.get("TELEGRAM_ALLOWED_USER_ID", "0"))` | Numeric Telegram user id compared with `update.effective_user.id`. If the variable is unset, the value is `0`. An empty or non-integer value raises `ValueError` while `bot.py` is importing. |
| `ANTHROPIC_API_KEY` | Not named in the Python files. `.env.example` lists it. `ingest.py` constructs `anthropic.Anthropic()` with no API key argument. | Key for the Anthropic client used by classification and image extraction. |

## Running

From the repo directory, with the virtualenv active and the variables exported:

```bash
python3 bot.py
```

Log lines go to stderr at INFO (`curriculum_bot`), with the time, level, and message.

You can also call the pipeline once without Telegram. That still needs `ANTHROPIC_API_KEY` and a `curriculum.md` in the repo directory:

```bash
python3 ingest.py "https://x.com/user/status/123"
python3 ingest.py "https://example.com/post"
python3 ingest.py "paste raw text here..."
python3 ingest.py /path/to/screenshot.png
```

With no argument, `ingest.py` prints those four forms and exits.

There is no test suite, and no test runner is listed in `requirements.txt`.

## What you can send

`classify_input` in `ingest.py` decides the type:

- A Twitter/X status URL. The message must start with `http://` or `https://`, then `twitter.com` or `x.com`, a username, `/status/`, and a numeric id. `classify_input` uses `re.match`, so text after the id still counts as a tweet, and the whole message is what gets fetched. fxtwitter supplies the tweet text and, when present, the quoted tweet. Photos are downloaded and passed through the same image prompt as a screenshot, and that text is appended to the tweet. Chromium then loads the status URL when the payload is a single line, or when `split("\n", 2)[-1]` (stripped) is shorter than 80 characters (`TWITTER_MIN_TEXT_LENGTH`). If the page text is still under 80 characters, ingest returns an error and asks you to paste the text.
- Any other string that starts with `http://` or `https://`. Playwright launches headless Chromium, waits for `networkidle` (15 second timeout) plus two seconds, strips nav, footer, aside, header, and a few ad and sidebar selectors, and reads `article`, then `main`, then `body`.
- Raw text of at least 100 characters. Shorter text that is not a URL or an image path returns `ERROR: Cannot classify input: ...`. The stored source id is `pasted_text`.
- A path to an existing `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, or `.bmp` file. Claude is asked for the visible text, diagrams, charts, and concepts.

A Telegram photo is downloaded to `/tmp/curriculum_screenshot.jpg` and then ingested as that path. The bot has no handler for documents, video, or other attachments.

Claude sees at most the first 6000 characters of the extracted text. Content the model marks as not relevant to AI/ML learning is not written; the bot replies `SKIPPED:` plus the reason. Before calling Claude, ingest hashes the extracted text and returns `DUPLICATE:` when that 12-character hash is already in the manifest. `append_to_curriculum` checks the hash again before writing.

## Telegram commands

`/start` replies with a short help text and does not check the user id. Every other handler checks `update.effective_user.id` against `TELEGRAM_ALLOWED_USER_ID`. A mismatch gets the reply `Not authorised.` and is not logged.

| Command | Behaviour |
|---|---|
| `/start` | Usage help |
| `/status` | Count of manifest rows, then sections with counts, then empty sections |
| `/sections` | Section headings, one per line, excluding Learner Profile and Manifest |
| `/recent` | Last 5 manifest rows, newest first |
| `/search <term>` | Titles that contain the term (entry headings and the manifest). The reply is `No results for '...'` when nothing matches |
| `/rename Old \| New` | Rename a `##` heading and the matching `\| old name \|` cells. An unknown name produces suggestions when a partial match exists |
| `/add_section Name \| Description` | Insert a section (status `NOT STARTED`) just before the `---` that precedes Uncategorised, or before `## Manifest` if there is no Uncategorised heading |
| `/delete <title>` | Delete one entry by partial title match against the manifest. Several matches ask you to be more specific |
| `/move <title> \| Section` | Move one entry to an existing `##` heading and update its manifest row |
| `/export` | Send the current `curriculum.md` as a file |

Text that is not a command is ingested. The bot replies `Processing...` for text and `Processing screenshot...` for a photo, then the result (`ADDED: ...`, `DUPLICATE:`, `SKIPPED:`, or `ERROR:`).

## Security

`.env` is gitignored. Credentials are environment variables. See `SECURITY.md` for reporting a vulnerability and for what the project sends to Anthropic.

## Licence

MIT. See `LICENSE`. Copyright (c) 2026 Jacob Kowalewski.
