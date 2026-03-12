"""
Memory module voor Kaironis.

Biedt vector store opslag en semantisch zoeken in TCT strategy documenten.

Components:
    KnowledgeBase   — Hoofd interface: ingest, query, context generatie
    ChromaClient    — ChromaDB HTTP client wrapper
    EmbeddingClient — Ollama (nomic-embed-text) + fallback embeddings
    chunk_markdown  — Markdown text chunker

Typisch gebruik::

    from src.memory import KnowledgeBase

    kb = KnowledgeBase()
    kb.ingest_strategy_docs("docs/strategy/")

    context = kb.get_context_for_trade(
        "Bullish H4 supply zone, liquiditeit boven gesweept, 09:30 NY"
    )

SSH tunnel setup (als ChromaDB en Ollama op sandbox draaien)::

    from src.utils.ssh_tunnel import chromadb_tunnel, ollama_tunnel

    with chromadb_tunnel() as chroma_port, ollama_tunnel() as ollama_port:
        kb = KnowledgeBase()
        results = kb.query_strategy("entry criteria supply zone")
"""

from .chroma_client import ChromaClient
from .chunker import chunk_markdown
from .embeddings import EmbeddingClient
from .knowledge_base import KnowledgeBase

__all__ = [
    "KnowledgeBase",
    "ChromaClient",
    "EmbeddingClient",
    "chunk_markdown",
]
