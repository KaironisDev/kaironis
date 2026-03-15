"""
Kaironis Telegram Bot — Operator Interface

Commands:
    /start      - Welkomstbericht
    /help       - Overzicht van commando's
    /status     - Huidige agent status + ChromaDB status
    /pause      - Pauzeer autonome trading
    /resume     - Hervat autonome trading
    /emergency  - KILL SWITCH — stop alles onmiddellijk
    /ask        - Query de TCT strategy knowledge base
    /note       - Sla een marktobservatie op
    /lesson     - Sla een les op
    /notes      - Toon de laatste 5 notities

Architecture:
    - Async via python-telegram-bot v21
    - State management via Redis
    - Audit logging via structured JSON
    - Memory via ChromaDB + PostgreSQL
"""

import logging
import os
from datetime import datetime

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
OPERATOR_CHAT_ID = int(os.getenv("TELEGRAM_OPERATOR_CHAT_ID", "0"))

# DATABASE_URL: gebruik directe URL of stel samen uit losse variabelen
DATABASE_URL = os.getenv("DATABASE_URL") or (
    "postgresql://{user}:{password}@{host}:{port}/{db}".format(
        user=os.getenv("POSTGRES_USER", "kaironis"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        db=os.getenv("POSTGRES_DB", "kaironis"),
    )
)

# Agent state (in-memory voor nu, later via Redis)
agent_state = {
    "trading_active": False,
    "paused": False,
    "emergency_stop": False,
    "started_at": datetime.utcnow().isoformat(),
    "version": "0.2.0",
}

# Lazy-initialized ReflectionLog
_reflection_log = None


def _get_reflection_log():
    """Lazy initialisatie van de ReflectionLog."""
    global _reflection_log
    if _reflection_log is None and DATABASE_URL:
        from src.memory.reflection import ReflectionLog
        _reflection_log = ReflectionLog(dsn=DATABASE_URL)
    return _reflection_log


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
        "_v0.2.0 — Memory Query & Reflection System_"
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
        from src.memory.knowledge_base import KnowledgeBase
        kb = KnowledgeBase()
        stats = kb.get_stats()
        count = stats.get("document_count", 0)
        chroma_status = "✅ Bereikbaar"
        chroma_count = f"\n*Chunks in collection:* {count}"
    except Exception as e:
        chroma_status = f"❌ Niet bereikbaar ({type(e).__name__})"
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
        from src.memory.knowledge_base import KnowledgeBase
        kb = KnowledgeBase()
        # Haal meer results op zodat we lege/header chunks kunnen filteren
        raw_results = kb.query_strategy(question, n_results=8)
        # Filter chunks die alleen headers/separators bevatten
        results = []
        for r in raw_results:
            doc = r.get("document", "")
            real_lines = [l for l in doc.split("\n")
                         if l.strip() and not l.strip().startswith("#") and l.strip() != "---"]
            real_content = " ".join(real_lines).strip()
            if len(real_content) > 80:  # minimaal 80 tekens echte content
                r["_real_content"] = real_content
                results.append(r)
            if len(results) >= 3:
                break
    except Exception as e:
        logger.error("KnowledgeBase query mislukt: %s", e)
        await update.message.reply_text(
            f"❌ Fout bij query naar knowledge base: `{type(e).__name__}: {e}`",
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

        # Gebruik de voorgefilterde content
        doc_preview = result.get("_real_content", "")
        if not doc_preview:
            doc_lines = [l for l in doc.split("\n") if l.strip() and not l.strip().startswith("#")]
            doc_preview = " ".join(doc_lines)[:600] if doc_lines else doc[:600]
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
        # Initialiseer tabel als nodig
        await reflection.initialize()
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
            f"❌ Fout bij opslaan: `{type(e).__name__}: {e}`",
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
        await reflection.initialize()
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
            f"❌ Fout bij opslaan: `{type(e).__name__}: {e}`",
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
        await reflection.initialize()
        records = await reflection.get_recent(limit=5)
    except Exception as e:
        logger.error("Notes ophalen mislukt: %s", e)
        await update.message.reply_text(
            f"❌ Fout bij ophalen notities: `{type(e).__name__}: {e}`",
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
        # Datum afkappen tot datum+tijd
        ts = rec["created_at"]
        if isinstance(ts, str) and "T" in ts:
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
    # In Markdown v1 zijn _*`[ de speciale tekens
    for char in ["_", "*", "`", "["]:
        text = text.replace(char, f"\\{char}")
    return text


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main() -> None:
    """Start de Telegram bot."""
    if not BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN niet ingesteld in environment variabelen")

    if not OPERATOR_CHAT_ID:
        raise ValueError("TELEGRAM_OPERATOR_CHAT_ID niet ingesteld in environment variabelen")

    logger.info(f"Kaironis Bot v{agent_state['version']} wordt gestart...")

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands registreren
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("emergency", cmd_emergency))

    # Memory Query
    app.add_handler(CommandHandler("ask", cmd_ask))

    # Reflection
    app.add_handler(CommandHandler("note", cmd_note))
    app.add_handler(CommandHandler("lesson", cmd_lesson))
    app.add_handler(CommandHandler("notes", cmd_notes))

    logger.info("Bot gestart. Wachten op berichten...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
