"""
AI Curriculum Ingestion Pipeline
Step 1: Input Classification (screenshot, twitter, url, text)
Step 2: Twitter/X Extraction (via fxtwitter API, with image + Playwright fallback)
Step 3: Generic URL Extraction (via Playwright)
Step 4: Claude API Processing (curriculum analysis)
Step 5: Curriculum File Writing (append to curriculum.md)
Step 6: Main ingest() entry point
Step 7: Screenshot Extraction (via Claude Vision API)
Step 8: Curriculum Management (rename, add, delete, move, search, status, sections, recent)
"""

import os
import re
import json
import hashlib
import asyncio
import base64
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen, Request, urlretrieve
from urllib.parse import urlparse

import anthropic
from playwright.async_api import async_playwright


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CURRICULUM_PATH = os.path.join(os.path.dirname(__file__), "curriculum.md")
TWITTER_MIN_TEXT_LENGTH = 80
RAW_TEXT_MIN_LENGTH = 100


# ---------------------------------------------------------------------------
# Step 1: Input Classification
# ---------------------------------------------------------------------------

def classify_input(raw: str) -> tuple[str, str]:
    stripped = raw.strip()

    if os.path.isfile(stripped):
        ext = Path(stripped).suffix.lower()
        if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"):
            return ("screenshot", stripped)

    twitter_pattern = r"https?://(www\.)?(twitter\.com|x\.com)/\w+/status/\d+"
    if re.match(twitter_pattern, stripped):
        return ("twitter", stripped)

    if stripped.startswith("http://") or stripped.startswith("https://"):
        return ("url", stripped)

    if len(stripped) >= RAW_TEXT_MIN_LENGTH:
        return ("text", stripped)

    raise ValueError(f"Cannot classify input: {stripped[:100]}")


# ---------------------------------------------------------------------------
# Step 2: Twitter/X Extraction
# ---------------------------------------------------------------------------

def extract_twitter(url: str) -> dict:
    parsed = urlparse(url)
    api_url = f"https://api.fxtwitter.com{parsed.path}"

    req = Request(api_url, headers={"User-Agent": "CurriculumIngest/1.0"})

    try:
        with urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as e:
        return {
            "source_type": "twitter",
            "source_id": url,
            "raw_text": f"[ERROR] Failed to fetch tweet: {e}",
            "image_urls": [],
        }

    tweet = data.get("tweet", {})

    if not tweet:
        return {
            "source_type": "twitter",
            "source_id": url,
            "raw_text": "[ERROR] No tweet data in API response.",
            "image_urls": [],
        }

    author = tweet.get("author", {})
    author_name = author.get("name", "Unknown")
    author_handle = author.get("screen_name", "unknown")
    tweet_text = tweet.get("text", "")
    created_at = tweet.get("created_at", "")

    parts = []
    parts.append(
        f"[Main tweet] @{author_handle} ({author_name}) — {created_at}:\n{tweet_text}"
    )

    quote = tweet.get("quote", {})
    if quote:
        q_author = quote.get("author", {})
        q_handle = q_author.get("screen_name", "unknown")
        q_name = q_author.get("name", "Unknown")
        q_text = quote.get("text", "")
        q_date = quote.get("created_at", "")
        parts.append(
            f"[Quoted tweet] @{q_handle} ({q_name}) — {q_date}:\n{q_text}"
        )

    image_urls = []
    media = tweet.get("media", {})
    if media:
        photos = media.get("photos", [])
        for photo in photos:
            img_url = photo.get("url", "")
            if img_url:
                image_urls.append(img_url)

    return {
        "source_type": "twitter",
        "source_id": url,
        "author": f"@{author_handle}",
        "raw_text": "\n\n---\n\n".join(parts),
        "image_urls": image_urls,
    }


def download_image(url: str, dest_path: str) -> bool:
    try:
        req = Request(url, headers={"User-Agent": "CurriculumIngest/1.0"})
        with urlopen(req, timeout=15) as response:
            with open(dest_path, "wb") as f:
                f.write(response.read())
        return True
    except Exception as e:
        print(f"  Failed to download image: {e}")
        return False


# ---------------------------------------------------------------------------
# Step 3: Generic URL Extraction
# ---------------------------------------------------------------------------

async def extract_url(url: str) -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto(url, wait_until="networkidle", timeout=15000)
        await page.wait_for_timeout(2000)

        content = await page.evaluate("""
            () => {
                const junk = [
                    'nav', 'footer', 'aside', 'header',
                    '.sidebar', '.ad', '.advertisement',
                    '[role="navigation"]', '[role="banner"]',
                    '[role="complementary"]'
                ];
                junk.forEach(selector => {
                    document.querySelectorAll(selector).forEach(
                        el => el.remove()
                    );
                });

                const article = document.querySelector('article');
                if (article) return article.innerText;

                const main = document.querySelector('main');
                if (main) return main.innerText;

                return document.body.innerText;
            }
        """)

        title = await page.title()
        await browser.close()

    return {
        "source_type": "url",
        "source_id": url,
        "title": title,
        "raw_text": content.strip(),
    }


# ---------------------------------------------------------------------------
# Step 7: Screenshot Extraction (via Claude Vision)
# ---------------------------------------------------------------------------

def extract_screenshot(filepath: str) -> dict:
    with open(filepath, "rb") as f:
        img_bytes = f.read()

    img_b64 = base64.standard_b64encode(img_bytes).decode("utf-8")

    ext = Path(filepath).suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }
    media_type = media_types.get(ext, "image/jpeg")

    client = anthropic.Anthropic()

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": img_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Extract ALL meaningful content from this image. "
                            "This includes:\n"
                            "- All visible text (preserve formatting, code blocks, etc.)\n"
                            "- Description of any diagrams, flowcharts, or architecture visuals\n"
                            "- Data from any charts or graphs\n"
                            "- Key concepts shown visually\n"
                            "Return the content as structured plain text. "
                            "For code, use markdown code blocks. "
                            "For diagrams, describe the structure and relationships."
                        ),
                    },
                ],
            }
        ],
    )

    extracted_text = response.content[0].text

    return {
        "source_type": "screenshot",
        "source_id": filepath,
        "raw_text": extracted_text,
    }


# ---------------------------------------------------------------------------
# Step 4: Claude API Processing
# ---------------------------------------------------------------------------

CURRICULUM_SECTIONS = {
    "0. Multi-Agent Simulation": "Running autonomous ML experiments using agents (e.g. karpathy/autoresearch). Training loops, hyperparameter search, experiment tracking.",
    "1. Vibetunnel": "Completed. Intro to AI-assisted development and vibe coding workflows.",
    "2. LangChain": "Completed. LangChain framework, agents, chains, LangGraph, create_react_agent.",
    "2a. Anthropic Complete Guide to Building Skills for Claude": "SKILL.md file structure, MCP tool integration, testing and distributing Claude skills.",
    "3. RAG Architecture": "Retrieval-augmented generation. Chunking strategies, retrieval pipelines, combining search with LLM generation, hybrid search.",
    "4. Vector Database Implementation": "Vector stores (Qdrant, ChromaDB, Pinecone, pgvector). Indexing, similarity search, HNSW, IVF, distance metrics.",
    "5. Embedding Pipelines": "Text embeddings, embedding models, dimensionality, preprocessing text for embedding, batch embedding, storing and retrieving embeddings.",
    "6. Agent Memory Systems": "Short-term and long-term memory for agents. Conversation buffers, summary memory, retrieval-backed memory, persistent agent state.",
    "7. Context Window Optimisation": "Managing token limits. Summarisation, sliding windows, priority-based context selection, stuffing strategies.",
    "8. Structured Output Pipelines": "Getting LLMs to return JSON, XML, or typed outputs reliably. Schema enforcement, validation, retry logic, Pydantic models.",
    "9. Model Routing Logic": "Directing queries to different models based on complexity, cost, or task type. Cascading, fallback chains, classifier-based routing.",
    "10. Local Model Deployment": "Running models locally. Ollama, llama.cpp, GGUF, quantisation, MLX on Apple Silicon, serving local models via API.",
    "11. AI Guardrails & Validation": "Input/output filtering, content moderation, hallucination detection, safety layers, prompt injection defence.",
    "12. MCP Integration": "Model Context Protocol. Building MCP servers/clients, tool registration, connecting LLMs to external services and APIs.",
    "13. Batch Processing Architecture": "Processing large volumes of LLM requests. Queue systems, rate limiting, async batch jobs, cost optimisation.",
    "14. LLM Observability & Logging": "Monitoring LLM systems in production. Token usage tracking, latency, error rates, prompt versioning, LangSmith, Helicone.",
    "15. Cursor": "Cursor IDE. AI-assisted code editing, composer mode, codebase indexing, .cursorrules configuration.",
    "16. ClayLead": "Clay platform for lead enrichment and automated outreach using AI.",
    "17. Agent-Assisted Development": "Practical workflows for coding with LLM agents. Human-agent collaboration patterns, supervision strategies, declarative vs imperative prompting, test-first agent development.",
    "18. Synthetic Discourse": "Multi-agent debate and discourse patterns for knowledge synthesis.",
    "Uncategorised": "Resources that don't fit existing sections. Review periodically to determine if a new section is warranted.",
}


def process_with_claude(payload: dict) -> dict:
    client = anthropic.Anthropic()

    sections_text = ""
    for name, desc in CURRICULUM_SECTIONS.items():
        sections_text += f"- {name}: {desc}\n"

    prompt = f"""You are an AI curriculum assistant. Analyse the following content and return a structured JSON response.

LEARNER CONTEXT:
- ~9 months of AI/ML building experience
- Completed: Vibetunnel, LangChain fundamentals
- Currently building: multi-agent orchestration system (Python/FastAPI, Claude API, pgvector)
- Next up: RAG architecture, vector databases, embeddings
- Practical experience with: Playwright scraping, Claude API, async Python, Telegram bots

CURRICULUM SECTIONS (assign the content to the single most appropriate one based on the descriptions):
{sections_text}

INGESTED CONTENT:
Source type: {payload['source_type']}
Source: {payload['source_id']}
Text:
---
{payload['raw_text'][:6000]}
---

RULES:
- Extract AT LEAST 5 learning components if the content is substantive. Aim for 5-10.
- Be thorough. Capture every distinct concept, technique, insight, or principle.
- Do not summarise away the detail — each component should be a specific, teachable thing.
- If the content covers multiple curriculum areas, pick the PRIMARY one but mention others in the rationale.

Respond with ONLY a JSON object. No markdown fences, no explanation, just the JSON:
{{
    "is_relevant": true,
    "title": "Short descriptive title for this resource",
    "summary": "2-3 sentence summary of what this content teaches",
    "learning_components": [
        {{
            "concept": "Name of a specific concept or technique",
            "description": "One sentence explaining it",
            "level": "beginner or intermediate or advanced"
        }}
    ],
    "curriculum_section": "Exact section name from the list above",
    "level": "beginner or intermediate or advanced",
    "rationale": "Why this belongs in the chosen section. Mention any secondary sections it also touches."
}}

If the content is NOT relevant to AI/ML learning, return:
{{
    "is_relevant": false,
    "reason": "Brief explanation of why this isn't relevant"
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_response = response.content[0].text.strip()
    raw_response = re.sub(r"^```json\s*", "", raw_response)
    raw_response = re.sub(r"\s*```$", "", raw_response)

    result = json.loads(raw_response)
    return result


# ---------------------------------------------------------------------------
# Step 5: Curriculum File Writing
# ---------------------------------------------------------------------------

def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def load_manifest() -> list[dict]:
    with open(CURRICULUM_PATH, "r", encoding="utf-8") as f:
        curriculum_text = f.read()

    entries = []
    in_manifest = False

    for line in curriculum_text.split("\n"):
        if line.startswith("| Hash"):
            in_manifest = True
            continue
        if in_manifest and line.startswith("|---"):
            continue
        if in_manifest and line.startswith("|"):
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 6:
                entries.append({
                    "hash": parts[0],
                    "source_type": parts[1],
                    "source": parts[2],
                    "title": parts[3],
                    "section": parts[4],
                    "date": parts[5],
                })

    return entries


def append_to_curriculum(payload: dict, analysis: dict) -> str:
    c_hash = content_hash(payload["raw_text"])
    manifest = load_manifest()

    if any(entry["hash"] == c_hash for entry in manifest):
        return "DUPLICATE: This exact content is already in the curriculum."

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    section = analysis["curriculum_section"]
    title = analysis["title"]
    summary = analysis["summary"]
    source_type = payload["source_type"]
    source_id = payload["source_id"]

    components_md = ""
    for comp in analysis.get("learning_components", []):
        components_md += (
            f"  - **{comp['concept']}** ({comp['level']}): "
            f"{comp['description']}\n"
        )

    entry_block = (
        f"#### [{date_str}] {title}\n"
        f"- **Source:** {source_type} — `{source_id}`\n"
        f"- **Level:** {analysis['level']}\n"
        f"- **Summary:** {summary}\n"
        f"- **Learning components:**\n"
        f"{components_md}"
        f"- **Rationale:** {analysis['rationale']}\n"
    )

    with open(CURRICULUM_PATH, "r", encoding="utf-8") as f:
        lines = f.read().split("\n")

    section_header = f"## {section}"
    inserted = False

    for i, line in enumerate(lines):
        if line.strip() == section_header:
            for j in range(i + 1, min(i + 10, len(lines))):
                if lines[j].strip() == "### Ingested Resources":
                    for k in range(j + 1, min(j + 3, len(lines))):
                        if lines[k].strip() == "_None yet._":
                            lines[k] = entry_block
                            inserted = True
                            break
                    if not inserted:
                        lines.insert(j + 1, "\n" + entry_block)
                        inserted = True
                    break
            break

    if not inserted:
        for i, line in enumerate(lines):
            if line.strip() == "## Uncategorised":
                for j in range(i + 1, min(i + 10, len(lines))):
                    if lines[j].strip() == "### Ingested Resources":
                        for k in range(j + 1, min(j + 3, len(lines))):
                            if lines[k].strip() == "_None yet._":
                                lines[k] = entry_block
                                inserted = True
                                break
                        if not inserted:
                            lines.insert(j + 1, "\n" + entry_block)
                            inserted = True
                        break
                break

    manifest_row = (
        f"| {c_hash} | {source_type} | {source_id} "
        f"| {title} | {section} | {date_str} |"
    )

    last_table_row = -1
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].startswith("|") and not lines[i].startswith("| Hash") and not lines[i].startswith("|---"):
            last_table_row = i
            break

    if last_table_row >= 0:
        lines.insert(last_table_row + 1, manifest_row)
    else:
        for i, line in enumerate(lines):
            if line.startswith("|---"):
                lines.insert(i + 1, manifest_row)
                break

    with open(CURRICULUM_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return f"ADDED: {title} -> {section}"


# ---------------------------------------------------------------------------
# Step 8: Curriculum Management
# ---------------------------------------------------------------------------

def rename_section(old_name: str, new_name: str) -> str:
    with open(CURRICULUM_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    old_header = f"## {old_name}"
    if old_header not in content:
        lines = content.split("\n")
        matches = [l for l in lines if l.startswith("## ") and old_name.lower() in l.lower()]
        if matches:
            match_names = [m.replace("## ", "") for m in matches]
            return f"Section '{old_name}' not found. Did you mean: {', '.join(match_names)}?"
        return f"Section '{old_name}' not found in curriculum."

    new_header = f"## {new_name}"
    content = content.replace(old_header, new_header)
    content = content.replace(f"| {old_name} |", f"| {new_name} |")

    with open(CURRICULUM_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    if old_name in CURRICULUM_SECTIONS:
        CURRICULUM_SECTIONS[new_name] = CURRICULUM_SECTIONS.pop(old_name)

    return f"RENAMED: '{old_name}' -> '{new_name}'"


def add_section(name: str, description: str) -> str:
    with open(CURRICULUM_PATH, "r", encoding="utf-8") as f:
        lines = f.read().split("\n")

    header = f"## {name}"
    if any(line.strip() == header for line in lines):
        return f"Section '{name}' already exists."

    new_section = (
        f"\n---\n\n"
        f"## {name}\n"
        f"**Status:** NOT STARTED\n"
        f"**Covers:** {description}\n"
        f"\n"
        f"### Ingested Resources\n"
        f"_None yet._\n"
    )

    insert_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "## Uncategorised":
            insert_idx = i
            break

    if insert_idx is not None:
        for j in range(insert_idx - 1, -1, -1):
            if lines[j].strip() == "---":
                insert_idx = j
                break
        lines.insert(insert_idx, new_section)
    else:
        for i, line in enumerate(lines):
            if line.strip() == "## Manifest":
                lines.insert(i, new_section)
                break

    with open(CURRICULUM_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    CURRICULUM_SECTIONS[name] = description

    return f"ADDED SECTION: {name}"


def get_status() -> str:
    manifest = load_manifest()
    total = len(manifest)

    section_counts = {}
    for entry in manifest:
        sec = entry.get("section", "Unknown")
        section_counts[sec] = section_counts.get(sec, 0) + 1

    with open(CURRICULUM_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    all_sections = []
    for line in content.split("\n"):
        if line.startswith("## ") and not line.startswith("## Manifest") and not line.startswith("## Learner Profile"):
            sec_name = line.replace("## ", "").strip()
            all_sections.append(sec_name)

    lines = []
    lines.append(f"Total resources ingested: {total}")
    lines.append("")

    empty_sections = []
    for sec in all_sections:
        count = section_counts.get(sec, 0)
        if count > 0:
            lines.append(f"  {sec}: {count}")
        else:
            empty_sections.append(sec)

    if empty_sections:
        lines.append("")
        lines.append(f"Empty sections ({len(empty_sections)}):")
        for sec in empty_sections:
            lines.append(f"  - {sec}")

    return "\n".join(lines)


def list_sections() -> str:
    """Returns a numbered list of all curriculum sections."""
    with open(CURRICULUM_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    sections = []
    for line in content.split("\n"):
        if line.startswith("## ") and not line.startswith("## Manifest") and not line.startswith("## Learner Profile"):
            sec_name = line.replace("## ", "").strip()
            sections.append(sec_name)

    if not sections:
        return "No sections found."

    return "\n".join(sections)


def search_curriculum(term: str) -> str:
    """
    Searches curriculum entries for a keyword.
    Looks in titles, summaries, and learning component names.
    Returns matching entry titles with their sections.
    """
    with open(CURRICULUM_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    term_lower = term.lower()
    results = []
    current_section = ""

    for line in content.split("\n"):
        if line.startswith("## ") and not line.startswith("## Manifest"):
            current_section = line.replace("## ", "").strip()
        elif line.startswith("#### ["):
            # This is an entry title line like: #### [2026-03-20] Some Title
            title = line.split("] ", 1)[-1] if "] " in line else line
            if term_lower in title.lower():
                results.append(f"  [{current_section}] {title}")
        elif term_lower in line.lower() and line.strip().startswith("- **"):
            # Match in summary or learning component
            # Find the most recent title
            pass

    # Also search manifest for broader matches
    manifest = load_manifest()
    for entry in manifest:
        title = entry.get("title", "")
        section = entry.get("section", "")
        if term_lower in title.lower() and f"[{section}] {title}" not in "\n".join(results):
            results.append(f"  [{section}] {title}")

    if not results:
        return f"No results for '{term}'."

    return f"Results for '{term}':\n" + "\n".join(results)


def delete_entry(search_title: str) -> str:
    """
    Deletes a curriculum entry by title (partial match).
    Removes the entry block from its section and the
    corresponding row from the manifest table.
    """
    with open(CURRICULUM_PATH, "r", encoding="utf-8") as f:
        lines = f.read().split("\n")

    # Find the entry in the manifest first
    manifest = load_manifest()
    matched = [e for e in manifest if search_title.lower() in e["title"].lower()]

    if not matched:
        return f"No entry found matching '{search_title}'."

    if len(matched) > 1:
        titles = [f"  - {e['title']}" for e in matched]
        return f"Multiple matches. Be more specific:\n" + "\n".join(titles)

    target = matched[0]
    target_title = target["title"]
    target_hash = target["hash"]

    # Remove the entry block from the curriculum body
    # Entry blocks start with #### [date] Title and end before the next
    # #### or --- or ## header
    new_lines = []
    skip = False
    for i, line in enumerate(lines):
        if line.startswith("#### [") and target_title in line:
            skip = True
            continue
        if skip:
            # Stop skipping when we hit another entry, section, or separator
            if (line.startswith("#### [") or line.startswith("## ") or
                    line.strip() == "---" or line.strip() == ""):
                if line.strip() == "":
                    continue  # skip the blank line after the entry too
                skip = False
                new_lines.append(line)
                continue
            continue  # still inside the entry block, skip this line
        new_lines.append(line)

    # Remove the manifest row
    final_lines = []
    for line in new_lines:
        if line.startswith("|") and target_hash in line:
            continue
        final_lines.append(line)

    with open(CURRICULUM_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(final_lines))

    return f"DELETED: {target_title}"


def move_entry(search_title: str, new_section: str) -> str:
    """
    Moves a curriculum entry to a different section.
    Finds the entry, removes it from its current section,
    and re-inserts it into the new section.
    Also updates the manifest table.
    """
    with open(CURRICULUM_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Check the new section exists
    if f"## {new_section}" not in content:
        # Try partial match
        lines_check = content.split("\n")
        matches = [l.replace("## ", "") for l in lines_check
                   if l.startswith("## ") and new_section.lower() in l.lower()]
        if matches:
            return f"Section '{new_section}' not found. Did you mean: {', '.join(matches)}?"
        return f"Section '{new_section}' not found."

    lines = content.split("\n")

    # Find the entry in manifest
    manifest = load_manifest()
    matched = [e for e in manifest if search_title.lower() in e["title"].lower()]

    if not matched:
        return f"No entry found matching '{search_title}'."

    if len(matched) > 1:
        titles = [f"  - {e['title']}" for e in matched]
        return f"Multiple matches. Be more specific:\n" + "\n".join(titles)

    target = matched[0]
    target_title = target["title"]
    target_hash = target["hash"]
    old_section = target["section"]

    if old_section == new_section:
        return f"'{target_title}' is already in '{new_section}'."

    # Extract the entry block
    entry_lines = []
    capturing = False
    entry_start = -1
    entry_end = -1

    for i, line in enumerate(lines):
        if line.startswith("#### [") and target_title in line:
            capturing = True
            entry_start = i
        if capturing:
            if (i > entry_start and
                    (line.startswith("#### [") or line.startswith("## ") or line.strip() == "---")):
                entry_end = i
                break
            entry_lines.append(line)

    if entry_end == -1:
        entry_end = len(lines)

    if not entry_lines:
        return f"Could not find entry block for '{target_title}'."

    entry_block = "\n".join(entry_lines)

    # Remove from old location
    # Also remove any trailing blank line
    del lines[entry_start:entry_end]

    # Insert into new section
    section_header = f"## {new_section}"
    inserted = False

    for i, line in enumerate(lines):
        if line.strip() == section_header:
            for j in range(i + 1, min(i + 10, len(lines))):
                if lines[j].strip() == "### Ingested Resources":
                    for k in range(j + 1, min(j + 3, len(lines))):
                        if lines[k].strip() == "_None yet._":
                            lines[k] = entry_block
                            inserted = True
                            break
                    if not inserted:
                        lines.insert(j + 1, "\n" + entry_block)
                        inserted = True
                    break
            break

    if not inserted:
        return f"Could not insert into section '{new_section}'."

    # Update manifest: replace old section name with new
    for i, line in enumerate(lines):
        if line.startswith("|") and target_hash in line:
            lines[i] = line.replace(f"| {old_section} |", f"| {new_section} |")
            break

    with open(CURRICULUM_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return f"MOVED: '{target_title}' from '{old_section}' to '{new_section}'"


def get_recent(n: int = 5) -> str:
    """Returns the last n ingested items from the manifest."""
    manifest = load_manifest()

    if not manifest:
        return "No resources ingested yet."

    recent = manifest[-n:]
    recent.reverse()  # newest first

    lines = [f"Last {len(recent)} ingested:"]
    for entry in recent:
        lines.append(
            f"  [{entry.get('date', '?')}] {entry['title']}\n"
            f"    -> {entry['section']}"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 6: Main ingest() entry point
# ---------------------------------------------------------------------------

async def ingest(raw_input: str) -> str:
    try:
        input_type, value = classify_input(raw_input)
    except ValueError as e:
        return f"ERROR: {e}"

    try:
        if input_type == "twitter":
            payload = extract_twitter(value)

            image_urls = payload.get("image_urls", [])
            if image_urls:
                print(f"  Tweet has {len(image_urls)} image(s). Extracting content...")
                for i, img_url in enumerate(image_urls):
                    img_ext = ".jpg"
                    if ".png" in img_url:
                        img_ext = ".png"
                    elif ".webp" in img_url:
                        img_ext = ".webp"

                    tmp_path = f"/tmp/tweet_image_{i}{img_ext}"
                    if download_image(img_url, tmp_path):
                        try:
                            img_result = extract_screenshot(tmp_path)
                            img_text = img_result.get("raw_text", "")
                            if img_text:
                                payload["raw_text"] += (
                                    f"\n\n---\n\n"
                                    f"[Image {i+1} content]:\n{img_text}"
                                )
                                print(f"  Extracted {len(img_text)} chars from image {i+1}")
                        except Exception as e:
                            print(f"  Failed to extract image {i+1}: {e}")

            text_without_header = payload["raw_text"].split("\n", 2)[-1] if "\n" in payload["raw_text"] else ""
            if len(text_without_header.strip()) < TWITTER_MIN_TEXT_LENGTH:
                print(f"  Still minimal text ({len(text_without_header.strip())} chars). Falling back to browser...")
                payload = await extract_url(value)
                payload["source_type"] = "twitter"

                if len(payload["raw_text"]) < TWITTER_MIN_TEXT_LENGTH:
                    return (
                        "ERROR: This appears to be a Twitter Article or image-only post. "
                        "Neither the API nor the browser could extract the content. "
                        "Copy-paste the article text directly and send it."
                    )

        elif input_type == "url":
            payload = await extract_url(value)

        elif input_type == "text":
            payload = {
                "source_type": "text",
                "source_id": "pasted_text",
                "raw_text": value,
            }

        elif input_type == "screenshot":
            payload = extract_screenshot(value)

        else:
            return f"ERROR: Unknown input type '{input_type}'"

    except Exception as e:
        return f"ERROR: Extraction failed: {e}"

    if payload["raw_text"].startswith("[ERROR]"):
        return f"ERROR: {payload['raw_text']}"

    c_hash = content_hash(payload["raw_text"])
    manifest = load_manifest()
    if any(entry["hash"] == c_hash for entry in manifest):
        return "DUPLICATE: This exact content is already in the curriculum."

    try:
        analysis = process_with_claude(payload)
    except Exception as e:
        return f"ERROR: Claude processing failed: {e}"

    if not analysis.get("is_relevant"):
        reason = analysis.get("reason", "not relevant to AI/ML learning")
        return f"SKIPPED: {reason}"

    try:
        result = append_to_curriculum(payload, analysis)
    except Exception as e:
        return f"ERROR: Writing to curriculum failed: {e}"

    return result


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        user_input = sys.argv[1]
        print(f"Ingesting: {user_input[:80]}...")
        result = asyncio.run(ingest(user_input))
        print(result)
    else:
        print("Usage:")
        print('  python3 ingest.py "https://x.com/user/status/123"   # tweet')
        print('  python3 ingest.py "https://some-blog.com/post"      # URL')
        print('  python3 ingest.py "paste raw text here..."          # text')
        print('  python3 ingest.py /path/to/screenshot.png           # image')
