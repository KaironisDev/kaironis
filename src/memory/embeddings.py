"""
Embedding wrapper for the Kaironis memory module.

Primary: Ollama nomic-embed-text via SSH tunnel to sandbox.
Fallback: sentence-transformers locally (all-MiniLM-L6-v2).

Configuration via environment variables:
  OLLAMA_HOST  - Ollama host (default: localhost)
  OLLAMA_PORT  - Ollama port (default: 11435 via SSH tunnel)
"""

import os
import logging
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

# Strip http(s):// prefix als aanwezig — we bouwen de URL zelf
_raw_host = os.getenv("OLLAMA_HOST", "localhost")
OLLAMA_HOST = _raw_host.replace("http://", "").replace("https://", "").split(":")[0]
OLLAMA_PORT = int(os.getenv("OLLAMA_PORT", "11435"))
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "nomic-embed-text")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "30"))

# Fallback model (sentence-transformers)
FALLBACK_MODEL = os.getenv("EMBEDDING_FALLBACK_MODEL", "all-MiniLM-L6-v2")


class EmbeddingClient:
    """
    Client for generating text embeddings.

    Tries Ollama (nomic-embed-text) first.
    Falls back to sentence-transformers locally if Ollama is unavailable.

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
        self._ollama_available: Optional[bool] = None  # None = not yet tested
        self._fallback_model = None  # Lazy loaded

    @property
    def _ollama_url(self) -> str:
        return f"http://{self.ollama_host}:{self.ollama_port}/api/embeddings"

    def _check_ollama(self) -> bool:
        """Test whether Ollama is reachable (cached after first check)."""
        if self._ollama_available is not None:
            return self._ollama_available

        try:
            resp = requests.get(
                f"http://{self.ollama_host}:{self.ollama_port}/api/tags",
                timeout=5,
            )
            self._ollama_available = resp.status_code == 200
        except Exception as exc:
            logger.warning("Ollama not reachable at %s:%d — %s", self.ollama_host, self.ollama_port, exc)
            self._ollama_available = False

        if self._ollama_available:
            logger.info("Ollama available at %s:%d", self.ollama_host, self.ollama_port)
        else:
            logger.warning("Ollama not available — falling back to sentence-transformers")

        return self._ollama_available

    def _get_ollama_embedding(self, text: str) -> List[float]:
        """Request embedding via Ollama API."""
        payload = {"model": self.model, "prompt": text}
        resp = requests.post(self._ollama_url, json=payload, timeout=OLLAMA_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        embedding: List[float] = data["embedding"]
        return embedding

    def _get_fallback_embedding(self, text: str) -> List[float]:
        """Generate embedding via sentence-transformers (locally)."""
        if self._fallback_model is None:
            try:
                from sentence_transformers import SentenceTransformer

                logger.info("Loading fallback model: %s", FALLBACK_MODEL)
                self._fallback_model = SentenceTransformer(FALLBACK_MODEL)
            except ImportError as exc:
                raise RuntimeError(
                    "sentence-transformers not installed. "
                    "Install with: pip install sentence-transformers"
                ) from exc

        vector = self._fallback_model.encode(text, normalize_embeddings=True)
        return vector.tolist()

    def get_embedding(self, text: str) -> List[float]:
        """
        Generate an embedding vector for the given text.

        Tries Ollama (nomic-embed-text), falls back to sentence-transformers
        if Ollama is not reachable.

        Args:
            text: The text to embed.

        Returns:
            Embedding vector as a list of floats.

        Raises:
            RuntimeError: If neither Ollama nor the fallback is available.
        """
        if not text or not text.strip():
            raise ValueError("Text must not be empty")

        if self._check_ollama():
            try:
                return self._get_ollama_embedding(text)
            except Exception as exc:
                logger.error("Ollama embedding failed: %s — switching to fallback", exc)
                self._ollama_available = False  # Reset cache

        return self._get_fallback_embedding(text)

    def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts.

        Returns:
            List of embedding vectors.
        """
        return [self.get_embedding(text) for text in texts]

    def reset_availability_cache(self) -> None:
        """Reset the Ollama availability cache (useful after tunnel restart)."""
        self._ollama_available = None
