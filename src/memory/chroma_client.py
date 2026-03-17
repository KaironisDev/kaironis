"""
ChromaDB client wrapper voor Kaironis memory module.

Verbinding via SSH tunnel: localhost:8001 → sandbox:8000
Collection: "tct_strategy"

Configuratie via environment variables:
  CHROMADB_HOST  - host van ChromaDB (default: localhost)
  CHROMADB_PORT  - port van ChromaDB (default: 8001 via SSH tunnel)
"""

import os
import logging
import uuid
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)

CHROMADB_HOST = os.getenv("CHROMADB_HOST", "localhost")
CHROMADB_PORT = int(os.getenv("CHROMADB_PORT", "8001"))
COLLECTION_NAME = os.getenv("CHROMADB_COLLECTION", "tct_strategy")


class ChromaClient:
    """
    Wrapper rond de ChromaDB HTTP client.

    Beheert de "tct_strategy" collection en biedt eenvoudige
    methodes voor opslaan, zoeken en verwijderen van documenten.

    Example::

        client = ChromaClient()
        client.add_documents(
            texts=["Supply zone op H4 niveau", "Liquiditeit boven swing high"],
            metadatas=[{"source": "lecture_3.md"}, {"source": "lecture_4.md"}],
        )
        results = client.query("supply zone", n_results=3)
    """

    def __init__(
        self,
        host: str = CHROMADB_HOST,
        port: int = CHROMADB_PORT,
        collection_name: str = COLLECTION_NAME,
    ) -> None:
        self.host = host
        self.port = port
        self.collection_name = collection_name
        self._client: Optional[chromadb.HttpClient] = None
        self._collection: Optional[Any] = None

    def _get_client(self) -> chromadb.HttpClient:
        """Lazy initialisatie van de ChromaDB client."""
        if self._client is None:
            logger.info("Verbinding met ChromaDB op %s:%d", self.host, self.port)
            self._client = chromadb.HttpClient(
                host=self.host,
                port=self.port,
                settings=Settings(anonymized_telemetry=False),
            )
        return self._client

    def _get_collection(self) -> Any:
        """Haal de collection op, maak hem aan als hij niet bestaat."""
        if self._collection is None:
            client = self._get_client()
            self._collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("Collection '%s' gereed", self.collection_name)
        return self._collection

    def add_documents(
        self,
        texts: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Voeg documenten toe aan de collection.

        Args:
            texts: Lijst van document teksten.
            embeddings: Corresponderende embedding vectors.
            metadatas: Optionele metadata dicts per document.
            ids: Optionele unieke IDs (worden gegenereerd als None).

        Returns:
            Lijst van document IDs.

        Raises:
            ValueError: Als texts en embeddings niet dezelfde lengte hebben.
        """
        if len(texts) != len(embeddings):
            raise ValueError(
                f"Aantal teksten ({len(texts)}) moet gelijk zijn aan "
                f"aantal embeddings ({len(embeddings)})"
            )

        if ids is None:
            ids = [str(uuid.uuid4()) for _ in texts]

        if metadatas is None:
            metadatas = [{} for _ in texts]

        collection = self._get_collection()
        collection.add(
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids,
        )

        logger.info("%d documenten toegevoegd aan '%s'", len(texts), self.collection_name)
        return ids

    def query(
        self,
        query_embedding: List[float],
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Zoek semantisch in de collection.

        Args:
            query_embedding: De embedding vector van de zoekopdracht.
            n_results: Maximum aantal resultaten (default: 5).
            where: Optioneel metadata filter (ChromaDB where-clause).

        Returns:
            Lijst van dicts met keys: id, document, metadata, distance.
        """
        collection = self._get_collection()

        kwargs: Dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = collection.query(**kwargs)

        # Zet ChromaDB output om naar lijst van dicts
        output: List[Dict[str, Any]] = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for doc_id, doc, meta, dist in zip(ids, docs, metas, distances):
            output.append({
                "id": doc_id,
                "document": doc,
                "metadata": meta or {},
                "distance": dist,
            })

        return output

    def delete(
        self,
        ids: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Verwijder documenten uit de collection.

        Args:
            ids: Lijst van document IDs om te verwijderen.
            where: Metadata filter — verwijdert alle matching documenten.

        Raises:
            ValueError: Als noch ids noch where opgegeven zijn.
        """
        if not ids and not where:
            raise ValueError("Geef ids of where op om documenten te verwijderen")

        collection = self._get_collection()

        if ids:
            collection.delete(ids=ids)
            logger.info("%d documenten verwijderd uit '%s'", len(ids), self.collection_name)

        if where:
            collection.delete(where=where)
            logger.info("Documenten met filter %s verwijderd uit '%s'", where, self.collection_name)

    def count(self) -> int:
        """Geeft het aantal documenten in de collection terug."""
        collection = self._get_collection()
        return collection.count()

    def collection_exists(self) -> bool:
        """Controleer of de collection bestaat en bereikbaar is."""
        try:
            self._get_collection()
            return True
        except Exception:
            return False

    def reset_collection(self) -> None:
        """
        Verwijder en hermaak de collection (destructief!).

        Gebruik alleen voor development/testing.
        """
        client = self._get_client()
        try:
            client.delete_collection(self.collection_name)
            logger.warning("Collection '%s' verwijderd", self.collection_name)
        except Exception:
            pass
        self._collection = None
        self._get_collection()
        logger.info("Collection '%s' opnieuw aangemaakt", self.collection_name)
