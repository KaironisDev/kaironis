"""
Knowledge base interface for Kaironis — main entry point for the memory module.

Manages ingestion of TCT strategy documents, semantic search,
and context generation for trading decisions.

Example::

    kb = KnowledgeBase()
    kb.ingest_strategy_docs("docs/strategy/")
    results = kb.query_strategy("supply zone entry criteria")
    context = kb.get_context_for_trade("Bullish setup on H4 supply zone, 09:30 NY")
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .chroma_client import ChromaClient
from .chunker import chunk_markdown
from .embeddings import EmbeddingClient

logger = logging.getLogger(__name__)

# Batch size for ChromaDB upserts
_INGEST_BATCH_SIZE = int(os.getenv("KB_INGEST_BATCH_SIZE", "50"))

# Max context length for trade context output
_MAX_CONTEXT_CHARS = int(os.getenv("KB_MAX_CONTEXT_CHARS", "4000"))


class KnowledgeBase:
    """
    Main interface for the Kaironis TCT strategy knowledge base.

    Combines ChromaDB storage, Ollama embeddings and markdown chunking
    in a simple API.

    Args:
        chroma_client: ChromaDB client (default: new instance).
        embedding_client: Embedding client (default: new instance).
        chunk_max_tokens: Max tokens per chunk during ingest (default: 500).
        chunk_overlap: Token overlap between chunks (default: 50).
    """

    def __init__(
        self,
        chroma_client: Optional[ChromaClient] = None,
        embedding_client: Optional[EmbeddingClient] = None,
        chunk_max_tokens: int = 500,
        chunk_overlap: int = 50,
    ) -> None:
        self.chroma = chroma_client or ChromaClient()
        self.embedder = embedding_client or EmbeddingClient()
        self.chunk_max_tokens = chunk_max_tokens
        self.chunk_overlap = chunk_overlap

    # ─────────────────────────────────────────────
    # Ingest
    # ─────────────────────────────────────────────

    def ingest_strategy_docs(
        self,
        docs_path: str,
        force_reingest: bool = False,
    ) -> Dict[str, Any]:
        """
        Read all .md files from docs_path, chunk them and store in ChromaDB.

        Recursively searches for .md files in subdirectories
        (lectures/, reviews/, reference/).

        Args:
            docs_path: Path to the strategy docs directory.
            force_reingest: If True, clear existing data first.

        Returns:
            Dict with statistics: files_processed, chunks_created, errors.
        """
        path = Path(docs_path)
        if not path.exists():
            raise FileNotFoundError(f"Strategy docs directory not found: {docs_path}")

        if force_reingest:
            logger.warning("Force reingest — existing collection will be cleared")
            self.chroma.reset_collection()

        md_files = sorted(path.rglob("*.md"))
        if not md_files:
            logger.warning("No .md files found in %s", docs_path)
            return {"files_processed": 0, "chunks_created": 0, "errors": []}

        logger.info("Ingesting %d markdown files from %s", len(md_files), docs_path)

        stats: Dict[str, Any] = {
            "files_processed": 0,
            "chunks_created": 0,
            "errors": [],
        }

        # Batch buffers
        batch_texts: List[str] = []
        batch_embeddings: List[List[float]] = []
        batch_metadatas: List[Dict[str, Any]] = []
        batch_ids: List[str] = []

        def flush_batch() -> None:
            """Store the current batch in ChromaDB."""
            if not batch_texts:
                return
            self.chroma.add_documents(
                texts=batch_texts,
                embeddings=batch_embeddings,
                metadatas=batch_metadatas,
                ids=batch_ids,
            )
            logger.debug("Batch of %d chunks stored", len(batch_texts))
            batch_texts.clear()
            batch_embeddings.clear()
            batch_metadatas.clear()
            batch_ids.clear()

        for md_file in md_files:
            try:
                text = md_file.read_text(encoding="utf-8")
                chunks = chunk_markdown(
                    text,
                    max_tokens=self.chunk_max_tokens,
                    overlap=self.chunk_overlap,
                )

                # Relative path for metadata
                try:
                    rel_path = str(md_file.relative_to(path))
                except ValueError:
                    rel_path = md_file.name

                # Determine category based on subdirectory
                category = _detect_category(rel_path)

                for chunk_idx, chunk in enumerate(chunks):
                    # Skip header-only chunks: short (<150 chars) and no sentence (no period/comma/colon)
                    if chunk_idx == 0 and len(chunk) < 150 and not any(c in chunk for c in (".", ",", ":")):
                        logger.debug(
                            "Chunk 0 of %s skipped (header/filename detection, %d chars)",
                            rel_path, len(chunk),
                        )
                        continue

                    chunk_id = f"{rel_path}::{chunk_idx}"
                    meta: Dict[str, Any] = {
                        "source": rel_path,
                        "filename": md_file.name,
                        "category": category,
                        "chunk_index": chunk_idx,
                        "total_chunks": len(chunks),
                    }

                    try:
                        embedding = self.embedder.get_embedding(chunk)
                    except Exception as emb_exc:
                        logger.error(
                            "Embedding failed for %s chunk %d: %s",
                            rel_path, chunk_idx, emb_exc
                        )
                        stats["errors"].append(  # type: ignore[attr-defined]
                            f"{rel_path}::{chunk_idx}: embedding error"
                        )
                        continue

                    batch_texts.append(chunk)
                    batch_embeddings.append(embedding)
                    batch_metadatas.append(meta)
                    batch_ids.append(chunk_id)

                    if len(batch_texts) >= _INGEST_BATCH_SIZE:
                        flush_batch()

                stats["files_processed"] = stats["files_processed"] + 1
                stats["chunks_created"] = stats["chunks_created"] + len(chunks)
                logger.debug("Processed: %s (%d chunks)", rel_path, len(chunks))

            except Exception as exc:
                logger.error("Error processing %s: %s", md_file, exc)
                stats["errors"].append(f"{md_file.name}: {exc}")  # type: ignore[attr-defined]

        # Final batch
        flush_batch()

        logger.info(
            "Ingest complete: %d files, %d chunks, %d errors",
            stats["files_processed"],
            stats["chunks_created"],
            len(stats["errors"]),
        )
        return stats

    # ─────────────────────────────────────────────
    # Queries
    # ─────────────────────────────────────────────

    def query_strategy(
        self,
        question: str,
        n_results: int = 5,
        category_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search in the TCT strategy knowledge base.

        Args:
            question: The search query in natural language.
            n_results: Number of results (default: 5).
            category_filter: Filter by category: "lectures", "reviews", "reference".

        Returns:
            List of dicts with keys:
              - document (str): The found text chunk
              - metadata (dict): Source file, category, etc.
              - distance (float): Cosine distance (lower = more relevant)
        """
        if not question or not question.strip():
            raise ValueError("Search query must not be empty")

        query_embedding = self.embedder.get_embedding(question)

        where: Optional[Dict[str, Any]] = None
        if category_filter:
            where = {"category": {"$eq": category_filter}}

        results = self.chroma.query(
            query_embedding=query_embedding,
            n_results=n_results,
            where=where,
        )

        logger.debug(
            "Query '%s': %d results found",
            question[:50],
            len(results),
        )
        return results

    def get_context_for_trade(
        self,
        setup_description: str,
        n_results: int = 5,
    ) -> str:
        """
        Generate formatted strategy context for a trade setup.

        Looks up relevant TCT knowledge based on the setup description
        and formats it as readable text for Kaironis.

        Args:
            setup_description: Description of the trade setup (e.g.
                "Bullish H4 supply zone, 09:30 NY open, liquidity above swept").
            n_results: Number of sources to consult (default: 5).

        Returns:
            Formatted string with relevant strategy context,
            ready to append to Kaironis's prompt.
        """
        if not setup_description or not setup_description.strip():
            return "No setup description provided."

        try:
            results = self.query_strategy(setup_description, n_results=n_results)
        except Exception as exc:
            logger.error("Failed to retrieve context: %s", exc)
            return f"[Error retrieving strategy context: {exc}]"

        if not results:
            return "No relevant strategy information found for this setup."

        lines: List[str] = [
            "=== TCT STRATEGY CONTEXT ===",
            f"Setup: {setup_description}",
            "",
        ]

        total_chars = sum(len(line) for line in lines)

        for i, result in enumerate(results, 1):
            doc = result.get("document", "")
            meta = result.get("metadata", {})
            distance = result.get("distance", 1.0)

            source = meta.get("source", "unknown")
            category = meta.get("category", "")
            relevance = max(0.0, 1.0 - distance)

            header = f"[{i}] {source}"
            if category:
                header += f" ({category})"
            header += f" — relevance: {relevance:.0%}"

            entry = f"{header}\n{doc}\n"

            # Stop if we hit the max context length limit
            if total_chars + len(entry) > _MAX_CONTEXT_CHARS:
                lines.append(f"[{i}+ more results truncated due to length limit]")
                break

            lines.append(entry)
            total_chars += len(entry)

        lines.append("=== END CONTEXT ===")
        return "\n".join(lines)

    # ─────────────────────────────────────────────
    # Utilities
    # ─────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Return statistics about the knowledge base."""
        return {
            "collection": self.chroma.collection_name,
            "document_count": self.chroma.count(),
            "chromadb_host": self.chroma.host,
            "chromadb_port": self.chroma.port,
            "ollama_model": self.embedder.model,
        }


def _detect_category(rel_path: str) -> str:
    """Detect the category of a document based on its path."""
    lower = rel_path.lower()
    if "lecture" in lower:
        return "lectures"
    if "review" in lower:
        return "reviews"
    if "reference" in lower or "dictionary" in lower or "variable" in lower:
        return "reference"
    return "general"
