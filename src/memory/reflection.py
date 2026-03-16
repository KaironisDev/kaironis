"""
Reflection & Learning System for Kaironis.

Stores trade observations, learnings and strategy notes in PostgreSQL.
Full-text search via PostgreSQL ILIKE with wildcard injection protection.

Example::

    log = ReflectionLog(dsn="postgresql://user:pass@localhost/kaironis")
    await log.log_observation("lesson_learned", "Never trade in the first 5 min after NY open")
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

# Valid categories
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
        """Create the table and indices if they do not exist yet."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            # Execute statements individually
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS reflections (
                    id SERIAL PRIMARY KEY,
                    category VARCHAR(50) NOT NULL,
                    content TEXT NOT NULL,
                    metadata JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS reflections_category_idx ON reflections(category)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS reflections_created_idx ON reflections(created_at DESC)"
            )
        logger.info("ReflectionLog table initialized")

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    # ─────────────────────────────────────────────
    # Write
    # ─────────────────────────────────────────────

    async def log_observation(
        self,
        category: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
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
                json.dumps(metadata) if metadata else None,
            )

        record_id: int = row["id"]
        logger.info(
            "Observation stored: id=%d category=%s chars=%d",
            record_id, category, len(content)
        )
        return record_id

    # ─────────────────────────────────────────────
    # Read
    # ─────────────────────────────────────────────

    async def get_recent(
        self,
        limit: int = 10,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve the most recent observations.

        Args:
            limit: Maximum number of records (default: 10).
            category: Filter by category (optional).

        Returns:
            List of dicts with id, category, content, metadata, created_at.
        """
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
        Full-text search in PostgreSQL via ILIKE (portable, no tsvector setup needed).

        Args:
            query: Search term(s).

        Returns:
            List of matching dicts, sorted by date (most recent first).
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

        logger.debug("Search '%s': %d results", query, len(rows))
        return [_row_to_dict(row) for row in rows]


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _row_to_dict(row: asyncpg.Record) -> Dict[str, Any]:
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
