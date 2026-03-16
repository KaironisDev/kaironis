"""
Kaironis Telegram Bot — Operator Interface

Commands:
    /start     - Welcome message
    /help      - Command overview
    /status    - Current agent status
    /pause     - Pause autonomous trading
    /resume    - Resume autonomous trading
    /emergency - KILL SWITCH — stop everything immediately
    /ask       - Query the TCT knowledge base
    /explain   - Have Kaironis explain a concept via OpenRouter

Architecture:
    - Async via python-telegram-bot v21
    - State management via Redis
    - Audit logging via structured JSON
"""

import asyncio
import logging
import os
from datetime import datetime, timezone

import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from src.memory.knowledge_base import KnowledgeBase

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

# Agent state (in-memory for now, later via Redis)
agent_state = {
    "trading_active": False,
    "paused": False,
    "emergency_stop": False,
    "started_at": datetime.now(tz=timezone.utc).isoformat(),
    "version": "0.1.0",
}


# ─────────────────────────────────────────────
# Security — only the operator may issue commands
# ─────────────────────────────────────────────

def operator_only(func):
    """Decorator: block everyone who is not the operator."""
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
    wrapper.__name__ = func.__name__
    return wrapper


# ─────────────────────────────────────────────
# Command Handlers
# ─────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message on first contact."""
    await update.message.reply_text(
        "⚡ *Kaironis online.*\n\n"
        "I am your autonomous trading partner.\n"
        "Use /help for a command overview.\n\n"
        "_The opportune moment awaits._",
        parse_mode="Markdown",
    )


@operator_only
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Overview of all commands."""
    help_text = (
        "🤖 *Kaironis Command Overview*\n\n"
        "*Status & Info*\n"
        "/status — Current agent status\n"
        "/help — This overview\n\n"
        "*Trading Control*\n"
        "/pause — Pause autonomous trading\n"
        "/resume — Resume autonomous trading\n\n"
        "*Emergency*\n"
        "/emergency — ⛔ KILL SWITCH — stop everything\n\n"
        "_More commands will be added in upcoming phases._"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


@operator_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return current agent status."""
    status_emoji = "🔴" if agent_state["emergency_stop"] else \
                   "⏸️" if agent_state["paused"] else \
                   "🟢" if agent_state["trading_active"] else "🟡"

    status_text = "EMERGENCY STOP" if agent_state["emergency_stop"] else \
                  "Paused" if agent_state["paused"] else \
                  "Trading active" if agent_state["trading_active"] else "Standby"

    message = (
        f"{status_emoji} *Kaironis Status*\n\n"
        f"*Status:* {status_text}\n"
        f"*Version:* {agent_state['version']}\n"
        f"*Online since:* {agent_state['started_at']} UTC\n\n"
        f"*Trading:* {'Active ✅' if agent_state['trading_active'] else 'Inactive ⏹️'}\n"
        f"*Paused:* {'Yes ⏸️' if agent_state['paused'] else 'No'}\n"
        f"*Emergency stop:* {'YES 🚨' if agent_state['emergency_stop'] else 'No'}"
    )
    await update.message.reply_text(message, parse_mode="Markdown")


@operator_only
async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pause autonomous trading."""
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


# ─────────────────────────────────────────────
# Knowledge base & AI commands
# ─────────────────────────────────────────────

@operator_only
async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Query the TCT strategy knowledge base."""
    question = " ".join(context.args) if context.args else ""
    if not question.strip():
        await update.message.reply_text(
            "❓ Usage: /ask <question>\nExample: /ask What is a PO3 schematic?"
        )
        return

    await update.message.reply_text("🔍 Searching TCT knowledge base…")
    try:
        kb = KnowledgeBase()
        results = kb.query_strategy(question, n_results=3)
        if not results:
            await update.message.reply_text("No relevant information found.")
            return

        lines = [f"📚 *Answer to:* _{question}_\n"]
        for i, r in enumerate(results, 1):
            doc = r.get("document", "")[:500]
            source = r.get("metadata", {}).get("source", "unknown")
            lines.append(f"*[{i}] {source}*\n{doc}\n")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as exc:
        logger.error("Error in /ask: %s", exc)
        await update.message.reply_text(f"❌ Error retrieving answer: {exc}")


@operator_only
async def cmd_explain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Have Kaironis explain a TCT concept via OpenRouter."""
    concept = " ".join(context.args) if context.args else ""
    if not concept.strip():
        await update.message.reply_text(
            "❓ Usage: /explain <concept>\nExample: /explain liquidity sweep"
        )
        return

    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if not openrouter_key:
        await update.message.reply_text("❌ OPENROUTER_API_KEY not configured.")
        return

    await update.message.reply_text(f"🤔 Generating explanation for: _{concept}_…", parse_mode="Markdown")
    try:
        # Use asyncio.to_thread to avoid blocking the event loop during HTTP call
        response = await asyncio.to_thread(
            requests.post,
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {openrouter_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "anthropic/claude-3-haiku",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are Kaironis, an AI trading assistant specializing in "
                            "TCT (Time-Cycle Trading). Provide clear, concise explanations "
                            "of TCT concepts. Maximum 300 words."
                        ),
                    },
                    {"role": "user", "content": f"Explain: {concept}"},
                ],
                "max_tokens": 400,
            },
            timeout=30,
        )
        response.raise_for_status()
        answer = response.json()["choices"][0]["message"]["content"]
        await update.message.reply_text(f"💡 *{concept}*\n\n{answer}", parse_mode="Markdown")
    except Exception as exc:
        logger.error("Error in /explain: %s", exc)
        await update.message.reply_text(f"❌ OpenRouter error: {exc}")


# ─────────────────────────────────────────────
# Unknown command handler
# ─────────────────────────────────────────────

@operator_only
async def cmd_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "❓ Unknown command. Use /help for an overview."
    )


# ─────────────────────────────────────────────
# Global error handler
# ─────────────────────────────────────────────

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catches all unexpected errors and logs them. Sends a notification to the operator."""
    logger.error("Unexpected error: %s", context.error, exc_info=context.error)
    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"❌ Unexpected error: {type(context.error).__name__}. It has been logged.",
            )
        except Exception:
            pass


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main() -> None:
    """Start the Telegram bot."""
    if not BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not set in environment variables")

    if not OPERATOR_CHAT_ID:
        raise ValueError("TELEGRAM_OPERATOR_CHAT_ID not set in environment variables")

    logger.info("Kaironis Bot v%s starting...", agent_state['version'])

    app = Application.builder().token(BOT_TOKEN).build()

    # Register commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("emergency", cmd_emergency))
    app.add_handler(CommandHandler("ask", cmd_ask))
    app.add_handler(CommandHandler("explain", cmd_explain))

    # Global error handler
    app.add_error_handler(error_handler)

    logger.info("Bot started. Waiting for messages...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
