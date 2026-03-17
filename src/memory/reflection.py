"""
Reflection & Learning System for Kaironis.

Stores trade observations, learnings and strategy notes in PostgreSQL.
Full-text search via PostgreSQL ILIKE with wildcard injection protection.

Example::

    log = ReflectionLog(dsn="postgresql://user:pass@localhost/kaironis")
    await log.log_observation("lesson_learned", "Never trade in the first 5 min after NY open")
    recent = await log.get_recent(limit=5)
    hits = await log.search("NY open")

Note:
    The GIN trigram indexes (reflections_content_trgm_idx, reflections_category_trgm_idx)
    require the pg_trgm PostgreSQL extension. This extension must be created by a database
    administrator (superuser) in advance::

        docker exec kaironis-postgres psql -U postgres -d kaironis -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"

    If the extension is not available, the trigram indexes are skipped.
    ILIKE searches remain functional, but without the performance optimisation of GIN indexes.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Optional

import asyncpg

logger = logging.getLogger(__name__)

# Valid categories
VALID_CATEGORIES = frozenset([
    "trade_setup",
    "market_observation",
    "lesson_learned",
    "strategy_note",
])

# DDL statements as explicit tuple — avoids fragile split(";") on embedded semicolons
# Base structure (no superuser required)
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

# GIN trigram indexes — require pg_trgm extension (superuser rights).
# Only created if the extension is available.
TRGM_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS reflections_content_trgm_idx ON reflections USING GIN (content gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS reflections_category_trgm_idx ON reflections USING GIN (category gin_trgm_ops)",
)

# Maximum number of records that get_recent() may return
MAX_LIMIT = 1000


class ReflectionLog:
    """
    Stores trade observations and learnings in PostgreSQL.

    Args:
        dsn: PostgreSQL connection string.
             Example: "postgresql://kaironis:secret@localhost/kaironis"
        pool: Existing asyncpg connection pool (optional; overrides dsn).
    """

    def __init__(
        self,
        dsn: Optional[str] = None,
        pool: Optional[asyncpg.Pool] = None,
    ) -> None:
        self._dsn = dsn
        self._pool: Optional[asyncpg.Pool] = pool
        # Track whether we created the pool ourselves (True) or received it injected (False).
        # close() only closes self-owned pools to avoid destroying external pools.
        self._owns_pool: bool = pool is None
        self._pool_init_lock = asyncio.Lock()

    async def _get_pool(self) -> asyncpg.Pool:
        """Lazy initialization of the connection pool (race-condition safe)."""
        if self._pool is None:
            async with self._pool_init_lock:
                if self._pool is None:
                    if not self._dsn:
                        raise ValueError("No DSN provided for ReflectionLog")
                    self._pool = await asyncpg.create_pool(self._dsn)
        return self._pool

    async def initialize(self) -> None:
        """
        Create the table and indices if they do not exist yet.

        Base DDL (table + standard indexes) is executed in one transaction.
        GIN trigram indexes are attempted afterwards; if pg_trgm is not available,
        a warning is logged and the rest of startup continues.

        Tip: pre-create pg_trgm in production::

            docker exec kaironis-postgres psql -U postgres -d kaironis \\
                -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
        """
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            # Base structure atomically in one transaction
            async with conn.transaction():
                for statement in CREATE_TABLE_STATEMENTS:
                    stmt = statement.strip()
                    if stmt:
                        await conn.execute(stmt)

            # Trigram indexes optional — require pg_trgm extension
            for statement in TRGM_INDEX_STATEMENTS:
                stmt = statement.strip()
                if stmt:
                    try:
                        await conn.execute(stmt)
                    except asyncpg.UndefinedObjectError:
                        logger.warning(
                            "pg_trgm extension not available — trigram index skipped. "
                            "Pre-create the extension for better ILIKE performance: "
                            "docker exec kaironis-postgres psql -U postgres -d kaironis "
                            "-c \"CREATE EXTENSION IF NOT EXISTS pg_trgm;\""
                        )
                        break  # Both indexes require pg_trgm; one warning is enough

        logger.info("ReflectionLog table initialized")

    async def close(self) -> None:
        """Close the connection pool — only if we created it ourselves."""
        if self._pool is not None and self._owns_pool:
            await self._pool.close()
            self._pool = None

    # ─────────────────────────────────────────────────────────────────
    # Write
    # ─────────────────────────────────────────────────────────────────

    async def log_observation(
        self,
        category: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> int:
        """
        Store an observation or learning.

        Args:
            category: One of: trade_setup, market_observation,
                      lesson_learned, strategy_note.
            content: The text of the observation.
            metadata: Optional extra data as dict (stored as JSONB).

        Returns:
            The new record ID.

        Raises:
            ValueError: If category is invalid or content is empty.
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
                f"Invalid category '{category}'. "
                f"Use one of: {', '.join(sorted(VALID_CATEGORIES))}"
            )

        content = content.strip()
        if not content:
            raise ValueError("Content must not be empty")

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
            "Observation stored: id=%d category=%s chars=%d",
            record_id, category, len(content)
        )
        return record_id

    # ─────────────────────────────────────────────────────────────────
    # Read
    # ─────────────────────────────────────────────────────────────────

    async def get_recent(
        self,
        limit: int = 10,
        category: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve the most recent observations.

        Args:
            limit: Maximum number of records (default: 10). Must be >= 1 and <= MAX_LIMIT.
            category: Filter by category (optional). Must be one of VALID_CATEGORIES.

        Returns:
            List of dicts with id, category, content, metadata, created_at.

        Raises:
            TypeError: If limit is not an integer (or is a bool).
            ValueError: If limit is outside the range [1, MAX_LIMIT].
            TypeError: If category is not a string.
            ValueError: If category is not in VALID_CATEGORIES.
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
                    f"Invalid category '{category}'. "
                    f"Use one of: {', '.join(sorted(VALID_CATEGORIES))}"
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
        Full-text search in PostgreSQL via ILIKE (portable, no tsvector setup needed).

        Args:
            query: Search term(s).
            limit: Maximum number of results (default: 20). Must be >= 1 and <= MAX_LIMIT.

        Returns:
            List of matching dicts, sorted by date (most recent first).

        Raises:
            TypeError: If query is not a string or limit is not an integer.
            ValueError: If limit is outside the range [1, MAX_LIMIT].
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

        # Log anonymised query (first 4 chars + "...") to avoid leaking reflection data
        masked_query = query[:4] + "..." if len(query) > 4 else "***"
        logger.debug("Search '%s' (len=%d): %d results", masked_query, len(query), len(rows))
        return [_row_to_dict(row) for row in rows]


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    """Convert an asyncpg Record to a plain dict."""
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
