"""
Integration tests voor Kaironis Telegram bot commands: /ask en /explain.

Mockt externe dependencies (KnowledgeBase, OpenRouter, requests)
zodat de tests offline draaien en snel zijn.
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import Update, User, Chat, Message
from telegram.ext import ContextTypes


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

OPERATOR_ID = 98661271


def make_update(user_id: int, text: str = "", args: list = None) -> tuple[Update, MagicMock]:
    """
    Maak een nep Telegram Update + Context aan voor gebruik in tests.

    Args:
        user_id: Telegram user ID van de afzender.
        text: Berichttekst.
        args: Command argumenten (context.args).

    Returns:
        Tuple van (update, context) mocks.
    """
    user = MagicMock(spec=User)
    user.id = user_id

    chat = MagicMock(spec=Chat)
    chat.id = user_id

    message = MagicMock(spec=Message)
    message.reply_text = AsyncMock()
    message.text = text

    update = MagicMock(spec=Update)
    update.effective_user = user
    update.effective_chat = chat
    update.message = message

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.args = args or []
    context.bot = AsyncMock()

    return update, context


# ─────────────────────────────────────────────
# /ask tests
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ask_valid_question_returns_results():
    """Test dat /ask met een geldige vraag resultaten teruggeeft uit de KnowledgeBase."""
    from src.orchestration.bot import cmd_ask

    mock_results = [
        {
            "document": "Een PO3 schematic beschrijft de drie fasen van een price move: accumulation, manipulation en distribution.",
            "metadata": {"source": "lectures/po3.md", "category": "lectures"},
            "distance": 0.1,
        }
    ]

    update, context = make_update(OPERATOR_ID, args=["Wat", "is", "PO3?"])

    with patch("src.orchestration.bot.KnowledgeBase") as MockKB:
        instance = MockKB.return_value
        instance.query_strategy.return_value = mock_results

        await cmd_ask(update, context)

    # Verwacht minstens twee berichten: "zoeken…" en het resultaat
    assert update.message.reply_text.call_count >= 2
    last_call = update.message.reply_text.call_args_list[-1]
    assert "PO3" in last_call[0][0] or "po3" in last_call[0][0].lower()


@pytest.mark.asyncio
async def test_ask_empty_question_returns_usage():
    """Test dat /ask zonder argumenten een gebruiksaanwijzing geeft."""
    from src.orchestration.bot import cmd_ask

    update, context = make_update(OPERATOR_ID, args=[])

    await cmd_ask(update, context)

    update.message.reply_text.assert_called_once()
    reply = update.message.reply_text.call_args[0][0]
    assert "/ask" in reply


@pytest.mark.asyncio
async def test_ask_no_results_returns_not_found():
    """Test dat /ask een 'niet gevonden' bericht geeft als KB leeg teruggeeft."""
    from src.orchestration.bot import cmd_ask

    update, context = make_update(OPERATOR_ID, args=["obscure", "concept"])

    with patch("src.orchestration.bot.KnowledgeBase") as MockKB:
        instance = MockKB.return_value
        instance.query_strategy.return_value = []

        await cmd_ask(update, context)

    last_reply = update.message.reply_text.call_args_list[-1][0][0]
    assert "gevonden" in last_reply.lower() or "geen" in last_reply.lower()


@pytest.mark.asyncio
async def test_ask_kb_exception_returns_error():
    """Test dat /ask bij een KB fout een foutbericht stuurt (geen crash)."""
    from src.orchestration.bot import cmd_ask

    update, context = make_update(OPERATOR_ID, args=["supply", "zone"])

    with patch("src.orchestration.bot.KnowledgeBase") as MockKB:
        instance = MockKB.return_value
        instance.query_strategy.side_effect = RuntimeError("ChromaDB onbereikbaar")

        await cmd_ask(update, context)

    last_reply = update.message.reply_text.call_args_list[-1][0][0]
    assert "❌" in last_reply or "Fout" in last_reply or "fout" in last_reply


# ─────────────────────────────────────────────
# /explain tests
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_explain_valid_concept_returns_response():
    """Test dat /explain met een geldig concept een uitleg teruggeeft van OpenRouter."""
    from src.orchestration.bot import cmd_explain

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {"message": {"content": "Een liquidity sweep is wanneer de prijs..."}}
        ]
    }
    mock_response.raise_for_status = MagicMock()

    update, context = make_update(OPERATOR_ID, args=["liquidity", "sweep"])

    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key-123"}):
        with patch("src.orchestration.bot.requests.post", return_value=mock_response):
            await cmd_explain(update, context)

    last_reply = update.message.reply_text.call_args_list[-1][0][0]
    assert "liquidity sweep" in last_reply.lower() or "sweep" in last_reply.lower()


@pytest.mark.asyncio
async def test_explain_missing_api_key_returns_error():
    """Test dat /explain een foutbericht geeft als OPENROUTER_API_KEY niet is ingesteld."""
    from src.orchestration.bot import cmd_explain

    update, context = make_update(OPERATOR_ID, args=["supply", "zone"])

    # Zorg dat de env var NIET aanwezig is
    env = {k: v for k, v in os.environ.items() if k != "OPENROUTER_API_KEY"}
    with patch.dict(os.environ, env, clear=True):
        await cmd_explain(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "OPENROUTER_API_KEY" in reply or "❌" in reply


@pytest.mark.asyncio
async def test_explain_empty_concept_returns_usage():
    """Test dat /explain zonder argumenten een gebruiksaanwijzing geeft."""
    from src.orchestration.bot import cmd_explain

    update, context = make_update(OPERATOR_ID, args=[])

    await cmd_explain(update, context)

    update.message.reply_text.assert_called_once()
    reply = update.message.reply_text.call_args[0][0]
    assert "/explain" in reply


@pytest.mark.asyncio
async def test_explain_openrouter_error_returns_error_message():
    """Test dat /explain bij een OpenRouter fout een foutbericht stuurt (geen crash)."""
    from src.orchestration.bot import cmd_explain

    update, context = make_update(OPERATOR_ID, args=["PO3"])

    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key-123"}):
        with patch("src.orchestration.bot.requests.post", side_effect=RuntimeError("timeout")):
            await cmd_explain(update, context)

    last_reply = update.message.reply_text.call_args_list[-1][0][0]
    assert "❌" in last_reply or "fout" in last_reply.lower()


# ─────────────────────────────────────────────
# operator_only decorator test
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_operator_only_blocks_non_operator():
    """Test dat operator_only decorator niet-operators blokkeert."""
    from src.orchestration.bot import cmd_ask

    NON_OPERATOR_ID = 99999999
    update, context = make_update(NON_OPERATOR_ID, args=["test", "vraag"])

    with patch("src.orchestration.bot.OPERATOR_CHAT_ID", OPERATOR_ID):
        await cmd_ask(update, context)

    update.message.reply_text.assert_called_once()
    reply = update.message.reply_text.call_args[0][0]
    assert "Niet geautoriseerd" in reply or "operator" in reply.lower() or "⛔" in reply


@pytest.mark.asyncio
async def test_operator_only_allows_operator():
    """Test dat operator_only decorator de echte operator doorlaat."""
    from src.orchestration.bot import cmd_ask

    mock_results = [
        {
            "document": "Test document inhoud met voldoende tekst.",
            "metadata": {"source": "test.md", "category": "general"},
            "distance": 0.2,
        }
    ]
    update, context = make_update(OPERATOR_ID, args=["test"])

    with patch("src.orchestration.bot.OPERATOR_CHAT_ID", OPERATOR_ID):
        with patch("src.orchestration.bot.KnowledgeBase") as MockKB:
            instance = MockKB.return_value
            instance.query_strategy.return_value = mock_results

            await cmd_ask(update, context)

    # Operator wordt doorgelaten, dus KnowledgeBase wordt aangeroepen
    MockKB.return_value.query_strategy.assert_called_once()
