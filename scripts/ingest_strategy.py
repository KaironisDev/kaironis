"""
TCT Strategy Knowledge Base Ingestion Script
=============================================

Ingesteert alle TCT strategy .md bestanden in ChromaDB op de sandbox VPS.

Werking:
1. Opent SSH tunnels: localhost:18000 → sandbox:8000 (ChromaDB)
                      localhost:11434 → sandbox:11434 (Ollama)
2. Test verbindingen met ChromaDB en Ollama
3. Maakt "tct_strategy" collection aan (of gebruikt bestaande)
4. Leest alle .md bestanden uit docs/strategy/ recursief
5. Chunked elk bestand (max 500 tokens, 50 overlap, markdown-aware)
6. Genereert embeddings via Ollama nomic-embed-text
7. Slaat chunks + embeddings + metadata op in ChromaDB
8. Voert 5 validatie queries uit
9. Schrijft ingest_report.md

Gebruik:
    python scripts/ingest_strategy.py [--reset]

    --reset: Verwijder en hermaak de collection voor een frisse start
"""

import argparse
import json
import logging
import os
import sys
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import paramiko
import requests
import chromadb
from chromadb.config import Settings

# ─────────────────────────────────────────────
# Configuratie
# ─────────────────────────────────────────────

WORKSPACE = Path(__file__).parent.parent
DOCS_DIR = WORKSPACE / "docs" / "strategy"
SCRIPTS_DIR = WORKSPACE / "scripts"

SSH_HOST = "72.61.167.71"
SSH_PORT = 2847
SSH_USER = "kaironis"
SSH_KEY = Path(r"C:\Users\Perry\.ssh\kaironis_sandbox")

CHROMA_LOCAL_PORT = 18000   # tunnel: localhost:18000 → sandbox:8000
CHROMA_REMOTE_PORT = 8000

OLLAMA_LOCAL_PORT = 11434   # tunnel: localhost:11434 → sandbox:11434
OLLAMA_REMOTE_PORT = 11434

COLLECTION_NAME = "tct_strategy"
OLLAMA_MODEL = "nomic-embed-text"

MAX_TOKENS = 500
OVERLAP_TOKENS = 50

VALIDATION_QUERIES = [
    "What is a PO3 schematic?",
    "How do I identify supply and demand zones?",
    "What are the session times for London and New York?",
    "What is the risk management rule for position sizing?",
    "How do I trade liquidity sweeps?",
]

# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# SSH Tunnel
# ─────────────────────────────────────────────

class SSHTunnel:
    """Beheert twee SSH port-forwarding tunnels via Paramiko."""

    def __init__(self):
        self.client: Optional[paramiko.SSHClient] = None
        self._threads: List[threading.Thread] = []
        self._stop_event = threading.Event()

    def connect(self):
        logger.info("SSH verbinding openen naar %s:%d …", SSH_HOST, SSH_PORT)
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(
            hostname=SSH_HOST,
            port=SSH_PORT,
            username=SSH_USER,
            key_filename=str(SSH_KEY),
            timeout=15,
        )
        logger.info("SSH verbinding OK ✓")

        # Start tunnels in achtergrond threads
        self._start_tunnel(CHROMA_LOCAL_PORT, "localhost", CHROMA_REMOTE_PORT, "ChromaDB")
        self._start_tunnel(OLLAMA_LOCAL_PORT, "localhost", OLLAMA_REMOTE_PORT, "Ollama")

        # Geef tunnels even tijd om op te starten
        time.sleep(2)

    def _start_tunnel(self, local_port: int, remote_host: str, remote_port: int, name: str):
        """Start een port-forwarding tunnel in een daemon thread."""
        import socket

        transport = self.client.get_transport()

        def forward():
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                server.bind(("127.0.0.1", local_port))
            except OSError as e:
                logger.warning("Poort %d al in gebruik (%s) — probeer bestaande tunnel te gebruiken", local_port, e)
                return

            server.listen(5)
            server.settimeout(1)
            logger.info("Tunnel %s: localhost:%d → %s:%d", name, local_port, remote_host, remote_port)

            while not self._stop_event.is_set():
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    continue
                except Exception:
                    break

                try:
                    channel = transport.open_channel(
                        "direct-tcpip",
                        (remote_host, remote_port),
                        conn.getpeername(),
                    )
                except Exception as e:
                    logger.error("Channel openen mislukt: %s", e)
                    conn.close()
                    continue

                # Bidirectioneel doorsturen
                t = threading.Thread(target=self._forward_data, args=(conn, channel), daemon=True)
                t.start()

            server.close()

        t = threading.Thread(target=forward, daemon=True)
        t.start()
        self._threads.append(t)

    @staticmethod
    def _forward_data(local_conn, remote_channel):
        import select
        import socket

        try:
            while True:
                r, _, _ = select.select([local_conn, remote_channel], [], [], 5)
                if not r:
                    continue
                for s in r:
                    if s is local_conn:
                        data = local_conn.recv(4096)
                        if not data:
                            return
                        remote_channel.send(data)
                    elif s is remote_channel:
                        data = remote_channel.recv(4096)
                        if not data:
                            return
                        local_conn.send(data)
        except Exception:
            pass
        finally:
            try:
                local_conn.close()
            except Exception:
                pass
            try:
                remote_channel.close()
            except Exception:
                pass

    def close(self):
        self._stop_event.set()
        if self.client:
            self.client.close()
        logger.info("SSH tunnel gesloten")


# ─────────────────────────────────────────────
# Chunker (hergebruikt uit src/memory/chunker.py)
# ─────────────────────────────────────────────

# Voeg src aan het pad toe zodat we chunker.py kunnen importeren
sys.path.insert(0, str(WORKSPACE / "src"))
from memory.chunker import chunk_markdown


# ─────────────────────────────────────────────
# Ollama Embeddings
# ─────────────────────────────────────────────

def get_embedding(text: str) -> List[float]:
    """Genereer embedding via Ollama nomic-embed-text (via SSH tunnel)."""
    url = f"http://localhost:{OLLAMA_LOCAL_PORT}/api/embeddings"
    resp = requests.post(
        url,
        json={"model": OLLAMA_MODEL, "prompt": text},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def test_ollama() -> bool:
    """Test of Ollama bereikbaar is."""
    try:
        resp = requests.get(f"http://localhost:{OLLAMA_LOCAL_PORT}/api/tags", timeout=10)
        if resp.status_code == 200:
            models = [m["name"] for m in resp.json().get("models", [])]
            logger.info("Ollama bereikbaar ✓  — modellen: %s", models)
            if not any(OLLAMA_MODEL in m for m in models):
                logger.warning("Model '%s' NIET gevonden in Ollama!", OLLAMA_MODEL)
            return True
    except Exception as e:
        logger.error("Ollama niet bereikbaar: %s", e)
    return False


# ─────────────────────────────────────────────
# ChromaDB
# ─────────────────────────────────────────────

def get_chroma_collection(reset: bool = False):
    """Maak verbinding met ChromaDB en geef de collection terug."""
    client = chromadb.HttpClient(
        host="localhost",
        port=CHROMA_LOCAL_PORT,
        settings=Settings(anonymized_telemetry=False),
    )

    # Test heartbeat
    try:
        hb = client.heartbeat()
        logger.info("ChromaDB bereikbaar ✓  heartbeat=%s", hb)
    except Exception as e:
        logger.error("ChromaDB niet bereikbaar: %s", e)
        raise

    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
            logger.info("Bestaande collection '%s' verwijderd (reset)", COLLECTION_NAME)
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    logger.info("Collection '%s' gereed — %d documenten aanwezig", COLLECTION_NAME, collection.count())
    return collection


# ─────────────────────────────────────────────
# Docs lezen + lecture_type bepalen
# ─────────────────────────────────────────────

def determine_lecture_type(filepath: Path) -> str:
    """Bepaal het type document op basis van het pad."""
    parts = filepath.parts
    if "lectures" in parts:
        return "lecture"
    elif "reviews" in parts:
        return "review"
    elif "reference" in parts:
        return "reference"
    return "other"


def load_strategy_docs() -> List[Dict]:
    """Laad alle .md bestanden uit docs/strategy/ recursief."""
    docs = []
    for md_file in sorted(DOCS_DIR.rglob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
            if not text.strip():
                logger.warning("Leeg bestand overgeslagen: %s", md_file.name)
                continue
            docs.append({
                "path": md_file,
                "text": text,
                "filename": md_file.name,
                "relative_path": str(md_file.relative_to(WORKSPACE)),
                "lecture_type": determine_lecture_type(md_file),
            })
            logger.debug("Geladen: %s (%d tekens)", md_file.name, len(text))
        except Exception as e:
            logger.error("Kan bestand niet lezen: %s — %s", md_file, e)

    logger.info("Totaal %d bestanden geladen uit %s", len(docs), DOCS_DIR)
    return docs


# ─────────────────────────────────────────────
# Ingestie
# ─────────────────────────────────────────────

def ingest_docs(collection, docs: List[Dict]) -> Dict:
    """
    Ingesteer alle documenten in ChromaDB.

    Returns:
        Stats dict met tellingen en eventuele errors.
    """
    stats = {
        "files_processed": 0,
        "files_skipped": 0,
        "chunks_total": 0,
        "chunks_stored": 0,
        "errors": [],
    }

    total_files = len(docs)

    for doc_idx, doc in enumerate(docs, 1):
        filename = doc["filename"]
        logger.info("[%d/%d] Verwerken: %s", doc_idx, total_files, filename)

        try:
            chunks = chunk_markdown(doc["text"], max_tokens=MAX_TOKENS, overlap=OVERLAP_TOKENS)
            if not chunks:
                logger.warning("Geen chunks gegenereerd voor %s", filename)
                stats["files_skipped"] += 1
                continue

            total_chunks = len(chunks)
            logger.info("  → %d chunks gegenereerd", total_chunks)

            ids = []
            embeddings = []
            metadatas = []
            texts = []

            for chunk_idx, chunk_text in enumerate(chunks):
                if not chunk_text.strip():
                    continue

                # Skip header-only chunks: kort (<150 tekens) én geen zin (geen punt/komma/dubbele punt)
                if chunk_idx == 0 and len(chunk_text) < 150 and not any(c in chunk_text for c in (".", ",", ":")):
                    logger.debug(
                        "Chunk 0 van %s overgeslagen (header/bestandsnaam detectie, %d tekens)",
                        filename, len(chunk_text),
                    )
                    continue

                try:
                    embedding = get_embedding(chunk_text)
                except Exception as e:
                    err_msg = f"Embedding mislukt voor {filename} chunk {chunk_idx}: {e}"
                    logger.error(err_msg)
                    stats["errors"].append(err_msg)
                    continue

                doc_id = f"{filename}__chunk_{chunk_idx:04d}"
                ids.append(doc_id)
                embeddings.append(embedding)
                texts.append(chunk_text)
                metadatas.append({
                    "source_file": doc["relative_path"],
                    "filename": filename,
                    "lecture_type": doc["lecture_type"],
                    "chunk_index": chunk_idx,
                    "total_chunks": total_chunks,
                })

                stats["chunks_total"] += 1

            if ids:
                # Batch toevoegen (vervangt als ID al bestaat)
                try:
                    collection.upsert(
                        ids=ids,
                        embeddings=embeddings,
                        documents=texts,
                        metadatas=metadatas,
                    )
                    stats["chunks_stored"] += len(ids)
                    logger.info("  → %d chunks opgeslagen ✓", len(ids))
                except Exception as e:
                    err_msg = f"ChromaDB upsert mislukt voor {filename}: {e}"
                    logger.error(err_msg)
                    stats["errors"].append(err_msg)

            stats["files_processed"] += 1

        except Exception as e:
            err_msg = f"Fout bij verwerken van {filename}: {e}"
            logger.error(err_msg)
            stats["errors"].append(err_msg)
            stats["files_skipped"] += 1

    logger.info(
        "Ingestie compleet: %d bestanden, %d chunks opgeslagen",
        stats["files_processed"],
        stats["chunks_stored"],
    )
    return stats


# ─────────────────────────────────────────────
# Validatie queries
# ─────────────────────────────────────────────

def run_validation_queries(collection) -> List[Dict]:
    """Voer validatie queries uit en geef resultaten terug."""
    results = []

    for query in VALIDATION_QUERIES:
        logger.info("Query: '%s'", query)

        try:
            query_embedding = get_embedding(query)

            raw = collection.query(
                query_embeddings=[query_embedding],
                n_results=3,
                include=["documents", "metadatas", "distances"],
            )

            hits = []
            ids = raw.get("ids", [[]])[0]
            docs = raw.get("documents", [[]])[0]
            metas = raw.get("metadatas", [[]])[0]
            distances = raw.get("distances", [[]])[0]

            for i, (doc_id, doc, meta, dist) in enumerate(zip(ids, docs, metas, distances)):
                # Cosine distance → similarity score
                score = 1 - dist
                snippet = doc[:200].replace("\n", " ") + ("…" if len(doc) > 200 else "")
                hits.append({
                    "rank": i + 1,
                    "id": doc_id,
                    "source": meta.get("filename", "?"),
                    "lecture_type": meta.get("lecture_type", "?"),
                    "score": round(score, 4),
                    "snippet": snippet,
                })
                logger.info(
                    "  [%d] %.4f  %s  — %s",
                    i + 1,
                    score,
                    meta.get("filename", "?"),
                    snippet[:80],
                )

            results.append({"query": query, "hits": hits})

        except Exception as e:
            logger.error("Query mislukt: %s — %s", query, e)
            results.append({"query": query, "hits": [], "error": str(e)})

    return results


# ─────────────────────────────────────────────
# Rapportage
# ─────────────────────────────────────────────

def write_report(stats: Dict, query_results: List[Dict], collection_count: int):
    """Schrijf het ingest rapport naar docs/strategy/ingest_report.md."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    report_path = DOCS_DIR / "ingest_report.md"

    lines = [
        f"# TCT Strategy Knowledge Base — Ingest Report",
        f"",
        f"**Datum:** {now}  ",
        f"**Model:** {OLLAMA_MODEL}  ",
        f"**Collection:** {COLLECTION_NAME}  ",
        f"",
        f"---",
        f"",
        f"## Statistieken",
        f"",
        f"| Metric | Waarde |",
        f"|--------|--------|",
        f"| Bestanden verwerkt | {stats['files_processed']} |",
        f"| Bestanden overgeslagen | {stats['files_skipped']} |",
        f"| Chunks gegenereerd | {stats['chunks_total']} |",
        f"| Chunks opgeslagen in ChromaDB | {stats['chunks_stored']} |",
        f"| Totaal docs in collection | {collection_count} |",
        f"| Errors | {len(stats['errors'])} |",
        f"",
    ]

    if stats["errors"]:
        lines += [
            f"## Errors",
            f"",
        ]
        for err in stats["errors"]:
            lines.append(f"- {err}")
        lines.append("")

    lines += [
        f"---",
        f"",
        f"## Validatie Query Resultaten",
        f"",
    ]

    for qr in query_results:
        lines += [
            f"### Query: \"{qr['query']}\"",
            f"",
        ]
        if "error" in qr:
            lines.append(f"❌ Error: {qr['error']}")
        elif not qr["hits"]:
            lines.append("Geen resultaten gevonden.")
        else:
            for hit in qr["hits"]:
                lines += [
                    f"**#{hit['rank']}** — `{hit['source']}` ({hit['lecture_type']}) — score: {hit['score']}",
                    f"> {hit['snippet']}",
                    f"",
                ]
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Rapport geschreven naar %s", report_path)
    return report_path


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ingesteer TCT strategy docs in ChromaDB")
    parser.add_argument("--reset", action="store_true", help="Verwijder en hermaak de ChromaDB collection")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("TCT Strategy Ingestie")
    logger.info("=" * 60)

    tunnel = SSHTunnel()
    try:
        # Stap 1: SSH tunnel openen
        tunnel.connect()

        # Stap 2: Verbindingen testen
        if not test_ollama():
            logger.error("Ollama niet bereikbaar — abort")
            sys.exit(1)

        collection = get_chroma_collection(reset=args.reset)

        # Stap 3: Docs laden
        docs = load_strategy_docs()
        if not docs:
            logger.error("Geen documenten gevonden in %s", DOCS_DIR)
            sys.exit(1)

        # Stap 4: Ingesteren
        start_time = time.time()
        stats = ingest_docs(collection, docs)
        elapsed = time.time() - start_time
        logger.info("Ingestie duurde %.1f seconden", elapsed)

        # Stap 5: Validatie queries
        logger.info("")
        logger.info("=" * 60)
        logger.info("Validatie queries")
        logger.info("=" * 60)
        query_results = run_validation_queries(collection)

        # Stap 6: Rapport
        collection_count = collection.count()
        report_path = write_report(stats, query_results, collection_count)

        logger.info("")
        logger.info("=" * 60)
        logger.info("SAMENVATTING")
        logger.info("=" * 60)
        logger.info("Bestanden verwerkt : %d", stats["files_processed"])
        logger.info("Chunks opgeslagen  : %d", stats["chunks_stored"])
        logger.info("Docs in collection : %d", collection_count)
        logger.info("Errors             : %d", len(stats["errors"]))
        logger.info("Rapport            : %s", report_path)

    finally:
        tunnel.close()


if __name__ == "__main__":
    main()
