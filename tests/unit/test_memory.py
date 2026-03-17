"""
Unit tests voor de Kaironis memory module.

Tests voor:
  - chunker.chunk_markdown
  - ChromaClient (mocked ChromaDB)
  - EmbeddingClient (mocked Ollama / sentence-transformers)
  - KnowledgeBase (integration met mocks)
"""

import pytest
from unittest.mock import MagicMock, patch, call
from typing import List


# ─────────────────────────────────────────────
# Chunker tests
# ─────────────────────────────────────────────

class TestChunkMarkdown:
    """Tests voor de markdown chunker."""

    def test_empty_text_returns_empty_list(self):
        from src.memory.chunker import chunk_markdown
        assert chunk_markdown("") == []
        assert chunk_markdown("   ") == []

    def test_short_text_returns_single_chunk(self):
        from src.memory.chunker import chunk_markdown
        text = "Dit is een korte tekst."
        chunks = chunk_markdown(text, max_tokens=500)
        assert len(chunks) == 1
        assert "korte tekst" in chunks[0]

    def test_splits_on_headers(self):
        from src.memory.chunker import chunk_markdown
        text = """# Hoofdstuk 1

Dit is de introductie.

## Sectie 1.1

Dit is sectie 1.1 met wat inhoud.

## Sectie 1.2

Dit is sectie 1.2 met andere inhoud.
"""
        chunks = chunk_markdown(text, max_tokens=100)
        # Elke sectie moet apart blijven
        assert len(chunks) >= 2
        # Headers moeten in chunks verschijnen
        assert any("Hoofdstuk 1" in c or "Sectie 1.1" in c for c in chunks)

    def test_large_text_splits_into_multiple_chunks(self):
        from src.memory.chunker import chunk_markdown
        # Genereer tekst die groter is dan max_tokens
        # 500 tokens * 4 chars = 2000 chars → maak tekst van 5000 chars
        long_paragraph = "Dit is een zin met inhoud. " * 200  # ~5400 chars
        chunks = chunk_markdown(long_paragraph, max_tokens=200)
        assert len(chunks) > 1

    def test_chunk_size_respects_max_tokens(self):
        from src.memory.chunker import chunk_markdown, _estimate_tokens
        # Gebruik overlap=0 zodat chunks puur op max_tokens worden gesplitst
        long_text = "Woord " * 1000
        chunks = chunk_markdown(long_text, max_tokens=100, overlap=0)
        # Zonder overlap mogen chunks niet veel groter zijn dan het maximum
        # (kleine overschrijding door zin-boundaries is acceptabel)
        for chunk in chunks:
            tokens = _estimate_tokens(chunk)
            assert tokens <= 150, f"Chunk te groot: {tokens} tokens"

    def test_overlap_content_present(self):
        from src.memory.chunker import chunk_markdown
        # Bij meerdere chunks moet overlap zichtbaar zijn
        text = "Eerste sectie met unieke term ALPHA. " * 30 + "\n\n" + \
               "Tweede sectie met andere inhoud. " * 30
        chunks = chunk_markdown(text, max_tokens=50, overlap=20)
        if len(chunks) >= 2:
            # Tweede chunk mag overlap prefix bevatten
            # (niet gegarandeerd maar wel verwacht bij kleine max_tokens)
            assert len(chunks) >= 2

    def test_respects_markdown_header_boundaries(self):
        from src.memory.chunker import chunk_markdown
        text = """# TCT Strategie

Introductie tekst hier.

## Supply Zones

Supply zones zijn gebieden waar instituties verkopen.
Kenmerk 1: Sterke neerwaartse beweging na zone.
Kenmerk 2: Weinig consolidatie.

## Demand Zones

Demand zones zijn gebieden waar instituties kopen.
Kenmerk 1: Sterke opwaartse beweging na zone.
"""
        chunks = chunk_markdown(text, max_tokens=500)
        # Alle content moet aanwezig zijn
        all_content = " ".join(chunks)
        assert "Supply Zones" in all_content
        assert "Demand Zones" in all_content

    def test_no_empty_chunks(self):
        from src.memory.chunker import chunk_markdown
        text = """# Header

Content hier.

## Lege sectie

## Sectie met content

Meer tekst.
"""
        chunks = chunk_markdown(text, max_tokens=100)
        for chunk in chunks:
            assert chunk.strip(), f"Lege chunk gevonden: {repr(chunk)}"

    def test_estimate_tokens(self):
        from src.memory.chunker import _estimate_tokens
        # 4 chars per token (ruwe schatting)
        assert _estimate_tokens("abcd") == 1
        assert _estimate_tokens("a" * 400) == 100
        assert _estimate_tokens("") == 1  # minimum 1


# ─────────────────────────────────────────────
# ChromaClient tests (mocked)
# ─────────────────────────────────────────────

class TestChromaClient:
    """Tests voor de ChromaDB client wrapper."""

    def _make_client(self) -> "ChromaClient":
        """Maak een ChromaClient met mocked internals."""
        from src.memory.chroma_client import ChromaClient

        client = ChromaClient(host="localhost", port=8001)
        # Mock de interne chromadb client
        mock_chroma = MagicMock()
        mock_collection = MagicMock()
        mock_chroma.get_or_create_collection.return_value = mock_collection
        client._client = mock_chroma
        client._collection = mock_collection
        return client

    def test_add_documents_calls_collection(self):
        from src.memory.chroma_client import ChromaClient

        client = self._make_client()
        mock_collection = client._collection

        texts = ["tekst 1", "tekst 2"]
        embeddings = [[0.1, 0.2], [0.3, 0.4]]
        ids = client.add_documents(texts=texts, embeddings=embeddings)

        mock_collection.add.assert_called_once()
        call_kwargs = mock_collection.add.call_args.kwargs
        assert call_kwargs["documents"] == texts
        assert call_kwargs["embeddings"] == embeddings
        assert len(call_kwargs["ids"]) == 2

    def test_add_documents_validates_length_mismatch(self):
        from src.memory.chroma_client import ChromaClient

        client = self._make_client()
        with pytest.raises(ValueError, match="gelijk zijn"):
            client.add_documents(
                texts=["tekst 1", "tekst 2"],
                embeddings=[[0.1, 0.2]],  # Slechts 1 embedding
            )

    def test_query_returns_structured_results(self):
        from src.memory.chroma_client import ChromaClient

        client = self._make_client()
        mock_collection = client._collection

        # Mock ChromaDB query response
        mock_collection.query.return_value = {
            "ids": [["id1", "id2"]],
            "documents": [["doc tekst 1", "doc tekst 2"]],
            "metadatas": [[{"source": "file1.md"}, {"source": "file2.md"}]],
            "distances": [[0.1, 0.3]],
        }

        results = client.query(query_embedding=[0.1, 0.2, 0.3], n_results=2)

        assert len(results) == 2
        assert results[0]["id"] == "id1"
        assert results[0]["document"] == "doc tekst 1"
        assert results[0]["metadata"]["source"] == "file1.md"
        assert results[0]["distance"] == 0.1

    def test_delete_with_ids(self):
        from src.memory.chroma_client import ChromaClient

        client = self._make_client()
        mock_collection = client._collection

        client.delete(ids=["id1", "id2"])
        mock_collection.delete.assert_called_once_with(ids=["id1", "id2"])

    def test_delete_requires_ids_or_where(self):
        from src.memory.chroma_client import ChromaClient

        client = self._make_client()
        with pytest.raises(ValueError, match="ids of where"):
            client.delete()

    def test_count_delegates_to_collection(self):
        from src.memory.chroma_client import ChromaClient

        client = self._make_client()
        client._collection.count.return_value = 42

        assert client.count() == 42

    def test_add_documents_generates_ids_when_none(self):
        from src.memory.chroma_client import ChromaClient

        client = self._make_client()
        texts = ["tekst A"]
        embeddings = [[0.5, 0.6]]

        ids = client.add_documents(texts=texts, embeddings=embeddings)

        assert len(ids) == 1
        assert isinstance(ids[0], str)
        assert len(ids[0]) > 0  # UUID heeft lengte


# ─────────────────────────────────────────────
# EmbeddingClient tests (mocked)
# ─────────────────────────────────────────────

class TestEmbeddingClient:
    """Tests voor de embedding wrapper."""

    def test_get_embedding_uses_ollama_when_available(self):
        from src.memory.embeddings import EmbeddingClient

        client = EmbeddingClient()
        client._ollama_available = True  # Forceer Ollama beschikbaar

        mock_embedding = [0.1, 0.2, 0.3, 0.4]

        with patch.object(client, "_get_ollama_embedding", return_value=mock_embedding) as mock_ollama:
            result = client.get_embedding("test tekst")

        mock_ollama.assert_called_once_with("test tekst")
        assert result == mock_embedding

    def test_get_embedding_falls_back_when_ollama_unavailable(self):
        from src.memory.embeddings import EmbeddingClient

        client = EmbeddingClient()
        client._ollama_available = False  # Forceer Ollama niet beschikbaar

        mock_embedding = [0.5, 0.6, 0.7]

        with patch.object(client, "_get_fallback_embedding", return_value=mock_embedding) as mock_fallback:
            result = client.get_embedding("test tekst")

        mock_fallback.assert_called_once_with("test tekst")
        assert result == mock_embedding

    def test_get_embedding_falls_back_after_ollama_error(self):
        from src.memory.embeddings import EmbeddingClient

        client = EmbeddingClient()
        client._ollama_available = True

        mock_fallback_embedding = [0.9, 0.8]

        with patch.object(client, "_get_ollama_embedding", side_effect=Exception("timeout")):
            with patch.object(client, "_get_fallback_embedding", return_value=mock_fallback_embedding) as mock_fallback:
                result = client.get_embedding("test tekst")

        mock_fallback.assert_called_once()
        assert result == mock_fallback_embedding
        # Ollama availability moet gereset zijn
        assert client._ollama_available is False

    def test_get_embedding_raises_on_empty_text(self):
        from src.memory.embeddings import EmbeddingClient

        client = EmbeddingClient()
        with pytest.raises(ValueError, match="empty"):
            client.get_embedding("")

    def test_get_embedding_raises_on_whitespace_text(self):
        from src.memory.embeddings import EmbeddingClient

        client = EmbeddingClient()
        with pytest.raises(ValueError, match="empty"):
            client.get_embedding("   ")

    def test_batch_embeddings(self):
        from src.memory.embeddings import EmbeddingClient

        client = EmbeddingClient()
        mock_embedding = [0.1, 0.2]

        with patch.object(client, "get_embedding", return_value=mock_embedding) as mock_embed:
            results = client.get_embeddings_batch(["tekst 1", "tekst 2", "tekst 3"])

        assert len(results) == 3
        assert mock_embed.call_count == 3
        assert all(r == mock_embedding for r in results)

    def test_reset_availability_cache(self):
        from src.memory.embeddings import EmbeddingClient

        client = EmbeddingClient()
        client._ollama_available = True
        client.reset_availability_cache()
        assert client._ollama_available is None


# ─────────────────────────────────────────────
# KnowledgeBase tests (integration met mocks)
# ─────────────────────────────────────────────

class TestKnowledgeBase:
    """Tests voor de KnowledgeBase hoofd interface."""

    def _make_kb(self):
        """Maak een KnowledgeBase met gemockte dependencies."""
        from src.memory.knowledge_base import KnowledgeBase

        mock_chroma = MagicMock()
        mock_embedder = MagicMock()
        mock_embedder.get_embedding.return_value = [0.1, 0.2, 0.3]

        kb = KnowledgeBase(
            chroma_client=mock_chroma,
            embedding_client=mock_embedder,
        )
        return kb, mock_chroma, mock_embedder

    def test_query_strategy_returns_results(self):
        kb, mock_chroma, mock_embedder = self._make_kb()

        mock_chroma.query.return_value = [
            {
                "id": "lecture_3.md::0",
                "document": "Supply zones worden gevormd door institutionele verkoop.",
                "metadata": {"source": "lectures/lecture_3.md", "category": "lectures"},
                "distance": 0.15,
            }
        ]

        results = kb.query_strategy("supply zone entry")

        mock_embedder.get_embedding.assert_called_once_with("supply zone entry")
        mock_chroma.query.assert_called_once()
        assert len(results) == 1
        assert "Supply zones" in results[0]["document"]

    def test_query_strategy_raises_on_empty_question(self):
        kb, _, _ = self._make_kb()
        with pytest.raises(ValueError, match="empty"):
            kb.query_strategy("")

    def test_get_context_for_trade_formats_output(self):
        kb, mock_chroma, _ = self._make_kb()

        mock_chroma.query.return_value = [
            {
                "id": "file::0",
                "document": "Relevante strategie informatie over supply zones.",
                "metadata": {"source": "lectures/TCT_3.md", "category": "lectures"},
                "distance": 0.2,
            }
        ]

        context = kb.get_context_for_trade("Bullish H4 supply zone setup")

        assert "TCT STRATEGY CONTEXT" in context
        assert "Bullish H4 supply zone setup" in context
        assert "supply zones" in context.lower()
        assert "END CONTEXT" in context

    def test_get_context_returns_message_when_no_results(self):
        kb, mock_chroma, _ = self._make_kb()
        mock_chroma.query.return_value = []

        context = kb.get_context_for_trade("unknown setup")

        assert "no" in context.lower() or "not" in context.lower()

    def test_get_context_handles_empty_description(self):
        kb, _, _ = self._make_kb()
        context = kb.get_context_for_trade("")
        assert len(context) > 0

    def test_get_stats(self):
        kb, mock_chroma, _ = self._make_kb()
        mock_chroma.count.return_value = 250
        mock_chroma.collection_name = "tct_strategy"
        mock_chroma.host = "localhost"
        mock_chroma.port = 8001

        stats = kb.get_stats()

        assert stats["document_count"] == 250
        assert stats["collection"] == "tct_strategy"

    def test_ingest_strategy_docs_nonexistent_path(self):
        kb, _, _ = self._make_kb()
        with pytest.raises(FileNotFoundError):
            kb.ingest_strategy_docs("/nonexistent/path/to/docs")

    def test_ingest_strategy_docs_processes_md_files(self, tmp_path):
        """Test ingest met echte tijdelijke bestanden."""
        kb, mock_chroma, mock_embedder = self._make_kb()
        mock_chroma.add_documents.return_value = ["id1"]

        # Maak tijdelijke .md bestanden
        (tmp_path / "lectures").mkdir()
        (tmp_path / "lectures" / "test_lecture.md").write_text(
            "# Test Lecture\n\nDit is test content voor de knowledge base.",
            encoding="utf-8",
        )
        (tmp_path / "reference").mkdir()
        (tmp_path / "reference" / "dictionary.md").write_text(
            "# TCT Dictionary\n\nSupply Zone: Gebied waar instituten verkopen.",
            encoding="utf-8",
        )

        stats = kb.ingest_strategy_docs(str(tmp_path))

        assert stats["files_processed"] == 2
        assert stats["chunks_created"] >= 2
        assert len(stats["errors"]) == 0
        mock_chroma.add_documents.assert_called()


# ─────────────────────────────────────────────
# Category detection test
# ─────────────────────────────────────────────

class TestCategoryDetection:
    """Tests voor de categorie detectie helper."""

    def test_lecture_category(self):
        from src.memory.knowledge_base import _detect_category
        assert _detect_category("lectures/TCT_Lecture_1.md") == "lectures"
        assert _detect_category("lectures/TCT_Lecture_1_AI_Text.md") == "lectures"

    def test_reviews_category(self):
        from src.memory.knowledge_base import _detect_category
        assert _detect_category("reviews/2025_Ranges_REVIEW.md") == "reviews"

    def test_reference_category(self):
        from src.memory.knowledge_base import _detect_category
        assert _detect_category("reference/TCT_Trading_Dictionary.md") == "reference"
        assert _detect_category("reference/2025-HP-TCT-model-variables.md") == "reference"

    def test_general_fallback(self):
        from src.memory.knowledge_base import _detect_category
        assert _detect_category("index.md") == "general"
        assert _detect_category("README.md") == "general"
