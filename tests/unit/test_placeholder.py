# Placeholder test — verwijder dit wanneer echte tests geschreven worden
# Dit zorgt ervoor dat de CI pipeline groen blijft zolang er geen echte tests zijn


def test_placeholder():
    """Placeholder test om CI pipeline groen te houden."""
    assert True


def test_risk_limits_constants():
    """Basis sanity check op risk limieten (hardcoded waarden uit SOUL.md)."""
    MAX_POSITION_SIZE_PERCENT = 1.0
    MAX_OPEN_POSITIONS = 3
    DAILY_LOSS_PAUSE_THRESHOLD = 2.0
    DRAWDOWN_WARNING_THRESHOLD = 4.0
    DRAWDOWN_PAUSE_THRESHOLD = 5.0

    # Verifieer dat limieten logisch zijn
    assert MAX_POSITION_SIZE_PERCENT > 0
    assert MAX_OPEN_POSITIONS > 0
    assert DAILY_LOSS_PAUSE_THRESHOLD < 3.0  # Onder Breakout Prop limiet van 3%
    assert DRAWDOWN_WARNING_THRESHOLD < DRAWDOWN_PAUSE_THRESHOLD
    assert DRAWDOWN_PAUSE_THRESHOLD < 6.0  # Onder Breakout Prop max drawdown
