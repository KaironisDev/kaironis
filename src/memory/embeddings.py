"""
Embedding wrapper voor Kaironis memory module.

Primair: Ollama nomic-embed-text via SSH tunnel naar sandbox.
Fallback: sentence-transformers lokaal (all-MiniLM-L6-v2).

Configuratie via environment variables:
  OLLAMA_HOST  - host van Ollama (default: localhost)
  OLLAMA_PORT  - port van Ollama (default: 11435 via SSH tunnel)
"""

import os
import logging
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "localhost")
OLLAMA_PORT = int(os.getenv("OLLAMA_PORT", "11435"))
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "nomic-embed-text")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "30"))

# Fallback model (sentence-transformers)
FALLBACK_MODEL = os.getenv("EMBEDDING_FALLBACK_MODEL", "all-MiniLM-L6-v2")


class EmbeddingClient:
    """
    Client voor het genereren van text embeddings.

    Probeert eerst Ollama (nomic-embed-text) te gebruiken.
    Als Ollama niet bereikbaar is, valt terug op sentence-transformers lokaal.

    Example::

        client = EmbeddingClient()
        embedding = client.get_embedding("Supply zone identified on H4")
    """

    def __init__(
        self,
        ollama_host: str = OLLAMA_HOST,
        ollama_port: int = OLLAMA_PORT,
        model: str = OLLAMA_MODEL,
    ) -> None:
        self.ollama_host = ollama_host
        self.ollama_port = ollama_port
        self.model = model
        self._ollama_available: Optional[bool] = None  # None = nog niet getest
        self._fallback_model = None  # Lazy loaded

    @property
    def _ollama_url(self) -> str:
        return f"http://{self.ollama_host}:{self.ollama_port}/api/embeddings"

    def _check_ollama(self) -> bool:
        """Test of Ollama bereikbaar is (cached na eerste check)."""
        if self._ollama_available is not None:
            return self._ollama_available

        try:
            resp = requests.get(
                f"http://{self.ollama_host}:{self.ollama_port}/api/tags",
                timeout=5,
            )
            self._ollama_available = resp.status_code == 200
        except Exception as exc:
            logger.warning("Ollama niet bereikbaar op %s:%d — %s", self.ollama_host, self.ollama_port, exc)
            self._ollama_available = False

        if self._ollama_available:
            logger.info("Ollama beschikbaar op %s:%d", self.ollama_host, self.ollama_port)
        else:
            logger.warning("Ollama niet beschikbaar — fallback naar sentence-transformers")

        return self._ollama_available

    def _get_ollama_embedding(self, text: str) -> List[float]:
        """Vraag embedding op via Ollama API."""
        payload = {"model": self.model, "prompt": text}
        resp = requests.post(self._ollama_url, json=payload, timeout=OLLAMA_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        embedding: List[float] = data["embedding"]
        return embedding

    def _get_fallback_embedding(self, text: str) -> List[float]:
        """Genereer embedding via sentence-transformers (lokaal)."""
        if self._fallback_model is None:
            try:
                from sentence_transformers import SentenceTransformer

                logger.info("Laden van fallback model: %s", FALLBACK_MODEL)
                self._fallback_model = SentenceTransformer(FALLBACK_MODEL)
            except ImportError as exc:
                raise RuntimeError(
                    "sentence-transformers niet geïnstalleerd. "
                    "Installeer met: pip install sentence-transformers"
                ) from exc

        vector = self._fallback_model.encode(text, normalize_embeddings=True)
        return vector.tolist()

    def get_embedding(self, text: str) -> List[float]:
        """
        Genereer een embedding vector voor de gegeven tekst.

        Probeert Ollama (nomic-embed-text), valt terug op sentence-transformers
        als Ollama niet bereikbaar is.

        Args:
            text: De tekst om te embedden.

        Returns:
            Embedding vector als lijst van floats.

        Raises:
            RuntimeError: Als noch Ollama noch de fallback beschikbaar is.
        """
        if not text or not text.strip():
            raise ValueError("Tekst mag niet leeg zijn")

        if self._check_ollama():
            try:
                return self._get_ollama_embedding(text)
            except Exception as exc:
                logger.error("Ollama embedding mislukt: %s — switch naar fallback", exc)
                self._ollama_available = False  # Reset cache

        return self._get_fallback_embedding(text)

    def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Genereer embeddings voor meerdere teksten.

        Args:
            texts: Lijst van teksten.

        Returns:
            Lijst van embedding vectors.
        """
        return [self.get_embedding(text) for text in texts]

    def reset_availability_cache(self) -> None:
        """Reset de Ollama availability cache (handig na tunnel restart)."""
        self._ollama_available = None
