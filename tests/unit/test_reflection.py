"""
Unit tests voor src/memory/reflection.py

Alle DB interacties worden gemockt via unittest.mock.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from src.memory.reflection import ReflectionLog, VALID_CATEGORIES, MAX_LIMIT, _row_to_dict


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
    row_id=1,
    category="lesson_learned",
    content="Test content",
    metadata=None,
    created_at=None,
):
    """Maak een nep asyncpg Record."""
    row = MagicMock()
    row.__getitem__ = lambda _, key: {
        "id": row_id,
        "category": category,
        "content": content,
        "metadata": json.dumps(metadata) if metadata is not None else None,
        "created_at": created_at or datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc),
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
        with pytest.raises(ValueError, match="Invalid category"):
            await log.log_observation("invalid_cat", "Some content")

    @pytest.mark.asyncio
    async def test_empty_content_raises(self):
        mock_pool, _ = make_mock_pool()
        log = ReflectionLog(pool=mock_pool)
        with pytest.raises(ValueError, match="Content must not be empty"):
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

    @pytest.mark.asyncio
    async def test_metadata_list_raises_typeerror(self):
        """metadata als list moet een TypeError gooien."""
        mock_pool, _ = make_mock_pool()
        log = ReflectionLog(pool=mock_pool)
        with pytest.raises(TypeError, match="metadata must be a dict or None"):
            await log.log_observation("lesson_learned", "Test", metadata=["a", "b"])

    @pytest.mark.asyncio
    async def test_metadata_string_raises_typeerror(self):
        """metadata als string moet een TypeError gooien."""
        mock_pool, _ = make_mock_pool()
        log = ReflectionLog(pool=mock_pool)
        with pytest.raises(TypeError, match="metadata must be a dict or None"):
            await log.log_observation("lesson_learned", "Test", metadata="niet-een-dict")

    @pytest.mark.asyncio
    async def test_log_observation_propagates_db_error(self):
        """DB-fout in fetchrow moet propageren naar de aanroeper."""
        mock_pool, mock_conn = make_mock_pool()
        mock_conn.fetchrow.side_effect = RuntimeError("db down")
        log = ReflectionLog(pool=mock_pool)
        with pytest.raises(RuntimeError, match="db down"):
            await log.log_observation("lesson_learned", "Test content")

    @pytest.mark.asyncio
    async def test_log_observation_propagates_acquire_error(self):
        """Pool.acquire() fout moet propageren naar de aanroeper."""
        mock_pool, mock_conn = make_mock_pool()
        mock_pool.acquire.side_effect = ConnectionError("pool exhausted")
        log = ReflectionLog(pool=mock_pool)
        with pytest.raises(ConnectionError, match="pool exhausted"):
            await log.log_observation("lesson_learned", "Test content")


# ─────────────────────────────────────────────
# Tests: ReflectionLog.get_recent
# ─────────────────────────────────────────────

class TestGetRecent:
    @pytest.mark.asyncio
    async def test_returns_list_of_dicts(self):
        rows = [
            make_mock_row(row_id=1, category="lesson_learned", content="Les 1"),
            make_mock_row(row_id=2, category="market_observation", content="Obs 2"),
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

        # Met category filter: (sql, category, limit) → 3 positional args
        call_args = mock_conn.fetch.call_args[0]
        assert len(call_args) == 3
        assert isinstance(call_args[0], str)   # SQL string
        assert call_args[1] == "lesson_learned"  # category op positie 1
        assert call_args[2] == 5                 # limit op positie 2

    @pytest.mark.asyncio
    async def test_no_filter_query_has_one_param(self):
        mock_pool, mock_conn = make_mock_pool(rows=[])
        log = ReflectionLog(pool=mock_pool)
        await log.get_recent(limit=7)

        # Zonder category: (sql, limit) → 2 positional args
        call_args = mock_conn.fetch.call_args[0]
        assert len(call_args) == 2
        assert isinstance(call_args[0], str)  # SQL string
        assert call_args[1] == 7              # limit op positie 1

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
    async def test_limit_exceeds_max_raises_valueerror(self):
        mock_pool, _ = make_mock_pool()
        log = ReflectionLog(pool=mock_pool)
        with pytest.raises(ValueError, match=f"limit must be <= {MAX_LIMIT}"):
            await log.get_recent(limit=MAX_LIMIT + 1)

    @pytest.mark.asyncio
    async def test_get_recent_propagates_db_error(self):
        """DB-fout in fetch moet propageren naar de aanroeper."""
        mock_pool, mock_conn = make_mock_pool()
        mock_conn.fetch.side_effect = RuntimeError("db down")
        log = ReflectionLog(pool=mock_pool)
        with pytest.raises(RuntimeError, match="db down"):
            await log.get_recent()

    @pytest.mark.asyncio
    async def test_get_recent_propagates_acquire_error(self):
        """Pool.acquire() fout in get_recent moet propageren."""
        mock_pool, mock_conn = make_mock_pool()
        mock_pool.acquire.side_effect = ConnectionError("pool exhausted")
        log = ReflectionLog(pool=mock_pool)
        with pytest.raises(ConnectionError, match="pool exhausted"):
            await log.get_recent()

    @pytest.mark.asyncio
    async def test_datetime_converted_to_isoformat(self):
        dt = datetime(2026, 3, 15, 9, 30, 0, tzinfo=timezone.utc)
        rows = [make_mock_row(row_id=1, content="test", created_at=dt)]
        mock_pool, _ = make_mock_pool(rows=rows)
        log = ReflectionLog(pool=mock_pool)
        result = await log.get_recent()
        assert result[0]["created_at"] == "2026-03-15T09:30:00+00:00"


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
            make_mock_row(row_id=1, content="PO3 uitleg in lectuur"),
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

        # (sql, pattern, limit) → 3 positional args
        call_args = mock_conn.fetch.call_args[0]
        assert len(call_args) == 3
        assert isinstance(call_args[0], str)         # SQL string
        assert call_args[1] == "%supply zone%"        # pattern op positie 1
        assert call_args[2] == 20                     # default limit op positie 2

    @pytest.mark.asyncio
    async def test_no_db_call_on_empty_query(self):
        mock_pool, mock_conn = make_mock_pool(rows=[])
        log = ReflectionLog(pool=mock_pool)
        await log.search("")
        mock_conn.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_propagates_db_error(self):
        """DB-fout in fetch tijdens search moet propageren naar de aanroeper."""
        mock_pool, mock_conn = make_mock_pool()
        mock_conn.fetch.side_effect = RuntimeError("db down")
        log = ReflectionLog(pool=mock_pool)
        with pytest.raises(RuntimeError, match="db down"):
            await log.search("PO3")

    @pytest.mark.asyncio
    async def test_search_propagates_acquire_error(self):
        """Pool.acquire() fout in search moet propageren."""
        mock_pool, mock_conn = make_mock_pool()
        mock_pool.acquire.side_effect = ConnectionError("pool exhausted")
        log = ReflectionLog(pool=mock_pool)
        with pytest.raises(ConnectionError, match="pool exhausted"):
            await log.search("PO3")

    @pytest.mark.asyncio
    async def test_search_escapes_percent_and_underscore(self):
        """Wildcards % en _ in de query moeten letterlijk behandeld worden via ESCAPE '\\'."""
        mock_pool, mock_conn = make_mock_pool(rows=[])
        log = ReflectionLog(pool=mock_pool)
        await log.search("PO3_50%")

        args = mock_conn.fetch.call_args[0]
        # SQL moet expliciet backslash als escape gebruiken
        assert "ESCAPE '\\'" in args[0]
        # Pattern arg: % en _ zijn geëscaped
        assert args[1] == r"%PO3\_50\%%"


# ─────────────────────────────────────────────
# Tests: ReflectionLog.initialize
# ─────────────────────────────────────────────

class TestInitialize:
    @pytest.mark.asyncio
    async def test_execute_called_for_base_statements(self):
        """Basisstructuur wordt aangemaakt; trigram indexes worden ook geprobeerd."""
        from src.memory.reflection import CREATE_TABLE_STATEMENTS, TRGM_INDEX_STATEMENTS
        mock_pool, mock_conn = make_mock_pool()
        # Simuleer transactie context manager
        mock_transaction = MagicMock()
        mock_transaction.__aenter__ = AsyncMock(return_value=None)
        mock_transaction.__aexit__ = AsyncMock(return_value=False)
        mock_conn.transaction = MagicMock(return_value=mock_transaction)
        log = ReflectionLog(pool=mock_pool)
        await log.initialize()
        # Alle base statements + alle trgm statements worden geprobeerd
        expected_count = len(CREATE_TABLE_STATEMENTS) + len(TRGM_INDEX_STATEMENTS)
        assert mock_conn.execute.call_count == expected_count

    @pytest.mark.asyncio
    async def test_initialize_skips_trgm_on_extension_missing(self):
        """Als pg_trgm niet beschikbaar is, wordt de trigram index overgeslagen zonder crash."""
        import asyncpg
        from src.memory.reflection import CREATE_TABLE_STATEMENTS
        mock_pool, mock_conn = make_mock_pool()
        mock_transaction = MagicMock()
        mock_transaction.__aenter__ = AsyncMock(return_value=None)
        mock_transaction.__aexit__ = AsyncMock(return_value=False)
        mock_conn.transaction = MagicMock(return_value=mock_transaction)

        # Eerste N calls (basisstructuur) slagen; daarna UndefinedObjectError voor trgm
        base_calls = len(CREATE_TABLE_STATEMENTS)
        call_count = 0

        async def execute_side_effect(stmt):
            nonlocal call_count
            call_count += 1
            if call_count > base_calls:
                raise asyncpg.UndefinedObjectError("type gin_trgm_ops does not exist")

        mock_conn.execute = AsyncMock(side_effect=execute_side_effect)
        log = ReflectionLog(pool=mock_pool)
        # Mag niet crashen
        await log.initialize()

    @pytest.mark.asyncio
    async def test_initialize_propagates_unexpected_db_error(self):
        """Een onverwachte DB-fout (niet UndefinedObjectError) moet propageren."""
        mock_pool, mock_conn = make_mock_pool()
        mock_transaction = MagicMock()
        mock_transaction.__aenter__ = AsyncMock(return_value=None)
        mock_transaction.__aexit__ = AsyncMock(return_value=False)
        mock_conn.transaction = MagicMock(return_value=mock_transaction)
        mock_conn.execute.side_effect = RuntimeError("disk full")
        log = ReflectionLog(pool=mock_pool)
        with pytest.raises(RuntimeError, match="disk full"):
            await log.initialize()

    @pytest.mark.asyncio
    async def test_initialize_propagates_acquire_error(self):
        """Pool.acquire() fout in initialize moet propageren."""
        mock_pool, mock_conn = make_mock_pool()
        mock_pool.acquire.side_effect = ConnectionError("pool exhausted")
        log = ReflectionLog(pool=mock_pool)
        with pytest.raises(ConnectionError, match="pool exhausted"):
            await log.initialize()


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
        with pytest.raises(ValueError, match="No DSN provided"):
            await log.get_recent()


# ─────────────────────────────────────────────
# Tests: _row_to_dict helper
# ─────────────────────────────────────────────

class TestRowToDict:
    def test_basic_conversion(self):
        row = make_mock_row(row_id=1, category="trade_setup", content="Test", metadata={"k": "v"})
        result = _row_to_dict(row)
        assert result["id"] == 1
        assert result["category"] == "trade_setup"
        assert result["content"] == "Test"
        assert result["metadata"] == {"k": "v"}

    def test_none_metadata_stays_none(self):
        row = make_mock_row(row_id=1, metadata=None)
        result = _row_to_dict(row)
        assert result["metadata"] is None

    def test_datetime_converted(self):
        dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        row = make_mock_row(created_at=dt)
        result = _row_to_dict(row)
        assert result["created_at"] == "2026-01-01T00:00:00+00:00"

    def test_string_metadata_parsed(self):
        row = make_mock_row(metadata={"key": "val"})
        result = _row_to_dict(row)
        assert result["metadata"]["key"] == "val"

    def test_invalid_json_metadata_returns_empty_dict(self):
        row = MagicMock()
        row.__getitem__ = lambda _, key: {
            "id": 1,
            "category": "lesson_learned",
            "content": "test",
            "metadata": "not-valid-json{{{",
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }[key]
        result = _row_to_dict(row)
        assert result["metadata"] == {}

    def test_empty_dict_metadata_stays_empty_dict(self):
        """Lege dict metadata mag niet naar None worden geconverteerd."""
        row = make_mock_row(row_id=1, metadata={})
        result = _row_to_dict(row)
        assert result["metadata"] == {}
