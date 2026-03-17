"""
Reflection & Learning System voor Kaironis.

Slaat trade observaties, learnings en strategie-notities op in PostgreSQL.
De search() methode gebruikt case-insensitive ILIKE-matching (substring zoeken).

Example::

    log = ReflectionLog(dsn="postgresql://user:pass@localhost/kaironis")
    await log.log_observation("lesson_learned", "Nooit traden in eerste 5 min na NY open")
    recent = await log.get_recent(limit=5)
    hits = await log.search("NY open")

Note:
    De GIN trigram indexes (reflections_content_trgm_idx, reflections_category_trgm_idx)
    vereisen de pg_trgm PostgreSQL-extensie. Deze extensie moet door een database-administrator
    (superuser) vooraf aangemaakt worden::

        docker exec kaironis-postgres psql -U postgres -d kaironis -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"

    Als de extensie niet beschikbaar is, worden de trigram indexes overgeslagen.
    ILIKE-zoekopdrachten blijven functioneel, maar zonder de performance-optimalisatie van GIN indexes.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Optional

import asyncpg

logger = logging.getLogger(__name__)

# Geldige categorieën
VALID_CATEGORIES = frozenset([
    "trade_setup",
    "market_observation",
    "lesson_learned",
    "strategy_note",
])

# DDL statements als expliciete tuple — vermijdt fragiel split(";") op embedded puntkomma's
# Basisstructuur (geen superuser vereist)
CREATE_TABLE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS reflections (
        id SERIAL PRIMARY KEY,
        category VARCHAR(50) NOT NULL,
        content TEXT NOT NULL,
        metadata JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS reflections_category_idx ON reflections(category)",
    "CREATE INDEX IF NOT EXISTS reflections_created_idx ON reflections(created_at DESC)",
)

# GIN trigram indexes — vereisen pg_trgm extensie (superuser-rechten).
# Worden alleen aangemaakt als de extensie beschikbaar is.
TRGM_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS reflections_content_trgm_idx ON reflections USING GIN (content gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS reflections_category_trgm_idx ON reflections USING GIN (category gin_trgm_ops)",
)

# Maximum aantal records dat get_recent() mag teruggeven
MAX_LIMIT = 1000


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
        """
        Maak de tabel en indices aan als ze nog niet bestaan.

        Basis DDL (tabel + standaard indexes) wordt in één transactie uitgevoerd.
        GIN trigram indexes worden daarna geprobeerd; als pg_trgm niet beschikbaar
        is, wordt een waarschuwing gelogd en de rest van de startup gaat door.

        Tip: pre-create pg_trgm in productie::

            docker exec kaironis-postgres psql -U postgres -d kaironis \\
                -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
        """
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            # Basisstructuur atomisch in één transactie
            async with conn.transaction():
                for statement in CREATE_TABLE_STATEMENTS:
                    stmt = statement.strip()
                    if stmt:
                        await conn.execute(stmt)

            # Trigram indexes optioneel — vereisen pg_trgm extensie
            for statement in TRGM_INDEX_STATEMENTS:
                stmt = statement.strip()
                if stmt:
                    try:
                        await conn.execute(stmt)
                    except asyncpg.UndefinedObjectError:
                        logger.warning(
                            "pg_trgm extensie niet beschikbaar — trigram index overgeslagen. "
                            "Pre-create de extensie voor betere ILIKE performance: "
                            "docker exec kaironis-postgres psql -U postgres -d kaironis "
                            "-c \"CREATE EXTENSION IF NOT EXISTS pg_trgm;\""
                        )
                        break  # Beide indexes vereisen pg_trgm; één warning is genoeg

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
        metadata: Optional[dict[str, Any]] = None,
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
        if not isinstance(category, str):
            raise TypeError(
                f"category must be a string, got {type(category).__name__!r}"
            )
        if not isinstance(content, str):
            raise TypeError(
                f"content must be a string, got {type(content).__name__!r}"
            )
        if metadata is not None and not isinstance(metadata, dict):
            raise TypeError(
                f"metadata must be a dict or None, got {type(metadata).__name__!r}"
            )
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
                json.dumps(metadata) if metadata is not None else None,
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
    ) -> list[dict[str, Any]]:
        """
        Haal de meest recente observaties op.

        Args:
            limit: Maximum aantal records (default: 10). Must be >= 1 and <= MAX_LIMIT.
            category: Filter op categorie (optioneel). Moet een van VALID_CATEGORIES zijn.

        Returns:
            Lijst van dicts met id, category, content, metadata, created_at.

        Raises:
            TypeError: Als limit geen integer is (of een bool).
            ValueError: Als limit buiten het bereik [1, MAX_LIMIT] valt.
            TypeError: Als category geen string is.
            ValueError: Als category niet in VALID_CATEGORIES zit.
        """
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise TypeError(
                f"limit must be an integer >= 1, got {type(limit).__name__}"
            )
        if limit < 1:
            raise ValueError(f"limit must be >= 1, got {limit}")
        if limit > MAX_LIMIT:
            raise ValueError(f"limit must be <= {MAX_LIMIT}, got {limit}")

        if category is not None:
            if not isinstance(category, str):
                raise TypeError(
                    f"category must be a string, got {type(category).__name__!r}"
                )
            if category not in VALID_CATEGORIES:
                raise ValueError(
                    f"Ongeldige categorie '{category}'. "
                    f"Gebruik een van: {', '.join(sorted(VALID_CATEGORIES))}"
                )

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

    async def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """
        Full-text zoeken in PostgreSQL via ILIKE (portable, geen tsvector setup nodig).

        Args:
            query: Zoekterm(en).
            limit: Maximum aantal resultaten (default: 20). Must be >= 1 and <= MAX_LIMIT.

        Returns:
            Lijst van matching dicts, gesorteerd op datum (meest recent eerst).

        Raises:
            TypeError: Als query geen string is of limit geen integer.
            ValueError: Als limit buiten het bereik [1, MAX_LIMIT] valt.
        """
        if not isinstance(query, str):
            raise TypeError(f"query must be a string, got {type(query).__name__!r}")
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise TypeError(
                f"limit must be an integer >= 1, got {type(limit).__name__}"
            )
        if limit < 1:
            raise ValueError(f"limit must be >= 1, got {limit}")
        if limit > MAX_LIMIT:
            raise ValueError(f"limit must be <= {MAX_LIMIT}, got {limit}")

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
                LIMIT $2
                """,
                pattern,
                limit,
            )

        # Log geanonimiseerde query (eerste 4 tekens + "...") om reflection-data niet te lekken
        masked_query = query[:4] + "..." if len(query) > 4 else "***"
        logger.debug("Search '%s' (len=%d): %d resultaten", masked_query, len(query), len(rows))
        return [_row_to_dict(row) for row in rows]


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
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
