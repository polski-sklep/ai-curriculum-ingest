"""
Curriculum Ingest Telegram Bot
Commands:
  /start - Help
  /status - Curriculum summary
  /rename Old | New - Rename a section
  /add_section Name | Description - Add section
  /search term - Search entries
  /delete title - Delete an entry
  /move title | Section - Move entry to section
  /sections - List all sections
  /recent - Last 5 ingested items
  /export - Send curriculum.md as file
"""

import os
import asyncio
import logging

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from ingest import (
    ingest,
    rename_section,
    add_section,
    get_status,
    list_sections,
    search_curriculum,
    delete_entry,
    move_entry,
    get_recent,
    CURRICULUM_PATH,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
# Set TELEGRAM_ALLOWED_USER_ID in .env to the numeric ID permitted to use this bot (DM @userinfobot to find yours).
ALLOWED_USER_ID = int(os.environ.get("TELEGRAM_ALLOWED_USER_ID", "0"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
LOG = logging.getLogger("curriculum_bot")


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Curriculum Ingest Bot.\n\n"
        "Send me:\n"
        "- A Twitter/X link\n"
        "- Any URL (blog, article, docs)\n"
        "- Raw text (paste an article)\n"
        "- A screenshot (image)\n\n"
        "Commands:\n"
        "/status - Curriculum summary\n"
        "/sections - List all sections\n"
        "/recent - Last 5 ingested items\n"
        "/search term - Search entries\n"
        "/rename Old | New - Rename a section\n"
        "/add_section Name | Description\n"
        "/delete title - Delete an entry\n"
        "/move title | Section - Move entry\n"
        "/export - Get curriculum.md file"
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("Not authorised.")
        return

    try:
        result = get_status()
    except Exception as e:
        result = f"ERROR: {e}"

    await update.message.reply_text(result)


async def sections_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("Not authorised.")
        return

    try:
        result = list_sections()
    except Exception as e:
        result = f"ERROR: {e}"

    await update.message.reply_text(result)


async def recent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("Not authorised.")
        return

    try:
        result = get_recent(5)
    except Exception as e:
        result = f"ERROR: {e}"

    await update.message.reply_text(result)


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("Not authorised.")
        return

    term = update.message.text.replace("/search", "", 1).strip()

    if not term:
        await update.message.reply_text("Usage: /search keyword")
        return

    try:
        result = search_curriculum(term)
    except Exception as e:
        result = f"ERROR: {e}"

    await update.message.reply_text(result)


async def rename_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("Not authorised.")
        return

    text = update.message.text.replace("/rename", "", 1).strip()

    if "|" not in text:
        await update.message.reply_text("Usage: /rename Old Name | New Name")
        return

    parts = text.split("|", 1)
    old_name = parts[0].strip()
    new_name = parts[1].strip()

    if not old_name or not new_name:
        await update.message.reply_text("Usage: /rename Old Name | New Name")
        return

    LOG.info("Rename: '%s' -> '%s'", old_name, new_name)

    try:
        result = rename_section(old_name, new_name)
    except Exception as e:
        result = f"ERROR: {e}"

    await update.message.reply_text(result)


async def add_section_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("Not authorised.")
        return

    text = update.message.text.replace("/add_section", "", 1).strip()

    if "|" not in text:
        await update.message.reply_text("Usage: /add_section Name | Description")
        return

    parts = text.split("|", 1)
    name = parts[0].strip()
    description = parts[1].strip()

    if not name or not description:
        await update.message.reply_text("Usage: /add_section Name | Description")
        return

    LOG.info("Add section: '%s'", name)

    try:
        result = add_section(name, description)
    except Exception as e:
        result = f"ERROR: {e}"

    await update.message.reply_text(result)


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("Not authorised.")
        return

    title = update.message.text.replace("/delete", "", 1).strip()

    if not title:
        await update.message.reply_text("Usage: /delete entry title (or partial match)")
        return

    LOG.info("Delete: '%s'", title)

    try:
        result = delete_entry(title)
    except Exception as e:
        result = f"ERROR: {e}"

    await update.message.reply_text(result)


async def move_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("Not authorised.")
        return

    text = update.message.text.replace("/move", "", 1).strip()

    if "|" not in text:
        await update.message.reply_text("Usage: /move Entry Title | New Section Name")
        return

    parts = text.split("|", 1)
    title = parts[0].strip()
    new_section = parts[1].strip()

    if not title or not new_section:
        await update.message.reply_text("Usage: /move Entry Title | New Section Name")
        return

    LOG.info("Move: '%s' -> '%s'", title, new_section)

    try:
        result = move_entry(title, new_section)
    except Exception as e:
        result = f"ERROR: {e}"

    await update.message.reply_text(result)


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("Not authorised.")
        return

    LOG.info("Export requested")

    try:
        await update.message.reply_document(
            document=open(CURRICULUM_PATH, "rb"),
            filename="curriculum.md",
            caption="Current curriculum file",
        )
    except Exception as e:
        await update.message.reply_text(f"ERROR: {e}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("Not authorised.")
        return

    user_text = update.message.text
    if not user_text:
        return

    LOG.info("Received text: %s", user_text[:80])
    await update.message.reply_text("Processing...")

    try:
        result = await ingest(user_text)
    except Exception as e:
        result = f"ERROR: {e}"

    await update.message.reply_text(result)
    LOG.info("Result: %s", result)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("Not authorised.")
        return

    LOG.info("Received photo")
    await update.message.reply_text("Processing screenshot...")

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)

    img_path = "/tmp/curriculum_screenshot.jpg"
    await file.download_to_drive(img_path)

    LOG.info("Downloaded image to %s", img_path)

    try:
        result = await ingest(img_path)
    except Exception as e:
        result = f"ERROR: {e}"

    await update.message.reply_text(result)
    LOG.info("Result: %s", result)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not set.")
        print("Run: export TELEGRAM_BOT_TOKEN='your-token'")
        return

    LOG.info("Starting Curriculum Ingest Bot...")

    app = ApplicationBuilder().token(TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("sections", sections_command))
    app.add_handler(CommandHandler("recent", recent_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("rename", rename_command))
    app.add_handler(CommandHandler("add_section", add_section_command))
    app.add_handler(CommandHandler("delete", delete_command))
    app.add_handler(CommandHandler("move", move_command))
    app.add_handler(CommandHandler("export", export_command))

    # Message handlers
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()


if __name__ == "__main__":
    main()
