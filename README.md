# AI Curriculum Ingest

A single-user Telegram bot that ingests AI/ML content from tweets, URLs, screenshots, and raw text, classifies it with Claude, and appends structured entries to a master `curriculum.md` learning document.

Self-hosted. Single user (configured Telegram user ID). No public access, no auth layer beyond the user-ID check.

## What it does

You send the bot:

- A Twitter/X status URL — fetched via the fxtwitter API; images on the tweet are pulled and run through Claude Vision.
- Any URL — extracted via a headless Playwright browser.
- Raw pasted text (≥100 characters).
- A photo / screenshot — Claude Vision extracts text, diagram descriptions, and chart data.

Claude classifies the content into one of your curriculum sections, summarises it, lists 5–10 learning components, and appends an entry to `curriculum.md`. A SHA-256 prefix manifest at the bottom of the file prevents duplicates.

## What it is not

- A multi-user product. The bot silently drops every message that is not from the configured user ID.
- A web service. There is no HTTP surface.
- A database-backed system. The "database" is the markdown file itself; git is the audit log.

## Setup

### 1. Prerequisites

- Python 3.11+
- A VPS or always-on machine (the bot uses long-poll, so no public URL is required)
- A Telegram bot token from `@BotFather`
- An Anthropic API key

### 2. Install

```bash
git clone <your-fork-url> ai-curriculum-ingest
cd ai-curriculum-ingest
python3 -m venv .venv
source .venv/bin/activate
pip install anthropic playwright python-telegram-bot
playwright install chromium
```

### 3. Configure

```bash
cp .env.example .env
# Then edit .env and set:
#   TELEGRAM_BOT_TOKEN          (from @BotFather)
#   TELEGRAM_ALLOWED_USER_ID    (numeric ID of the only user permitted — DM @userinfobot)
#   ANTHROPIC_API_KEY           (https://console.anthropic.com/)
```

### 4. Seed the curriculum file

Create `curriculum.md` with your starting sections. A minimal template:

```markdown
# AI Learning Curriculum

## Learner Profile
(Free-text description of you, your background, what you are studying.)

---

## 1. Your First Section
**Status:** NOT STARTED
**Covers:** What this section is about.

### Ingested Resources
_None yet._

---

## Uncategorised
**Status:** ALWAYS ACTIVE
**Covers:** Anything Claude cannot route to a specific section.

### Ingested Resources
_None yet._

---

## Manifest
| Hash | Source Type | Source | Title | Section | Date |
|---|---|---|---|---|---|
```

Then update `CURRICULUM_SECTIONS` in `ingest.py` to match your section names and one-line descriptions. Claude uses that dict to pick the correct section for each ingest.

### 5. Run (local)

```bash
export $(grep -v '^#' .env | xargs)
python3 bot.py
```

## Telegram commands

- Send any URL, raw text, or photo — it gets ingested.
- `/start` — usage help
- `/status` — counts per section
- `/sections` — list all sections
- `/recent` — last 5 ingested items
- `/search <term>` — search entries
- `/rename Old | New` — rename a section
- `/add_section Name | Description` — add a section
- `/delete <title>` — delete an entry (partial match)
- `/move <title> | Section` — move an entry
- `/export` — get `curriculum.md` as a file

## Architecture

```
Telegram message
    ↓
bot.py (long-poll, user-ID-gated)
    ↓
ingest.py: classify_input → extract → content_hash → dedupe
    ↓
Claude Sonnet (vision + classification)
    ↓
append entry to curriculum.md + write manifest row
```

See `ingest.py` for the full pipeline; the file is heavily commented.

## VPS deployment (systemd example)

`/etc/systemd/system/curriculum-bot.service`:

```
[Unit]
Description=AI Curriculum Ingest Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/ai-curriculum-ingest
EnvironmentFile=/opt/ai-curriculum-ingest/.env
ExecStart=/opt/ai-curriculum-ingest/.venv/bin/python3 /opt/ai-curriculum-ingest/bot.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now curriculum-bot
journalctl -u curriculum-bot -f      # live logs
sudo systemctl restart curriculum-bot   # after code changes
```

## Security

`.env` is in `.gitignore`. The bot silently drops messages from any user ID other than `TELEGRAM_ALLOWED_USER_ID` — no reply, no log, no DB write. See `SECURITY.md` for the full posture.

## Licence

MIT. See `LICENSE`.
