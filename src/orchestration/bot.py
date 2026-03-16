"""
Kaironis Telegram Bot — Operator Interface

Commands:
    /start      - Welkomstbericht
    /help       - Overzicht van commando's
    /status     - Huidige agent status + ChromaDB status
    /pause      - Pauzeer autonome trading
    /resume     - Hervat autonome trading
    /emergency  - KILL SWITCH — stop alles onmiddellijk
    /ask        - Query de TCT strategy knowledge base (ruwe chunks)
    /explain    - RAG: stel een vraag, krijg een samenvatting via AI
    /note       - Sla een marktobservatie op
    /lesson     - Sla een les op
    /notes      - Toon de laatste 5 notities

Architecture:
    - Async via python-telegram-bot v21
    - State management via Redis
    - Audit logging via structured JSON
    - Memory via ChromaDB + PostgreSQL
"""

import asyncio
import logging
import os
import requests
import sys
import threading
from datetime import datetime, timezone
from urllib.parse import quote_plus

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Structured logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
_raw_operator_id = os.getenv("TELEGRAM_OPERATOR_CHAT_ID", "0")
try:
    OPERATOR_CHAT_ID = int(_raw_operator_id)
except ValueError:
    logger.critical(
        "TELEGRAM_OPERATOR_CHAT_ID moet een integer zijn, kreeg: %r — bot kan niet starten.",
        _raw_operator_id,
    )
    sys.exit(
        f"Fout: TELEGRAM_OPERATOR_CHAT_ID moet een integer zijn, kreeg: {_raw_operator_id!r}"
    )

# Ollama config (strip http:// prefix als aanwezig)
_ollama_raw = os.getenv("OLLAMA_HOST", "localhost")
OLLAMA_HOST = _ollama_raw.replace("http://", "").replace("https://", "").split(":")[0]
OLLAMA_PORT = int(os.getenv("OLLAMA_PORT", "11434"))

# DATABASE_URL: gebruik directe URL of stel samen uit losse variabelen.
# Alleen als POSTGRES_HOST expliciet gezet is, anders blijft DATABASE_URL None
# zodat _get_reflection_log() correct None teruggeeft en de handlers de
# "DB niet geconfigureerd" melding tonen.
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

# Agent state (in-memory voor nu, later via Redis)
agent_state = {
    "trading_active": False,
    "paused": False,
    "emergency_stop": False,
    "started_at": datetime.now(tz=timezone.utc).isoformat(),
    "version": "0.3.0",
}

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


# ─────────────────────────────────────────────
# Security — alleen operator mag commando's geven
# ─────────────────────────────────────────────

def operator_only(func):
    """Decorator: blokkeer iedereen die geen operator is."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != OPERATOR_CHAT_ID:
            logger.warning(
                f"Ongeautoriseerde toegang van user {update.effective_user.id}"
            )
            await update.message.reply_text(
                "⛔ Niet geautoriseerd. Alleen de operator kan Kaironis aansturen."
            )
            return
        return await func(update, context)
    wrapper.__name__ = func.__name__
    return wrapper


# ─────────────────────────────────────────────
# Command Handlers
# ─────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welkomstbericht bij eerste contact."""
    await update.message.reply_text(
        "⚡ *Kaironis online.*\n\n"
        "Ik ben je autonome trading partner.\n"
        "Gebruik /help voor een overzicht van commando's.\n\n"
        "_The opportune moment awaits._",
        parse_mode="Markdown",
    )


@operator_only
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Overzicht van alle commando's."""
    help_text = (
        "🤖 *Kaironis Command Overview*\n\n"
        "*Status & Info*\n"
        "/status — Huidige agent + ChromaDB status\n"
        "/help — Dit overzicht\n\n"
        "*Trading Control*\n"
        "/pause — Pauzeer autonome trading\n"
        "/resume — Hervat autonome trading\n\n"
        "*Knowledge Base*\n"
        "/ask \\[vraag\\] — Query de TCT strategy knowledge base\n\n"
        "*Notities & Learnings*\n"
        "/note \\[tekst\\] — Sla een marktobservatie op\n"
        "/lesson \\[tekst\\] — Sla een les op\n"
        "/notes — Toon de laatste 5 notities\n\n"
        "*Emergency*\n"
        "/emergency — ⛔ KILL SWITCH — stop alles\n\n"
        f"_v{agent_state['version']} — Memory Query & Reflection System_"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


@operator_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Geef huidige agent status + ChromaDB status."""
    status_emoji = "🔴" if agent_state["emergency_stop"] else \
                   "⏸️" if agent_state["paused"] else \
                   "🟢" if agent_state["trading_active"] else "🟡"

    status_text = "EMERGENCY STOP" if agent_state["emergency_stop"] else \
                  "Gepauzeerd" if agent_state["paused"] else \
                  "Trading actief" if agent_state["trading_active"] else "Standby"

    # ChromaDB status check
    chroma_status = "❓ Niet gecheckt"
    chroma_count = ""
    try:
        kb = _get_knowledge_base()
        stats = await asyncio.to_thread(kb.get_stats)
        count = stats.get("document_count", 0)
        chroma_status = "✅ Bereikbaar"
        chroma_count = f"\n*Chunks in collection:* {count}"
    except Exception as e:
        chroma_status = f"❌ Niet bereikbaar ({_escape_md(type(e).__name__)})"
        logger.warning("ChromaDB status check mislukt: %s", e)

    message = (
        f"{status_emoji} *Kaironis Status*\n\n"
        f"*Status:* {status_text}\n"
        f"*Versie:* {agent_state['version']}\n"
        f"*Online sinds:* {agent_state['started_at']} UTC\n\n"
        f"*Trading:* {'Actief ✅' if agent_state['trading_active'] else 'Inactief ⏹️'}\n"
        f"*Gepauzeerd:* {'Ja ⏸️' if agent_state['paused'] else 'Nee'}\n"
        f"*Emergency stop:* {'JA 🚨' if agent_state['emergency_stop'] else 'Nee'}\n\n"
        f"*ChromaDB:* {chroma_status}{chroma_count}"
    )
    await update.message.reply_text(message, parse_mode="Markdown")


@operator_only
async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pauzeer autonome trading."""
    if agent_state["emergency_stop"]:
        await update.message.reply_text(
            "🚨 Emergency stop is actief. Gebruik /resume om te herstarten na review."
        )
        return

    agent_state["paused"] = True
    agent_state["trading_active"] = False
    logger.info(f"Trading gepauzeerd door operator {update.effective_user.id}")

    await update.message.reply_text(
        "⏸️ *Trading gepauzeerd.*\n\n"
        "Kaironis monitort nog wel de markten maar voert geen trades uit.\n"
        "Gebruik /resume om te hervatten.",
        parse_mode="Markdown",
    )


@operator_only
async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Hervat autonome trading."""
    agent_state["paused"] = False
    agent_state["emergency_stop"] = False
    agent_state["trading_active"] = True
    logger.info(f"Trading hervat door operator {update.effective_user.id}")

    await update.message.reply_text(
        "▶️ *Trading hervat.*\n\n"
        "Kaironis is weer actief en monitort op setups.\n"
        "Gebruik /status voor actuele staat.",
        parse_mode="Markdown",
    )


@operator_only
async def cmd_emergency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """KILL SWITCH — stop alles onmiddellijk."""
    agent_state["emergency_stop"] = True
    agent_state["trading_active"] = False
    agent_state["paused"] = True

    logger.critical(
        f"EMERGENCY STOP geactiveerd door operator {update.effective_user.id}"
    )

    await update.message.reply_text(
        "🚨 *EMERGENCY STOP GEACTIVEERD*\n\n"
        "✅ Alle trading gestopt\n"
        "✅ Geen nieuwe posities mogelijk\n"
        "✅ Monitors gepauzeerd\n\n"
        "_Review de situatie en gebruik /resume om te hervatten._",
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────────
# Memory Query — /ask
# ─────────────────────────────────────────────

@operator_only
async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Query de TCT strategy knowledge base via ChromaDB."""
    # Haal de vraag op uit de message tekst
    message_text = update.message.text or ""
    # Strip het /ask commando
    parts = message_text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await update.message.reply_text(
            "❓ Gebruik: `/ask [vraag]`\n\nVoorbeeld: `/ask wat is PO3?`",
            parse_mode="Markdown",
        )
        return

    question = parts[1].strip()

    # Stuur "typing..." indicator
    await update.message.chat.send_action("typing")

    try:
        kb = _get_knowledge_base()
        # Fetch more and filter chunk_index=0 (often header-only chunks)
        raw = await asyncio.to_thread(kb.query_strategy, question, 10)
        results = [r for r in raw if r.get("metadata", {}).get("chunk_index", 1) != 0][:3]
        # Fallback: also filter on chunk_index to avoid reintroducing header-only chunks
        if not results:
            results = [r for r in raw if r.get("metadata", {}).get("chunk_index", 1) != 0][:3]
    except Exception as e:
        logger.error("KnowledgeBase query failed: %s", e)
        await update.message.reply_text(
            f"❌ Fout bij query naar knowledge base: `{_escape_md(type(e).__name__)}`",
            parse_mode="Markdown",
        )
        return

    if not results:
        await update.message.reply_text(
            "🔍 Geen relevante informatie gevonden voor deze vraag.\n\n"
            "_Controleer of de knowledge base geïngesteerd is._",
            parse_mode="Markdown",
        )
        return

    # Bouw het antwoord op
    lines = [f"🧠 *Kennis over: {_escape_md(question)}*\n"]

    for i, result in enumerate(results, 1):
        doc = result.get("document", "")
        meta = result.get("metadata", {})
        distance = result.get("distance", 1.0)
        relevance = max(0.0, 1.0 - distance)

        # Metadata keys: filename, source_file, chunk_index
        filename = meta.get("filename") or meta.get("source_file") or meta.get("source") or "onbekend"
        # Strip pad prefix als aanwezig
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
            f"(chunk {chunk_idx}, relevantie: {relevance:.0%})\n"
            f"{_escape_md(doc_preview)}\n"
        )

    response = "\n".join(lines)

    # Zorg dat we onder de 4000-teken Telegram limiet blijven
    if len(response) > 3900:
        response = response[:3900] + "\n\n_[afgekapt]_"

    await update.message.reply_text(response, parse_mode="Markdown")


# ─────────────────────────────────────────────
# RAG — /explain
# ─────────────────────────────────────────────

OLLAMA_GENERATE_MODEL = os.getenv("OLLAMA_GENERATE_MODEL", "llama3.2:latest")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")

@operator_only
async def cmd_explain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """RAG: stel een vraag, krijg een AI-samenvatting op basis van TCT docs."""
    message_text = update.message.text or ""
    parts = message_text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await update.message.reply_text(
            "🤖 Gebruik: `/explain [vraag]`\n\nVoorbeeld: `/explain wat is PO3 en hoe gebruik ik het?`",
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
        # Fallback: keep chunk_index filter to avoid reintroducing header-only chunks
        if not chunks:
            chunks = [r for r in raw if r.get("metadata", {}).get("chunk_index", 1) != 0][:5]
    except Exception as e:
        await update.message.reply_text(
            f"❌ ChromaDB fout: `{_escape_md(type(e).__name__)}`",
            parse_mode="Markdown",
        )
        return

    if not chunks:
        await update.message.reply_text("🔍 Geen relevante informatie gevonden.")
        return

    # Stap 2: Bouw context op
    context_parts = []
    for i, r in enumerate(chunks, 1):
        meta = r.get("metadata", {})
        filename = meta.get("filename", "onbekend").replace(".md", "")
        doc = r.get("document", "")
        doc_lines = [line for line in doc.split("\n") if line.strip() and not line.strip().startswith("#")]
        content = " ".join(doc_lines).strip()[:800]
        if content:
            context_parts.append(f"[Bron {i}: {filename}]\n{content}")

    # Stop early als er na opschoning geen bruikbare context is
    if not context_parts:
        await update.message.reply_text(
            "🔍 Geen relevante informatie gevonden na opschoning van de gevonden chunks."
        )
        return

    context_text = "\n\n".join(context_parts)

    prompt = f"""Je bent Kaironis, een AI trading assistent gespecialiseerd in de TCT (Time-Cycle Trading) strategie.
Beantwoord de volgende vraag op basis van de gegeven TCT documentatie. Wees concreet en praktisch.
Antwoord in het Nederlands. Maximaal 400 woorden.

VRAAG: {question}

TCT DOCUMENTATIE:
{context_text}

ANTWOORD:"""

    # Stap 3: Genereer antwoord via OpenRouter (Gemini Flash)
    await update.message.reply_text("⏳ Even nadenken op basis van de TCT docs...")
    await update.message.chat.send_action("typing")

    if not OPENROUTER_API_KEY:
        await update.message.reply_text("❌ OPENROUTER\\_API\\_KEY niet ingesteld.", parse_mode="Markdown")
        return

    try:
        # asyncio.to_thread() voorkomt dat de blocking HTTP-call de event loop blokkeert.
        # Zo kan /emergency ook reageren terwijl OpenRouter nadenkt.
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
        err = _escape_md(f"{type(e).__name__}: {e}")
        await update.message.reply_text(
            f"❌ OpenRouter fout: `{err}`",
            parse_mode="Markdown",
        )
        return

    if not answer:
        await update.message.reply_text("❌ Leeg antwoord van het model.")
        return

    # Stap 4: Stuur antwoord
    sources = ", ".join(
        {r.get("metadata", {}).get("filename", "?").replace(".md", "") for r in chunks}
    )
    header = f"🤖 {question}\n\n"
    footer = f"\n\nBronnen: {sources}"

    response = header + answer + footer
    if len(response) > 3900:
        response = response[:3900] + "\n\n[afgekapt]"

    await update.message.reply_text(response)


# ─────────────────────────────────────────────
# Reflection Commands — /note, /lesson, /notes
# ─────────────────────────────────────────────

@operator_only
async def cmd_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sla een marktobservatie op."""
    message_text = update.message.text or ""
    parts = message_text.split(None, 1)

    if len(parts) < 2 or not parts[1].strip():
        await update.message.reply_text(
            "📝 Gebruik: `/note [tekst]`\n\nVoorbeeld: `/note DXY loopt in supply zone op H4`",
            parse_mode="Markdown",
        )
        return

    content = parts[1].strip()
    reflection = _get_reflection_log()

    if reflection is None:
        await update.message.reply_text(
            "❌ Database niet geconfigureerd (DATABASE\\_URL ontbreekt).",
            parse_mode="Markdown",
        )
        return

    try:
        record_id = await reflection.log_observation(
            category="market_observation",
            content=content,
            metadata={"telegram_user": update.effective_user.id},
        )
        await update.message.reply_text(
            f"✅ Observatie opgeslagen (id: {record_id})\n\n_{_escape_md(content)}_",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("Note opslaan mislukt: %s", e)
        await update.message.reply_text(
            f"❌ Fout bij opslaan: `{_escape_md(type(e).__name__)}`",
            parse_mode="Markdown",
        )


@operator_only
async def cmd_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sla een les op als 'lesson_learned'."""
    message_text = update.message.text or ""
    parts = message_text.split(None, 1)

    if len(parts) < 2 or not parts[1].strip():
        await update.message.reply_text(
            "🎓 Gebruik: `/lesson [tekst]`\n\nVoorbeeld: `/lesson Nooit traden in eerste 5 min na NY open`",
            parse_mode="Markdown",
        )
        return

    content = parts[1].strip()
    reflection = _get_reflection_log()

    if reflection is None:
        await update.message.reply_text(
            "❌ Database niet geconfigureerd (DATABASE\\_URL ontbreekt).",
            parse_mode="Markdown",
        )
        return

    try:
        record_id = await reflection.log_observation(
            category="lesson_learned",
            content=content,
            metadata={"telegram_user": update.effective_user.id},
        )
        await update.message.reply_text(
            f"🎓 Lesson learned opgeslagen (id: {record_id})\n\n_{_escape_md(content)}_",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("Lesson opslaan mislukt: %s", e)
        await update.message.reply_text(
            f"❌ Fout bij opslaan: `{_escape_md(type(e).__name__)}`",
            parse_mode="Markdown",
        )


@operator_only
async def cmd_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toon de laatste 5 notities."""
    reflection = _get_reflection_log()

    if reflection is None:
        await update.message.reply_text(
            "❌ Database niet geconfigureerd (DATABASE\\_URL ontbreekt).",
            parse_mode="Markdown",
        )
        return

    try:
        records = await reflection.get_recent(limit=5)
    except Exception as e:
        logger.error("Notes ophalen mislukt: %s", e)
        await update.message.reply_text(
            f"❌ Fout bij ophalen notities: `{_escape_md(type(e).__name__)}`",
            parse_mode="Markdown",
        )
        return

    if not records:
        await update.message.reply_text(
            "📭 Nog geen notities opgeslagen.\n\n"
            "Gebruik `/note` of `/lesson` om te beginnen.",
            parse_mode="Markdown",
        )
        return

    lines = ["📋 *Laatste notities:*\n"]
    category_emoji = {
        "market_observation": "👁️",
        "lesson_learned": "🎓",
        "trade_setup": "📊",
        "strategy_note": "📌",
    }

    for rec in records:
        emoji = category_emoji.get(rec["category"], "📝")
        cat = rec["category"].replace("_", " ").title()
        # Timestamp: parse ISO8601 volledig (timezone-aware) en formatteer leesbaar
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
        response = response[:3900] + "\n\n_[afgekapt]_"

    await update.message.reply_text(response, parse_mode="Markdown")


# ─────────────────────────────────────────────
# Unknown command handler
# ─────────────────────────────────────────────

@operator_only
async def cmd_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "❓ Onbekend commando. Gebruik /help voor een overzicht."
    )


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _escape_md(text: str) -> str:
    """Escape special characters voor Telegram Markdown v1."""
    # Escape backslash first to avoid double-escaping, then special chars
    text = text.replace("\\", "\\\\")
    for char in ["_", "*", "`", "[", "]"]:
        text = text.replace(char, f"\\{char}")
    return text


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

async def _on_startup(app) -> None:
    """Initialiseer services bij bot startup (vóór polling start)."""
    reflection = _get_reflection_log()
    if reflection is not None:
        try:
            await reflection.initialize()
            logger.info("ReflectionLog schema geïnitialiseerd bij startup")
        except Exception as e:
            logger.warning("ReflectionLog initialisatie mislukt (DB down?): %s", e)


def main() -> None:
    """Start de Telegram bot."""
    if not BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN niet ingesteld in environment variabelen")

    if not OPERATOR_CHAT_ID:
        raise ValueError("TELEGRAM_OPERATOR_CHAT_ID niet ingesteld in environment variabelen")

    logger.info(f"Kaironis Bot v{agent_state['version']} wordt gestart...")

    app = Application.builder().token(BOT_TOKEN).post_init(_on_startup).build()

    # Commands registreren
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("emergency", cmd_emergency))

    # Memory Query
    app.add_handler(CommandHandler("ask", cmd_ask))
    app.add_handler(CommandHandler("explain", cmd_explain))

    # Reflection
    app.add_handler(CommandHandler("note", cmd_note))
    app.add_handler(CommandHandler("lesson", cmd_lesson))
    app.add_handler(CommandHandler("notes", cmd_notes))

    logger.info("Bot gestart. Wachten op berichten...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
