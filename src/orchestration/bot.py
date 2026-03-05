"""
Kaironis Telegram Bot — Operator Interface

Commands:
    /start    - Welkomstbericht
    /help     - Overzicht van commando's
    /status   - Huidige agent status
    /pause    - Pauzeer autonome trading
    /resume   - Hervat autonome trading
    /emergency - KILL SWITCH — stop alles onmiddellijk

Architecture:
    - Async via python-telegram-bot v21
    - State management via Redis
    - Audit logging via structured JSON
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

# Agent state (in-memory voor nu, later via Redis)
agent_state = {
    "trading_active": False,
    "paused": False,
    "emergency_stop": False,
    "started_at": datetime.utcnow().isoformat(),
    "version": "0.1.0",
}


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
        "/status — Huidige agent status\n"
        "/help — Dit overzicht\n\n"
        "*Trading Control*\n"
        "/pause — Pauzeer autonome trading\n"
        "/resume — Hervat autonome trading\n\n"
        "*Emergency*\n"
        "/emergency — ⛔ KILL SWITCH — stop alles\n\n"
        "_Meer commando's worden toegevoegd in volgende fases._"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


@operator_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Geef huidige agent status."""
    status_emoji = "🔴" if agent_state["emergency_stop"] else \
                   "⏸️" if agent_state["paused"] else \
                   "🟢" if agent_state["trading_active"] else "🟡"

    status_text = "EMERGENCY STOP" if agent_state["emergency_stop"] else \
                  "Gepauzeerd" if agent_state["paused"] else \
                  "Trading actief" if agent_state["trading_active"] else "Standby"

    message = (
        f"{status_emoji} *Kaironis Status*\n\n"
        f"*Status:* {status_text}\n"
        f"*Versie:* {agent_state['version']}\n"
        f"*Online sinds:* {agent_state['started_at']} UTC\n\n"
        f"*Trading:* {'Actief ✅' if agent_state['trading_active'] else 'Inactief ⏹️'}\n"
        f"*Gepauzeerd:* {'Ja ⏸️' if agent_state['paused'] else 'Nee'}\n"
        f"*Emergency stop:* {'JA 🚨' if agent_state['emergency_stop'] else 'Nee'}"
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
# Unknown command handler
# ─────────────────────────────────────────────

@operator_only
async def cmd_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "❓ Onbekend commando. Gebruik /help voor een overzicht."
    )


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

    logger.info("Bot gestart. Wachten op berichten...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
