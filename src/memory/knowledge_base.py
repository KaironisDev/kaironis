"""
Knowledge base interface voor Kaironis — hoofd entry point voor de memory module.

Beheert het inladen van TCT strategy documenten, semantisch zoeken,
en het genereren van context voor trading decisions.

Example::

    kb = KnowledgeBase()
    kb.ingest_strategy_docs("docs/strategy/")
    results = kb.query_strategy("supply zone entry criteria")
    context = kb.get_context_for_trade("Bullish setup op H4 supply zone, 09:30 NY")
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .chroma_client import ChromaClient
from .chunker import chunk_markdown
from .embeddings import EmbeddingClient

logger = logging.getLogger(__name__)

# Batch grootte voor ChromaDB upserts
_INGEST_BATCH_SIZE = int(os.getenv("KB_INGEST_BATCH_SIZE", "50"))

# Max context lengte voor trade context output
_MAX_CONTEXT_CHARS = int(os.getenv("KB_MAX_CONTEXT_CHARS", "4000"))


class KnowledgeBase:
    """
    Hoofd interface voor de Kaironis TCT strategy knowledge base.

    Combineert ChromaDB opslag, Ollama embeddings en markdown chunking
    in een eenvoudige API.

    Args:
        chroma_client: ChromaDB client (default: nieuwe instantie).
        embedding_client: Embedding client (default: nieuwe instantie).
        chunk_max_tokens: Max tokens per chunk bij ingest (default: 500).
        chunk_overlap: Token overlap tussen chunks (default: 50).
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
        Lees alle .md bestanden uit docs_path, chunk ze en sla op in ChromaDB.

        Zoekt recursief naar .md bestanden in subdirectories
        (lectures/, reviews/, reference/).

        Args:
            docs_path: Pad naar de strategy docs directory.
            force_reingest: Als True, verwijder bestaande data eerst.

        Returns:
            Dict met statistieken: files_processed, chunks_created, errors.
        """
        path = Path(docs_path)
        if not path.exists():
            raise FileNotFoundError(f"Strategy docs directory niet gevonden: {docs_path}")

        if force_reingest:
            logger.warning("Force reingest — bestaande collection wordt geleegd")
            self.chroma.reset_collection()

        md_files = sorted(path.rglob("*.md"))
        if not md_files:
            logger.warning("Geen .md bestanden gevonden in %s", docs_path)
            return {"files_processed": 0, "chunks_created": 0, "errors": []}

        logger.info("Ingesteren van %d markdown bestanden uit %s", len(md_files), docs_path)

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
            """Sla de huidige batch op in ChromaDB."""
            if not batch_texts:
                return
            self.chroma.add_documents(
                texts=batch_texts,
                embeddings=batch_embeddings,
                metadatas=batch_metadatas,
                ids=batch_ids,
            )
            logger.debug("Batch van %d chunks opgeslagen", len(batch_texts))
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

                # Relatief pad voor metadata
                try:
                    rel_path = str(md_file.relative_to(path))
                except ValueError:
                    rel_path = md_file.name

                # Bepaal categorie op basis van subdir
                category = _detect_category(rel_path)

                for chunk_idx, chunk in enumerate(chunks):
                    # Skip header-only chunks: kort (<150 tekens) én geen zin (geen punt/komma/dubbele punt)
                    if chunk_idx == 0 and len(chunk) < 150 and not any(c in chunk for c in (".", ",", ":")):
                        logger.debug(
                            "Chunk 0 van %s overgeslagen (header/bestandsnaam detectie, %d tekens)",
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
                            "Embedding mislukt voor %s chunk %d: %s",
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
                logger.debug("Verwerkt: %s (%d chunks)", rel_path, len(chunks))

            except Exception as exc:
                logger.error("Fout bij verwerken van %s: %s", md_file, exc)
                stats["errors"].append(f"{md_file.name}: {exc}")  # type: ignore[attr-defined]

        # Laatste batch
        flush_batch()

        logger.info(
            "Ingest compleet: %d bestanden, %d chunks, %d fouten",
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
        Semantisch zoeken in de TCT strategy knowledge base.

        Args:
            question: De zoekvraag in natuurlijke taal.
            n_results: Aantal resultaten (default: 5).
            category_filter: Filter op categorie: "lectures", "reviews", "reference".

        Returns:
            Lijst van dicts met keys:
              - document (str): De gevonden tekst chunk
              - metadata (dict): Bronbestand, categorie, etc.
              - distance (float): Cosine afstand (lager = relevanter)
        """
        if not question or not question.strip():
            raise ValueError("Zoekvraag mag niet leeg zijn")

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
            "Query '%s': %d resultaten gevonden",
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
        Genereer geformatteerde strategy context voor een trade setup.

        Zoekt relevante TCT kennis op basis van de setup beschrijving
        en formatteert deze als leesbare tekst voor Kaironis.

        Args:
            setup_description: Beschrijving van de trade setup (bijv.
                "Bullish H4 supply zone, 09:30 NY open, liquiditeit boven swept").
            n_results: Aantal bronnen om te raadplegen (default: 5).

        Returns:
            Geformatteerde string met relevante strategy context,
            klaar om aan Kaironis's prompt toe te voegen.
        """
        if not setup_description or not setup_description.strip():
            return "Geen setup beschrijving opgegeven."

        try:
            results = self.query_strategy(setup_description, n_results=n_results)
        except Exception as exc:
            logger.error("Context ophalen mislukt: %s", exc)
            return f"[Fout bij ophalen strategy context: {exc}]"

        if not results:
            return "Geen relevante strategy informatie gevonden voor deze setup."

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

            source = meta.get("source", "onbekend")
            category = meta.get("category", "")
            relevance = max(0.0, 1.0 - distance)

            header = f"[{i}] {source}"
            if category:
                header += f" ({category})"
            header += f" — relevantie: {relevance:.0%}"

            entry = f"{header}\n{doc}\n"

            # Stop als we de max context limiet bereiken
            if total_chars + len(entry) > _MAX_CONTEXT_CHARS:
                lines.append(f"[{i}+ meer resultaten afgekapt wegens lengte limiet]")
                break

            lines.append(entry)
            total_chars += len(entry)

        lines.append("=== EINDE CONTEXT ===")
        return "\n".join(lines)

    # ─────────────────────────────────────────────
    # Utilities
    # ─────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Geeft statistieken over de knowledge base terug."""
        return {
            "collection": self.chroma.collection_name,
            "document_count": self.chroma.count(),
            "chromadb_host": self.chroma.host,
            "chromadb_port": self.chroma.port,
            "ollama_model": self.embedder.model,
        }


def _detect_category(rel_path: str) -> str:
    """Detecteer de categorie van een document op basis van het pad."""
    lower = rel_path.lower()
    if "lecture" in lower:
        return "lectures"
    if "review" in lower:
        return "reviews"
    if "reference" in lower or "dictionary" in lower or "variable" in lower:
        return "reference"
    return "general"
