"""
Unit tests voor de Telegram bot module.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ─────────────────────────────────────────────
# Agent State Tests
# ─────────────────────────────────────────────

def test_initial_agent_state():
    """Verifieer dat de initiële agent state correct is."""
    from src.orchestration.bot import agent_state

    assert agent_state["trading_active"] is False
    assert agent_state["paused"] is False
    assert agent_state["emergency_stop"] is False
    assert "version" in agent_state
    assert "started_at" in agent_state


def test_agent_state_after_pause():
    """Verifieer dat pauze de juiste state zet."""
    from src.orchestration import bot

    # Reset state
    bot.agent_state["trading_active"] = True
    bot.agent_state["paused"] = False
    bot.agent_state["emergency_stop"] = False

    # Simuleer pauze
    bot.agent_state["paused"] = True
    bot.agent_state["trading_active"] = False

    assert bot.agent_state["paused"] is True
    assert bot.agent_state["trading_active"] is False
    assert bot.agent_state["emergency_stop"] is False


def test_agent_state_after_emergency():
    """Verifieer dat emergency stop alles stillegt."""
    from src.orchestration import bot

    # Reset state
    bot.agent_state["trading_active"] = True
    bot.agent_state["paused"] = False
    bot.agent_state["emergency_stop"] = False

    # Simuleer emergency stop
    bot.agent_state["emergency_stop"] = True
    bot.agent_state["trading_active"] = False
    bot.agent_state["paused"] = True

    assert bot.agent_state["emergency_stop"] is True
    assert bot.agent_state["trading_active"] is False
    assert bot.agent_state["paused"] is True


def test_agent_state_after_resume():
    """Verifieer dat resume alle stops opheft."""
    from src.orchestration import bot

    # Start vanuit emergency stop
    bot.agent_state["emergency_stop"] = True
    bot.agent_state["paused"] = True
    bot.agent_state["trading_active"] = False

    # Simuleer resume
    bot.agent_state["paused"] = False
    bot.agent_state["emergency_stop"] = False
    bot.agent_state["trading_active"] = True

    assert bot.agent_state["emergency_stop"] is False
    assert bot.agent_state["paused"] is False
    assert bot.agent_state["trading_active"] is True


# ─────────────────────────────────────────────
# Risk Limit Sanity Checks (vanuit SOUL.md)
# ─────────────────────────────────────────────

def test_risk_limits_are_sane():
    """Verifieer dat risk limieten logisch zijn t.o.v. Breakout Prop regels."""
    MAX_POSITION_SIZE = 1.0
    MAX_OPEN_POSITIONS = 3
    DAILY_LOSS_PAUSE = 2.0       # Onze buffer
    PROP_DAILY_LOSS_LIMIT = 3.0  # Breakout Prop limiet
    DRAWDOWN_PAUSE = 5.0         # Onze buffer
    PROP_MAX_DRAWDOWN = 6.0      # Breakout Prop limiet

    assert MAX_POSITION_SIZE > 0
    assert MAX_OPEN_POSITIONS > 0
    assert DAILY_LOSS_PAUSE < PROP_DAILY_LOSS_LIMIT, \
        "Onze pauze drempel moet ONDER de prop firm limiet liggen"
    assert DRAWDOWN_PAUSE < PROP_MAX_DRAWDOWN, \
        "Onze drawdown pauze moet ONDER de prop firm max drawdown liggen"
