"""
Kaironis Telegram Bot — Operator Interface

Commands:
    /start      - Welcome message (content depends on access level)
    /myid       - Show your Telegram ID (public, no auth required)
    /help       - Command overview (operator only)
    /status     - Current agent status + ChromaDB status (operator only)
    /pause      - Pause autonomous trading (operator only)
    /resume     - Resume autonomous trading (operator only)
    /emergency  - KILL SWITCH — stop everything immediately (operator only)
    /ask        - Query the TCT strategy knowledge base (operator + allowlist)
    /explain    - RAG: ask a question, get a summary via AI (operator + allowlist)
    /note       - Save a market observation (operator only)
    /lesson     - Save a lesson learned (operator only)
    /notes      - Show the last 5 notes (operator only)

Access control:
    TELEGRAM_OPERATOR_CHAT_ID  - Full access (operator)
    TELEGRAM_ALLOWED_USERS     - Comma-separated IDs with /ask + /explain access

Architecture:
    - Async via python-telegram-bot v21
    - State management via Redis
    - Audit logging via structured JSON
    - Memory via ChromaDB + PostgreSQL
"""

import asyncio
import json
import logging
import os
import requests
import sys
import threading
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import quote_plus

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# Structured logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
_raw_operator_id = os.getenv("TELEGRAM_OPERATOR_CHAT_ID", "0")
try:
    OPERATOR_CHAT_ID = int(_raw_operator_id)
except ValueError:
    logger.critical(
        "TELEGRAM_OPERATOR_CHAT_ID must be an integer, got: %r — bot cannot start.",
        _raw_operator_id,
    )
    sys.exit(
        f"Error: TELEGRAM_OPERATOR_CHAT_ID must be an integer, got: {_raw_operator_id!r}"
    )

# Allowlist: comma-separated Telegram user IDs that may use /explain and /ask
# e.g. TELEGRAM_ALLOWED_USERS=123456789,987654321,555555555
_raw_allowed = os.getenv("TELEGRAM_ALLOWED_USERS", "")
ALLOWED_USER_IDS: set[int] = set()
for _uid in _raw_allowed.split(","):
    _uid = _uid.strip()
    if _uid.isdigit():
        ALLOWED_USER_IDS.add(int(_uid))

# Master trainer IDs: their free-text messages are treated as knowledge updates
# and staged for operator review before entering ChromaDB.
# e.g. TELEGRAM_TRAINER_IDS=7131738270
_raw_trainers = os.getenv("TELEGRAM_TRAINER_IDS", "")
TRAINER_IDS: set[int] = set()
for _uid in _raw_trainers.split(","):
    _uid = _uid.strip()
    if _uid.isdigit():
        TRAINER_IDS.add(int(_uid))

# Ollama config (strip http:// prefix if present)
_ollama_raw = os.getenv("OLLAMA_HOST", "localhost")
OLLAMA_HOST = _ollama_raw.replace("http://", "").replace("https://", "").split(":")[0]
OLLAMA_PORT = int(os.getenv("OLLAMA_PORT", "11434"))

# DATABASE_URL: use direct URL or compose from individual variables.
# Only if POSTGRES_HOST is explicitly set, otherwise DATABASE_URL stays None
# so that _get_reflection_log() correctly returns None and handlers show
# the "DB not configured" message.
_postgres_host = os.getenv("POSTGRES_HOST")
DATABASE_URL = os.getenv("DATABASE_URL") or (
    "postgresql://{user}:{password}@{host}:{port}/{db}".format(
        user=quote_plus(os.getenv("POSTGRES_USER", "kaironis")),
        password=quote_plus(os.getenv("POSTGRES_PASSWORD", "")),
        host=_postgres_host,
        port=os.getenv("POSTGRES_PORT", "5432"),
        db=os.getenv("POSTGRES_DB", "kaironis"),
    )
    if _postgres_host
    else None
)

# Agent state (in-memory for now, later via Redis)
agent_state = {
    "trading_active": False,
    "paused": False,
    "emergency_stop": False,
    "started_at": datetime.now(tz=timezone.utc).isoformat(),
    "version": "0.3.0",
}

# Lock for thread-safe mutations of agent_state (used by /pause, /resume, /emergency)
_agent_state_lock = threading.Lock()

# Lazy-initialized singletons — shared across all command handlers
_reflection_log = None
_knowledge_base = None
_reflection_lock = threading.Lock()
_knowledge_lock = threading.Lock()


def _get_reflection_log():
    """Lazy-initialize the ReflectionLog singleton."""
    global _reflection_log
    if _reflection_log is None:
        with _reflection_lock:
            if _reflection_log is None and DATABASE_URL:
                from src.memory.reflection import ReflectionLog
                _reflection_log = ReflectionLog(dsn=DATABASE_URL)
    return _reflection_log


def _get_knowledge_base():
    """Lazy-initialize the KnowledgeBase singleton. Avoids per-command re-init overhead."""
    global _knowledge_base
    if _knowledge_base is None:
        with _knowledge_lock:
            if _knowledge_base is None:
                from src.memory.knowledge_base import KnowledgeBase
                _knowledge_base = KnowledgeBase()
    return _knowledge_base


# ─────────────────────────────────────────────────────────────────
# Security — only the operator may issue commands
# ─────────────────────────────────────────────────────────────────

def operator_only(func):
    """Decorator: block everyone who is not the operator."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != OPERATOR_CHAT_ID:
            logger.warning(
                "Unauthorized access from user %s", update.effective_user.id
            )
            await update.message.reply_text(
                "⛔ Not authorized. Only the operator can control Kaironis."
            )
            return
        return await func(update, context)
    return wrapper


def allowed_user(func):
    """Decorator: allow operator + users on the TELEGRAM_ALLOWED_USERS allowlist."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if uid != OPERATOR_CHAT_ID and uid not in ALLOWED_USER_IDS:
            logger.warning("Unauthorized access from user %s", uid)
            await update.message.reply_text(
                "⛔ Not authorized.\n\n"
                "Use /myid to get your Telegram ID and share it with the operator."
            )
            return
        return await func(update, context)
    return wrapper


# ─────────────────────────────────────────────────────────────────
# Command Handlers
# ─────────────────────────────────────────────────────────────────

async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return the user's Telegram ID — public, no auth required."""
    uid = update.effective_user.id
    name = update.effective_user.first_name or "there"
    await update.message.reply_text(
        f"👤 *Your Telegram ID*\n\n`{uid}`\n\n"
        f"Hi {name}! Share this ID with the operator to get access to Kaironis.",
        parse_mode="Markdown",
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message — shows available commands based on access level."""
    uid = update.effective_user.id
    is_operator = uid == OPERATOR_CHAT_ID
    is_allowed = uid in ALLOWED_USER_IDS

    if is_operator:
        await update.message.reply_text(
            "⚡ *Kaironis online.*\n\n"
            "Welcome back, operator.\n\n"
            "*Available commands:*\n"
            "/explain \\[vraag\\] — RAG antwoord op TCT vraag\n"
            "/ask \\[vraag\\] — Ruwe chunks uit kennisbank\n"
            "/status — Agent \\+ ChromaDB status\n"
            "/pause — Pauzeer trading\n"
            "/resume — Hervat trading\n"
            "/note \\[tekst\\] — Sla observatie op\n"
            "/lesson \\[tekst\\] — Sla les op\n"
            "/notes — Laatste 5 notities\n"
            "/emergency — ⛔ KILL SWITCH\n"
            "/help — Volledig overzicht\n\n"
            "_The opportune moment awaits._",
            parse_mode="Markdown",
        )
    elif is_allowed:
        await update.message.reply_text(
            "⚡ *Kaironis — TCT Knowledge Base*\n\n"
            "Je hebt toegang tot de TCT strategie kennisbank.\n\n"
            "*Beschikbare commands:*\n"
            "/explain \\[vraag\\] — Gedetailleerd antwoord op TCT vraag\n"
            "/ask \\[vraag\\] — Ruwe chunks uit de strategie docs\n"
            "/myid — Jouw Telegram ID\n\n"
            "_Vraag alles over Time\\-Cycle Trading._",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            "⚡ *Kaironis*\n\n"
            "Je hebt momenteel geen toegang.\n\n"
            "Gebruik /myid om je Telegram ID op te vragen en deel dit met de operator.",
            parse_mode="Markdown",
        )


@operator_only
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Overview of all commands."""
    help_text = (
        "🤖 *Kaironis Command Overview*\n\n"
        "*Status & Info*\n"
        "/status — Current agent + ChromaDB status\n"
        "/help — This overview\n\n"
        "*Trading Control*\n"
        "/pause — Pause autonomous trading\n"
        "/resume — Resume autonomous trading\n\n"
        "*Knowledge Base*\n"
        "/ask \\[question\\] — Query the TCT strategy knowledge base\n\n"
        "*Notes & Learnings*\n"
        "/note \\[text\\] — Save a market observation\n"
        "/lesson \\[text\\] — Save a lesson learned\n"
        "/notes — Show the last 5 notes\n\n"
        "*Emergency*\n"
        "/emergency — ⛔ KILL SWITCH — stop everything\n\n"
        f"_v{agent_state['version']} — Memory Query & Reflection System_"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


@operator_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return current agent status + ChromaDB status."""
    status_emoji = "🔴" if agent_state["emergency_stop"] else \
                   "⏸️" if agent_state["paused"] else \
                   "🟢" if agent_state["trading_active"] else "🟡"

    status_text = "EMERGENCY STOP" if agent_state["emergency_stop"] else \
                  "Paused" if agent_state["paused"] else \
                  "Trading active" if agent_state["trading_active"] else "Standby"

    # ChromaDB status check
    chroma_status = "⬜ Not checked"
    chroma_count = ""
    try:
        kb = _get_knowledge_base()
        stats = await asyncio.to_thread(kb.get_stats)
        count = stats.get("document_count", 0)
        chroma_status = "✅ Reachable"
        chroma_count = f"\n*Chunks in collection:* {count}"
    except Exception as e:
        chroma_status = f"❌ Not reachable ({_escape_md(type(e).__name__)})"
        logger.warning("ChromaDB status check failed: %s", e)

    message = (
        f"{status_emoji} *Kaironis Status*\n\n"
        f"*Status:* {status_text}\n"
        f"*Version:* {agent_state['version']}\n"
        f"*Online since:* {agent_state['started_at']} UTC\n\n"
        f"*Trading:* {'Active ✅' if agent_state['trading_active'] else 'Inactive ⏹️'}\n"
        f"*Paused:* {'Yes ⏸️' if agent_state['paused'] else 'No'}\n"
        f"*Emergency stop:* {'YES 🚨' if agent_state['emergency_stop'] else 'No'}\n\n"
        f"*ChromaDB:* {chroma_status}{chroma_count}"
    )
    await update.message.reply_text(message, parse_mode="Markdown")


@operator_only
async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pause autonomous trading."""
    with _agent_state_lock:
        if agent_state["emergency_stop"]:
            await update.message.reply_text(
                "🚨 Emergency stop is active. Use /resume to restart after review."
            )
            return
        agent_state["paused"] = True
        agent_state["trading_active"] = False
    logger.info("Trading paused by operator %s", update.effective_user.id)

    await update.message.reply_text(
        "⏸️ *Trading paused.*\n\n"
        "Kaironis is still monitoring markets but will not execute trades.\n"
        "Use /resume to continue.",
        parse_mode="Markdown",
    )


@operator_only
async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Resume autonomous trading."""
    with _agent_state_lock:
        agent_state["paused"] = False
        agent_state["emergency_stop"] = False
        agent_state["trading_active"] = True
    logger.info("Trading resumed by operator %s", update.effective_user.id)

    await update.message.reply_text(
        "▶️ *Trading resumed.*\n\n"
        "Kaironis is active again and monitoring for setups.\n"
        "Use /status for current state.",
        parse_mode="Markdown",
    )


@operator_only
async def cmd_emergency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """KILL SWITCH — stop everything immediately."""
    with _agent_state_lock:
        agent_state["emergency_stop"] = True
        agent_state["trading_active"] = False
        agent_state["paused"] = True

    logger.critical(
        "EMERGENCY STOP activated by operator %s", update.effective_user.id
    )

    await update.message.reply_text(
        "🚨 *EMERGENCY STOP ACTIVATED*\n\n"
        "✅ All trading stopped\n"
        "✅ No new positions possible\n"
        "✅ Monitors paused\n\n"
        "_Review the situation and use /resume to continue._",
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────────────────────────────
# Knowledge base — /ask
# ─────────────────────────────────────────────────────────────────

@allowed_user
async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Query the TCT strategy knowledge base via ChromaDB."""
    message_text = update.message.text or ""
    # Strip the /ask command
    parts = message_text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await update.message.reply_text(
            "⬜ Usage: `/ask [question]`\n\nExample: `/ask what is PO3?`",
            parse_mode="Markdown",
        )
        return

    question = parts[1].strip()

    # Send "typing..." indicator
    await update.message.chat.send_action("typing")

    try:
        kb = _get_knowledge_base()
        # Fetch more and filter chunk_index=0 (often header-only chunks)
        raw = await asyncio.to_thread(kb.query_strategy, question, 10)
        results = [r for r in raw if r.get("metadata", {}).get("chunk_index", 1) != 0][:3]
    except Exception as e:
        logger.error("KnowledgeBase query failed: %s", e)
        await update.message.reply_text(
            f"❌ Error querying knowledge base: `{_escape_md(type(e).__name__)}`",
            parse_mode="Markdown",
        )
        return

    if not results:
        await update.message.reply_text(
            "🔍 No relevant information found for this question.\n\n"
            "_Check whether the knowledge base has been ingested._",
            parse_mode="Markdown",
        )
        return

    # Build the response
    lines = [f"📚 *Knowledge about: {_escape_md(question)}*\n"]

    for i, result in enumerate(results, 1):
        doc = result.get("document", "")
        meta = result.get("metadata", {})
        distance_raw = result.get("distance", 1.0)
        try:
            distance = max(0.0, float(distance_raw))
        except (TypeError, ValueError):
            logger.warning("Invalid distance value in /ask result: %r", distance_raw)
            distance = 1.0
        relevance = max(0.0, min(1.0, 1.0 - distance))

        # Metadata keys: filename, source_file, chunk_index
        filename = meta.get("filename") or meta.get("source_file") or meta.get("source") or "unknown"
        # Strip path prefix if present
        filename = filename.split("/")[-1].replace(".md", "")
        chunk_idx = meta.get("chunk_index", "?")

        # Show real content — filter headers but fall back to full text
        doc_lines = [line for line in doc.split("\n")
                     if line.strip() and not line.strip().startswith("#") and line.strip() != "---"]
        doc_preview = " ".join(doc_lines).strip() if doc_lines else doc.strip()
        if not doc_preview:
            doc_preview = doc.strip()
        if len(doc_preview) > 600:
            doc_preview = doc_preview[:600] + "…"

        lines.append(
            f"*[{i}] {_escape_md(filename)}* "
            f"(chunk {chunk_idx}, relevance: {relevance:.0%})\n"
            f"{_escape_md(doc_preview)}\n"
        )

    response = "\n".join(lines)

    # Keep under the 4000-char Telegram limit
    if len(response) > 3900:
        response = response[:3900] + "\n\n_[truncated]_"

    await update.message.reply_text(response, parse_mode="Markdown")


# ─────────────────────────────────────────────────────────────────
# RAG — /explain
# ─────────────────────────────────────────────────────────────────

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")

@allowed_user
async def cmd_explain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """RAG: ask a question, get an AI summary based on TCT docs."""
    message_text = update.message.text or ""
    parts = message_text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await update.message.reply_text(
            "🤖 Usage: `/explain [question]`\n\nExample: `/explain what is PO3 and how do I use it?`",
            parse_mode="Markdown",
        )
        return

    question = parts[1].strip()
    await update.message.chat.send_action("typing")

    # Step 1: Retrieve relevant chunks from ChromaDB
    try:
        kb = _get_knowledge_base()
        raw = await asyncio.to_thread(kb.query_strategy, question, 10)
        chunks = [r for r in raw if r.get("metadata", {}).get("chunk_index", 1) != 0][:5]
    except Exception as e:
        logger.error("ChromaDB query failed in /explain: %s", e)
        await update.message.reply_text(
            f"❌ ChromaDB error: `{_escape_md(type(e).__name__)}`",
            parse_mode="Markdown",
        )
        return

    if not chunks:
        await update.message.reply_text("🔍 No relevant information found.")
        return

    # Step 2: Build context
    context_parts = []
    for i, r in enumerate(chunks, 1):
        meta = r.get("metadata", {})
        filename = meta.get("filename", "unknown").replace(".md", "")
        doc = r.get("document", "")
        doc_lines = [line for line in doc.split("\n") if line.strip() and not line.strip().startswith("#")]
        content = " ".join(doc_lines).strip()[:800]
        if content:
            context_parts.append(f"[Source {i}: {filename}]\n{content}")

    # Stop early if there is no usable context after cleanup
    if not context_parts:
        await update.message.reply_text(
            "🔍 No relevant information found after cleaning up the retrieved chunks."
        )
        return

    context_text = "\n\n".join(context_parts)

    prompt = f"""You are Kaironis, an AI trading assistant specializing in the TCT (The Composite Trader) strategy.
Answer the following question based on the provided TCT documentation. Be concrete and practical.
Answer in English. Maximum 400 words.

<question>
{question}
</question>

<tct_documentation>
{context_text}
</tct_documentation>

Answer:"""

    # Step 3: Generate answer via OpenRouter (Gemini Flash)
    await update.message.reply_text("⏳ Thinking based on TCT docs...")
    await update.message.chat.send_action("typing")

    if not OPENROUTER_API_KEY:
        await update.message.reply_text("❌ OPENROUTER\\_API\\_KEY not configured.", parse_mode="Markdown")
        return

    try:
        # asyncio.to_thread() prevents the blocking HTTP call from blocking the event loop.
        # This allows /emergency to respond while OpenRouter is thinking.
        resp = await asyncio.to_thread(
            requests.post,
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/KaironisDev/kaironis",
                "X-Title": "Kaironis Trading Bot",
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 600,
            },
            timeout=30,
        )
        resp.raise_for_status()
        answer = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error("OpenRouter request failed in /explain: %s", e)
        err = _escape_md(f"{type(e).__name__}: {e}")
        await update.message.reply_text(
            f"❌ OpenRouter error: `{err}`",
            parse_mode="Markdown",
        )
        return

    if not answer:
        await update.message.reply_text("❌ Empty response from model.")
        return

    # Step 4: Send response
    sources = ", ".join(
        {r.get("metadata", {}).get("filename", "?").replace(".md", "") for r in chunks}  # set comprehension
    )
    header = f"🤖 {question}\n\n"
    footer = f"\n\nSources: {sources}"

    response = header + answer + footer
    if len(response) > 3900:
        response = response[:3900] + "\n\n[truncated]"

    await update.message.reply_text(response)


# ─────────────────────────────────────────────────────────────────
# Reflection Commands — /note, /lesson, /notes
# ─────────────────────────────────────────────────────────────────

async def _save_observation_and_reply(
    update: Update,
    *,
    category: str,
    usage_hint: str,
    success_prefix: str,
    success_label: str,
) -> None:
    """
    Shared helper for /note and /lesson.

    Parses the message text, saves the observation and sends a confirmation.
    On a failing Markdown reply, a plain-text fallback is attempted so that
    the operator always gets feedback that the save succeeded.
    """
    message_text = update.message.text or ""
    parts = message_text.split(None, 1)

    if len(parts) < 2 or not parts[1].strip():
        await update.message.reply_text(usage_hint, parse_mode="Markdown")
        return

    content = parts[1].strip()
    reflection = _get_reflection_log()

    if reflection is None:
        await update.message.reply_text(
            "⛔ Database not configured (DATABASE\\_URL missing).",
            parse_mode="Markdown",
        )
        return

    # Save and confirm separately so DB errors and reply errors are not mixed
    try:
        record_id = await reflection.log_observation(
            category=category,
            content=content,
            metadata={"telegram_user": update.effective_user.id},
        )
    except Exception as e:
        logger.exception("%s save failed: %s", success_label, e)
        await update.message.reply_text(
            f"⛔ Error saving: `{_escape_md(type(e).__name__)}`",
            parse_mode="Markdown",
        )
        return

    # First attempt: Markdown reply
    try:
        await update.message.reply_text(
            f"{success_prefix} {success_label} saved (id: {record_id})\n\n_{_escape_md(content)}_",
            parse_mode="Markdown",
        )
        return
    except Exception as e:
        logger.exception("Markdown reply for %s (id=%d) failed: %s", success_label, record_id, e)

    # Fallback: plain-text reply so operator knows the save succeeded
    try:
        await update.message.reply_text(
            f"{success_prefix} {success_label} saved (id: {record_id})."
        )
    except Exception as e:
        logger.exception("Fallback reply for %s (id=%d) also failed: %s", success_label, record_id, e)


@operator_only
async def cmd_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG001
    """Save a market observation."""
    await _save_observation_and_reply(
        update,
        category="market_observation",
        usage_hint="📝 Usage: `/note [text]`\n\nExample: `/note DXY running into supply zone on H4`",
        success_prefix="✅",
        success_label="Observation",
    )


@operator_only
async def cmd_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG001
    """Save a lesson as 'lesson_learned'."""
    await _save_observation_and_reply(
        update,
        category="lesson_learned",
        usage_hint="🎓 Usage: `/lesson [text]`\n\nExample: `/lesson Never trade in the first 5 min after NY open`",
        success_prefix="🎓",
        success_label="Lesson learned",
    )


@operator_only
async def cmd_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the last 5 notes."""
    reflection = _get_reflection_log()

    if reflection is None:
        await update.message.reply_text(
            "❌ Database not configured (DATABASE\\_URL missing).",
            parse_mode="Markdown",
        )
        return

    try:
        records = await reflection.get_recent(limit=5)
    except Exception as e:
        logger.error("Fetching notes failed: %s", e)
        await update.message.reply_text(
            f"❌ Error fetching notes: `{_escape_md(type(e).__name__)}`",
            parse_mode="Markdown",
        )
        return

    if not records:
        await update.message.reply_text(
            "📭 No notes saved yet.\n\n"
            "Use `/note` or `/lesson` to get started.",
            parse_mode="Markdown",
        )
        return

    lines = ["📋 *Latest notes:*\n"]
    category_emoji = {
        "market_observation": "📊",
        "lesson_learned": "🎓",
        "trade_setup": "📈",
        "strategy_note": "📎",
    }

    for rec in records:
        emoji = category_emoji.get(rec["category"], "📝")
        cat = rec["category"].replace("_", " ").title()
        # Timestamp: parse ISO8601 fully (timezone-aware) and format readable
        ts = rec["created_at"]
        if isinstance(ts, str) and "T" in ts:
            try:
                dt = datetime.fromisoformat(ts)
                ts = dt.strftime("%Y-%m-%d %H:%M %Z").strip() or dt.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                ts = ts[:16].replace("T", " ")
        content = rec["content"]
        if len(content) > 200:
            content = content[:200] + "…"

        lines.append(
            f"{emoji} *{cat}* — {ts}\n"
            f"_{_escape_md(content)}_\n"
        )

    response = "\n".join(lines)
    if len(response) > 3900:
        response = response[:3900] + "\n\n_[truncated]_"

    await update.message.reply_text(response, parse_mode="Markdown")


# ─────────────────────────────────────────────────────────────────
# Unknown command handler
# ─────────────────────────────────────────────────────────────────

@operator_only
async def cmd_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "⬜ Unknown command. Use /help for an overview."
    )


# ─────────────────────────────────────────────────────────────────
# Trainer free-text handler — stages knowledge updates for review
# ─────────────────────────────────────────────────────────────────

async def handle_trainer_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles free-text messages from trainer IDs (e.g. Lars).
    If the message is a reply to a bot message, captures the bot answer
    as context so the operator can see exactly what Lars is correcting.

    Approval flow:
        Trainer sends/replies → staged in DB → operator notified with context
        → operator uses /approve <id> or /reject <id> to action it
    """
    uid = update.effective_user.id
    if uid not in TRAINER_IDS:
        return  # Not a trainer — ignore

    text = update.message.text or ""
    if not text.strip():
        return

    trainer_name = update.effective_user.first_name or f"Trainer {uid}"
    logger.info("Trainer message received from %s (%s): %s", trainer_name, uid, text[:100])

    # Check if this is a reply to a bot message — capture context
    reply_context = None
    replied_msg = update.message.reply_to_message
    if replied_msg and replied_msg.from_user and replied_msg.from_user.is_bot:
        bot_text = replied_msg.text or ""
        reply_context = {"bot_answer": bot_text[:1000]}
        logger.info("Trainer is replying to bot message: %s", bot_text[:100])

    # Stage in PostgreSQL if available
    staged_id = None
    if DATABASE_URL:
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS staged_knowledge (
                        id SERIAL PRIMARY KEY,
                        trainer_id BIGINT NOT NULL,
                        trainer_name TEXT,
                        content TEXT NOT NULL,
                        reply_context JSONB,
                        status VARCHAR(20) NOT NULL DEFAULT 'pending',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        reviewed_at TIMESTAMPTZ,
                        reviewed_by BIGINT
                    )
                """)
                await conn.execute("""
                    ALTER TABLE staged_knowledge ADD COLUMN IF NOT EXISTS reply_context JSONB
                """)
                staged_id = await conn.fetchval("""
                    INSERT INTO staged_knowledge (trainer_id, trainer_name, content, reply_context)
                    VALUES ($1, $2, $3, $4) RETURNING id
                """, uid, trainer_name, text,
                    json.dumps(reply_context) if reply_context else None)
            finally:
                await conn.close()
        except Exception as e:
            logger.error("Failed to stage trainer message: %s", e)

    # Acknowledge to trainer
    await update.message.reply_text(
        f"✅ Thanks {trainer_name}! Your update has been received and is pending review.",
    )

    # Build operator notification with optional reply context
    preview = text[:300] + ("…" if len(text) > 300 else "")
    id_label = f" \\(ID: `{staged_id}`\\)" if staged_id else ""
    notification_parts = [
        f"📥 *New knowledge update from {_escape_md(trainer_name)}*{id_label}",
    ]
    if reply_context and reply_context.get("bot_answer"):
        bot_preview = reply_context["bot_answer"][:300] + ("…" if len(reply_context["bot_answer"]) > 300 else "")
        notification_parts.append(f"\n*Bot answered:*\n_{_escape_md(bot_preview)}_")
        notification_parts.append(f"\n*Lars corrects/adds:*\n_{_escape_md(preview)}_")
    else:
        notification_parts.append(f"\n_{_escape_md(preview)}_")
    notification_parts.append(
        f"\n`/approve {staged_id}` — add to ChromaDB\n"
        f"`/reject {staged_id}` — discard"
    )

    try:
        await context.bot.send_message(
            chat_id=OPERATOR_CHAT_ID,
            text="\n".join(notification_parts),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("Failed to notify operator of trainer message: %s", e)


@operator_only
async def cmd_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Approve a staged knowledge update and add it to ChromaDB."""
    parts = (update.message.text or "").split(None, 1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await update.message.reply_text("Usage: `/approve <id>`", parse_mode="Markdown")
        return

    staged_id = int(parts[1].strip())

    if not DATABASE_URL:
        await update.message.reply_text("❌ Database not configured.")
        return

    try:
        conn = await asyncpg.connect(DATABASE_URL)
        try:
            row = await conn.fetchrow(
                "SELECT * FROM staged_knowledge WHERE id = $1 AND status = 'pending'",
                staged_id
            )
            if not row:
                await update.message.reply_text(f"❌ No pending update with ID `{staged_id}`.", parse_mode="Markdown")
                return

            content = row["content"]
            trainer_name = row["trainer_name"] or "trainer"

            # Add to ChromaDB
            kb = _get_knowledge_base()
            chunk_id = f"trainer::{row['trainer_id']}::staged::{staged_id}"
            await asyncio.to_thread(
                kb.collection.add,
                ids=[chunk_id],
                documents=[content],
                metadatas=[{
                    "source_type": "trainer_update",
                    "trainer_id": str(row["trainer_id"]),
                    "trainer_name": trainer_name,
                    "staged_id": staged_id,
                    "filename": f"trainer_{trainer_name}.txt",
                    "chunk_index": 1,
                }],
            )

            # Mark as approved
            await conn.execute(
                "UPDATE staged_knowledge SET status = 'approved', reviewed_at = NOW(), reviewed_by = $1 WHERE id = $2",
                update.effective_user.id, staged_id
            )
        finally:
            await conn.close()
    except Exception as e:
        logger.error("Approve failed: %s", e)
        await update.message.reply_text(f"❌ Error: `{_escape_md(type(e).__name__)}`", parse_mode="Markdown")
        return

    await update.message.reply_text(
        f"✅ Update `{staged_id}` approved and added to ChromaDB.\n"
        f"_{_escape_md(content[:200])}_",
        parse_mode="Markdown",
    )


@operator_only
async def cmd_reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reject and discard a staged knowledge update."""
    parts = (update.message.text or "").split(None, 1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await update.message.reply_text("Usage: `/reject <id>`", parse_mode="Markdown")
        return

    staged_id = int(parts[1].strip())

    if not DATABASE_URL:
        await update.message.reply_text("❌ Database not configured.")
        return

    try:
        conn = await asyncpg.connect(DATABASE_URL)
        try:
            result = await conn.execute(
                "UPDATE staged_knowledge SET status = 'rejected', reviewed_at = NOW(), reviewed_by = $1 WHERE id = $2 AND status = 'pending'",
                update.effective_user.id, staged_id
            )
            if result == "UPDATE 0":
                await update.message.reply_text(f"❌ No pending update with ID `{staged_id}`.", parse_mode="Markdown")
                return
        finally:
            await conn.close()
    except Exception as e:
        logger.error("Reject failed: %s", e)
        await update.message.reply_text(f"❌ Error: `{_escape_md(type(e).__name__)}`", parse_mode="Markdown")
        return

    await update.message.reply_text(f"🗑️ Update `{staged_id}` rejected and discarded.", parse_mode="Markdown")


# ─────────────────────────────────────────────────────────────────
# Global error handler
# ─────────────────────────────────────────────────────────────────

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catches all unexpected errors and logs them. Sends a notification to the operator."""
    logger.error("Unexpected error: %s", context.error, exc_info=context.error)
    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"❌ Unexpected error: {type(context.error).__name__}. It has been logged.",
            )
        except Exception as notify_error:
            logger.error("Failed to send error notification: %s", notify_error)


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _escape_md(text: str) -> str:
    """Escape special characters for Telegram Markdown v1."""
    # Escape backslash first to avoid double-escaping, then special chars
    text = text.replace("\\", "\\\\")
    for char in ["_", "*", "`", "[", "]"]:
        text = text.replace(char, f"\\{char}")
    return text


# ─────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────

async def _on_startup(app) -> None:
    """Initialize services at bot startup (before polling starts)."""
    reflection = _get_reflection_log()
    if reflection is not None:
        try:
            await reflection.initialize()
            logger.info("ReflectionLog schema initialized at startup")
        except Exception as e:
            logger.warning("ReflectionLog initialization failed (DB down?): %s", e)

    # Pre-warm the KnowledgeBase singleton so the first /ask or /explain
    # has no cold-start delay. Errors are not fatal — the bot starts fine
    # without a pre-warmed KB.
    try:
        await asyncio.to_thread(_get_knowledge_base)
        logger.info("KnowledgeBase singleton pre-warmed at startup")
    except Exception as e:
        logger.warning("KnowledgeBase pre-warming failed (ChromaDB down?): %s", e)

    # Write health sentinel file for the Docker health check.
    # The health check (docker-compose.sandbox.yaml) tests for this file.
    try:
        with open("/tmp/kaironis_healthy", "w") as f:
            f.write(datetime.now(tz=timezone.utc).isoformat())
        logger.info("Health sentinel file written: /tmp/kaironis_healthy")
    except OSError as e:
        logger.warning("Could not write health sentinel file: %s", e)


def main() -> None:
    """Start the Telegram bot."""
    if not BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not set in environment variables")

    if not OPERATOR_CHAT_ID:
        raise ValueError("TELEGRAM_OPERATOR_CHAT_ID not set in environment variables")

    logger.info("Kaironis Bot v%s starting...", agent_state['version'])

    app = Application.builder().token(BOT_TOKEN).post_init(_on_startup).build()

    # Register commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("myid", cmd_myid))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("emergency", cmd_emergency))

    # Knowledge base
    app.add_handler(CommandHandler("ask", cmd_ask))
    app.add_handler(CommandHandler("explain", cmd_explain))

    # Reflection
    app.add_handler(CommandHandler("note", cmd_note))
    app.add_handler(CommandHandler("lesson", cmd_lesson))
    app.add_handler(CommandHandler("notes", cmd_notes))

    # Knowledge staging — trainer free-text + operator approval
    app.add_handler(CommandHandler("approve", cmd_approve))
    app.add_handler(CommandHandler("reject", cmd_reject))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_trainer_message))

    # Unknown commands fallback — must be registered last
    app.add_handler(MessageHandler(filters.COMMAND, cmd_unknown))

    # Global error handler
    app.add_error_handler(error_handler)

    logger.info("Bot started. Waiting for messages...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
