"""
Unit tests voor src/memory/reflection.py

Alle DB interacties worden gemockt via unittest.mock.
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from src.memory.reflection import ReflectionLog, VALID_CATEGORIES, _row_to_dict


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

def make_mock_pool(rows=None, fetchrow_result=None):
    """Maak een nep asyncpg pool met een context-manager-achtige acquire()."""
    mock_conn = AsyncMock()

    # fetchrow retourneert een enkele rij (dict-achtig)
    if fetchrow_result is not None:
        mock_conn.fetchrow = AsyncMock(return_value=fetchrow_result)
    else:
        mock_conn.fetchrow = AsyncMock(return_value={"id": 42})

    # fetch retourneert een lijst van rijen
    mock_conn.fetch = AsyncMock(return_value=rows or [])
    mock_conn.execute = AsyncMock(return_value=None)

    # Pool.acquire() is een async context manager
    mock_acquire = MagicMock()
    mock_acquire.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_acquire.__aexit__ = AsyncMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=mock_acquire)
    mock_pool.close = AsyncMock()

    return mock_pool, mock_conn


def make_mock_row(
    id=1,
    category="lesson_learned",
    content="Test content",
    metadata=None,
    created_at=None,
):
    """Maak een nep asyncpg Record."""
    row = MagicMock()
    row.__getitem__ = lambda self, key: {
        "id": id,
        "category": category,
        "content": content,
        "metadata": json.dumps(metadata) if metadata else None,
        "created_at": created_at or datetime(2026, 3, 15, 12, 0, 0),
    }[key]
    return row


# ─────────────────────────────────────────────
# Tests: ReflectionLog.log_observation
# ─────────────────────────────────────────────

class TestLogObservation:
    @pytest.mark.asyncio
    async def test_valid_observation_returns_id(self):
        mock_pool, mock_conn = make_mock_pool(
            fetchrow_result={"id": 7}
        )
        log = ReflectionLog(pool=mock_pool)
        result = await log.log_observation("lesson_learned", "Nooit traden in NY open eerste 5 min")
        assert result == 7

    @pytest.mark.asyncio
    async def test_all_valid_categories(self):
        for category in VALID_CATEGORIES:
            mock_pool, _ = make_mock_pool(fetchrow_result={"id": 1})
            log = ReflectionLog(pool=mock_pool)
            result = await log.log_observation(category, "Test content")
            assert result == 1

    @pytest.mark.asyncio
    async def test_invalid_category_raises(self):
        mock_pool, _ = make_mock_pool()
        log = ReflectionLog(pool=mock_pool)
        with pytest.raises(ValueError, match="Ongeldige categorie"):
            await log.log_observation("invalid_cat", "Some content")

    @pytest.mark.asyncio
    async def test_empty_content_raises(self):
        mock_pool, _ = make_mock_pool()
        log = ReflectionLog(pool=mock_pool)
        with pytest.raises(ValueError, match="Content mag niet leeg zijn"):
            await log.log_observation("lesson_learned", "   ")

    @pytest.mark.asyncio
    async def test_metadata_is_serialized(self):
        mock_pool, mock_conn = make_mock_pool(fetchrow_result={"id": 3})
        log = ReflectionLog(pool=mock_pool)
        meta = {"trade_id": "ABC123", "pair": "EURUSD"}
        await log.log_observation("trade_setup", "Long setup", metadata=meta)

        # Controleer dat fetchrow werd aangeroepen met de juiste args
        call_args = mock_conn.fetchrow.call_args
        # 4e positional arg is de metadata (als json string)
        args = call_args[0]
        assert json.loads(args[3]) == meta

    @pytest.mark.asyncio
    async def test_content_is_stripped(self):
        mock_pool, mock_conn = make_mock_pool(fetchrow_result={"id": 5})
        log = ReflectionLog(pool=mock_pool)
        await log.log_observation("strategy_note", "  content met spaties  ")
        call_args = mock_conn.fetchrow.call_args[0]
        assert call_args[2] == "content met spaties"

    @pytest.mark.asyncio
    async def test_no_metadata_passes_none(self):
        mock_pool, mock_conn = make_mock_pool(fetchrow_result={"id": 1})
        log = ReflectionLog(pool=mock_pool)
        await log.log_observation("market_observation", "DXY bearish")
        call_args = mock_conn.fetchrow.call_args[0]
        assert call_args[3] is None


# ─────────────────────────────────────────────
# Tests: ReflectionLog.get_recent
# ─────────────────────────────────────────────

class TestGetRecent:
    @pytest.mark.asyncio
    async def test_returns_list_of_dicts(self):
        rows = [
            make_mock_row(id=1, category="lesson_learned", content="Les 1"),
            make_mock_row(id=2, category="market_observation", content="Obs 2"),
        ]
        mock_pool, _ = make_mock_pool(rows=rows)
        log = ReflectionLog(pool=mock_pool)
        result = await log.get_recent(limit=10)
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[0]["content"] == "Les 1"

    @pytest.mark.asyncio
    async def test_empty_result(self):
        mock_pool, _ = make_mock_pool(rows=[])
        log = ReflectionLog(pool=mock_pool)
        result = await log.get_recent()
        assert result == []

    @pytest.mark.asyncio
    async def test_category_filter_uses_different_query(self):
        mock_pool, mock_conn = make_mock_pool(rows=[])
        log = ReflectionLog(pool=mock_pool)
        await log.get_recent(limit=5, category="lesson_learned")

        # Met category filter wordt fetch aangeroepen met 2 params
        call_args = mock_conn.fetch.call_args[0]
        # Eerste arg is de SQL, tweede is de category
        assert "lesson_learned" in call_args

    @pytest.mark.asyncio
    async def test_no_filter_query_has_one_param(self):
        mock_pool, mock_conn = make_mock_pool(rows=[])
        log = ReflectionLog(pool=mock_pool)
        await log.get_recent(limit=7)

        call_args = mock_conn.fetch.call_args[0]
        # Geen category, dus alleen de limit parameter
        assert 7 in call_args

    @pytest.mark.asyncio
    async def test_invalid_limit_type_raises_typeerror(self):
        mock_pool, _ = make_mock_pool()
        log = ReflectionLog(pool=mock_pool)
        with pytest.raises(TypeError, match="limit must be an integer"):
            await log.get_recent(limit=1.5)

    @pytest.mark.asyncio
    async def test_bool_limit_raises_typeerror(self):
        """bool is a subclass of int, so True/False must be explicitly rejected."""
        mock_pool, _ = make_mock_pool()
        log = ReflectionLog(pool=mock_pool)
        with pytest.raises(TypeError, match="limit must be an integer"):
            await log.get_recent(limit=True)

    @pytest.mark.asyncio
    async def test_negative_limit_raises_valueerror(self):
        mock_pool, _ = make_mock_pool()
        log = ReflectionLog(pool=mock_pool)
        with pytest.raises(ValueError, match="limit must be >= 1"):
            await log.get_recent(limit=0)

    @pytest.mark.asyncio
    async def test_datetime_converted_to_isoformat(self):
        dt = datetime(2026, 3, 15, 9, 30, 0)
        rows = [make_mock_row(id=1, content="test", created_at=dt)]
        mock_pool, _ = make_mock_pool(rows=rows)
        log = ReflectionLog(pool=mock_pool)
        result = await log.get_recent()
        assert result[0]["created_at"] == "2026-03-15T09:30:00"


# ─────────────────────────────────────────────
# Tests: ReflectionLog.search
# ─────────────────────────────────────────────

class TestSearch:
    @pytest.mark.asyncio
    async def test_empty_query_returns_empty(self):
        mock_pool, _ = make_mock_pool()
        log = ReflectionLog(pool=mock_pool)
        result = await log.search("")
        assert result == []

    @pytest.mark.asyncio
    async def test_whitespace_query_returns_empty(self):
        mock_pool, _ = make_mock_pool()
        log = ReflectionLog(pool=mock_pool)
        result = await log.search("   ")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_matching_rows(self):
        rows = [
            make_mock_row(id=1, content="PO3 uitleg in lectuur"),
        ]
        mock_pool, _ = make_mock_pool(rows=rows)
        log = ReflectionLog(pool=mock_pool)
        result = await log.search("PO3")
        assert len(result) == 1
        assert "PO3" in result[0]["content"]

    @pytest.mark.asyncio
    async def test_search_passes_ilike_pattern(self):
        mock_pool, mock_conn = make_mock_pool(rows=[])
        log = ReflectionLog(pool=mock_pool)
        await log.search("supply zone")

        call_args = mock_conn.fetch.call_args[0]
        # Pattern moet %supply zone% zijn
        assert "%supply zone%" in call_args

    @pytest.mark.asyncio
    async def test_no_db_call_on_empty_query(self):
        mock_pool, mock_conn = make_mock_pool(rows=[])
        log = ReflectionLog(pool=mock_pool)
        await log.search("")
        mock_conn.fetch.assert_not_called()


# ─────────────────────────────────────────────
# Tests: ReflectionLog.initialize
# ─────────────────────────────────────────────

class TestInitialize:
    @pytest.mark.asyncio
    async def test_execute_called_for_all_statements(self):
        from src.memory.reflection import CREATE_TABLE_STATEMENTS
        mock_pool, mock_conn = make_mock_pool()
        log = ReflectionLog(pool=mock_pool)
        await log.initialize()
        # One execute() call per statement in CREATE_TABLE_STATEMENTS
        assert mock_conn.execute.call_count == len(CREATE_TABLE_STATEMENTS)


# ─────────────────────────────────────────────
# Tests: ReflectionLog lifecycle
# ─────────────────────────────────────────────

class TestLifecycle:
    @pytest.mark.asyncio
    async def test_close_does_not_close_injected_pool(self):
        """An injected pool is externally owned; close() must leave it intact."""
        mock_pool, _ = make_mock_pool()
        log = ReflectionLog(pool=mock_pool)
        assert log._owns_pool is False, "Injected pool must not be owned"
        await log.close()
        mock_pool.close.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_close_closes_self_created_pool(self):
        """A pool created by ReflectionLog itself must be closed on close()."""
        mock_pool, _ = make_mock_pool()
        log = ReflectionLog(dsn="postgresql://localhost/kaironis")
        log._pool = mock_pool  # inject to simulate a created pool
        log._owns_pool = True
        await log.close()
        mock_pool.close.assert_awaited_once()
        assert log._pool is None

    @pytest.mark.asyncio
    async def test_no_dsn_and_no_pool_raises_on_query(self):
        log = ReflectionLog()  # geen dsn, geen pool
        with pytest.raises(ValueError, match="Geen DSN opgegeven"):
            await log.get_recent()


# ─────────────────────────────────────────────
# Tests: _row_to_dict helper
# ─────────────────────────────────────────────

class TestRowToDict:
    def test_basic_conversion(self):
        row = make_mock_row(id=1, category="trade_setup", content="Test", metadata={"k": "v"})
        result = _row_to_dict(row)
        assert result["id"] == 1
        assert result["category"] == "trade_setup"
        assert result["content"] == "Test"
        assert result["metadata"] == {"k": "v"}

    def test_none_metadata_stays_none(self):
        row = make_mock_row(id=1, metadata=None)
        result = _row_to_dict(row)
        assert result["metadata"] is None

    def test_datetime_converted(self):
        dt = datetime(2026, 1, 1, 0, 0, 0)
        row = make_mock_row(created_at=dt)
        result = _row_to_dict(row)
        assert result["created_at"] == "2026-01-01T00:00:00"

    def test_string_metadata_parsed(self):
        row = make_mock_row(metadata={"key": "val"})
        result = _row_to_dict(row)
        assert result["metadata"]["key"] == "val"

    def test_invalid_json_metadata_returns_empty_dict(self):
        row = MagicMock()
        row.__getitem__ = lambda self, key: {
            "id": 1,
            "category": "lesson_learned",
            "content": "test",
            "metadata": "not-valid-json{{{",
            "created_at": datetime(2026, 1, 1),
        }[key]
        result = _row_to_dict(row)
        assert result["metadata"] == {}
