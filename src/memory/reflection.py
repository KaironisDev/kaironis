"""
Reflection & Learning System voor Kaironis.

Slaat trade observaties, learnings en strategie-notities op in PostgreSQL.
Full-text search via PostgreSQL ts_vector.

Example::

    log = ReflectionLog(dsn="postgresql://user:pass@localhost/kaironis")
    await log.log_observation("lesson_learned", "Nooit traden in eerste 5 min na NY open")
    recent = await log.get_recent(limit=5)
    hits = await log.search("NY open")
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import asyncpg

logger = logging.getLogger(__name__)

# Geldige categorieën
VALID_CATEGORIES = frozenset([
    "trade_setup",
    "market_observation",
    "lesson_learned",
    "strategy_note",
])

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS reflections (
    id SERIAL PRIMARY KEY,
    category VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS reflections_category_idx ON reflections(category);
CREATE INDEX IF NOT EXISTS reflections_created_idx ON reflections(created_at DESC);
"""


class ReflectionLog:
    """
    Slaat trade observaties en learnings op in PostgreSQL.

    Args:
        dsn: PostgreSQL connection string.
             Voorbeeld: "postgresql://kaironis:secret@localhost/kaironis"
        pool: Bestaand asyncpg connection pool (optioneel; overschrijft dsn).
    """

    def __init__(
        self,
        dsn: Optional[str] = None,
        pool: Optional[asyncpg.Pool] = None,
    ) -> None:
        self._dsn = dsn
        self._pool: Optional[asyncpg.Pool] = pool
        # Track of we de pool zelf aangemaakt hebben (True) of ge-injecteerd kregen (False).
        # close() sluit alleen self-owned pools om externe pools niet te vernietigen.
        self._owns_pool: bool = pool is None
        self._pool_init_lock = asyncio.Lock()

    async def _get_pool(self) -> asyncpg.Pool:
        """Lazy initialisatie van de connection pool (race-condition safe)."""
        if self._pool is None:
            async with self._pool_init_lock:
                if self._pool is None:
                    if not self._dsn:
                        raise ValueError("Geen DSN opgegeven voor ReflectionLog")
                    self._pool = await asyncpg.create_pool(self._dsn)
        return self._pool

    async def initialize(self) -> None:
        """Maak de tabel en indices aan als ze nog niet bestaan."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            # Voer statements uit CREATE_TABLE_SQL afzonderlijk uit
            for statement in CREATE_TABLE_SQL.strip().split(";"):
                stmt = statement.strip()
                if stmt:
                    await conn.execute(stmt)
        logger.info("ReflectionLog tabel geïnitialiseerd")

    async def close(self) -> None:
        """Sluit de connection pool — alleen als we hem zelf aangemaakt hebben."""
        if self._pool is not None and self._owns_pool:
            await self._pool.close()
            self._pool = None

    # ─────────────────────────────────────────────
    # Schrijven
    # ─────────────────────────────────────────────

    async def log_observation(
        self,
        category: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Sla een observatie of learning op.

        Args:
            category: Eén van: trade_setup, market_observation,
                      lesson_learned, strategy_note.
            content: De tekst van de observatie.
            metadata: Optionele extra data als dict (wordt opgeslagen als JSONB).

        Returns:
            Het nieuwe record ID.

        Raises:
            ValueError: Als category ongeldig is of content leeg.
        """
        if category not in VALID_CATEGORIES:
            raise ValueError(
                f"Ongeldige categorie '{category}'. "
                f"Gebruik een van: {', '.join(sorted(VALID_CATEGORIES))}"
            )

        content = content.strip()
        if not content:
            raise ValueError("Content mag niet leeg zijn")

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO reflections (category, content, metadata)
                VALUES ($1, $2, $3)
                RETURNING id
                """,
                category,
                content,
                json.dumps(metadata) if metadata else None,
            )

        record_id: int = row["id"]
        logger.info(
            "Observatie opgeslagen: id=%d category=%s chars=%d",
            record_id, category, len(content)
        )
        return record_id

    # ─────────────────────────────────────────────
    # Lezen
    # ─────────────────────────────────────────────

    async def get_recent(
        self,
        limit: int = 10,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Haal de meest recente observaties op.

        Args:
            limit: Maximum aantal records (default: 10). Must be >= 1.
            category: Filter op categorie (optioneel).

        Returns:
            Lijst van dicts met id, category, content, metadata, created_at.

        Raises:
            ValueError: As limit < 1.
        """
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise TypeError(
                f"limit must be an integer >= 1, got {type(limit).__name__!r}"
            )
        if limit < 1:
            raise ValueError(f"limit must be >= 1, got {limit}")

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if category:
                rows = await conn.fetch(
                    """
                    SELECT id, category, content, metadata, created_at
                    FROM reflections
                    WHERE category = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                    """,
                    category,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, category, content, metadata, created_at
                    FROM reflections
                    ORDER BY created_at DESC
                    LIMIT $1
                    """,
                    limit,
                )

        return [_row_to_dict(row) for row in rows]

    async def search(self, query: str) -> List[Dict[str, Any]]:
        """
        Full-text zoeken in PostgreSQL via ILIKE (portable, geen tsvector setup nodig).

        Args:
            query: Zoekterm(en).

        Returns:
            Lijst van matching dicts, gesorteerd op datum (meest recent eerst).
        """
        query = query.strip()
        if not query:
            return []

        # Escape LIKE wildcards in user input to prevent injection
        safe_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{safe_query}%"
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, category, content, metadata, created_at
                FROM reflections
                WHERE content ILIKE $1 ESCAPE '\\' OR category ILIKE $1 ESCAPE '\\'
                ORDER BY created_at DESC
                LIMIT 20
                """,
                pattern,
            )

        logger.debug("Search '%s': %d resultaten", query, len(rows))
        return [_row_to_dict(row) for row in rows]


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _row_to_dict(row: asyncpg.Record) -> Dict[str, Any]:
    """Converteer een asyncpg Record naar een plain dict."""
    metadata = row["metadata"]
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except (json.JSONDecodeError, TypeError):
            metadata = {}

    created_at = row["created_at"]
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()

    return {
        "id": row["id"],
        "category": row["category"],
        "content": row["content"],
        "metadata": metadata,
        "created_at": created_at,
    }
