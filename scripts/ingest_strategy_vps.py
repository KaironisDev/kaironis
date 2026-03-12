"""
TCT Strategy Knowledge Base Ingestion Script (VPS Edition)
==========================================================

Draait DIRECT op de sandbox VPS — geen SSH tunnels nodig.
ChromaDB op localhost:8000, Ollama op Docker netwerk IP.

Gebruik:
    python3 scripts/ingest_strategy_vps.py [--reset]
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests
import chromadb
from chromadb.config import Settings

# ─────────────────────────────────────────────
# Configuratie
# ─────────────────────────────────────────────

WORKSPACE = Path(__file__).parent.parent
DOCS_DIR = WORKSPACE / "docs" / "strategy"

# ChromaDB: direct op localhost:8000 (Docker poort exposed)
CHROMA_HOST = "localhost"
CHROMA_PORT = 8000

# Ollama: niet direct exposed op host, bereikbaar via Docker network
# We detecteren het IP automatisch
def get_ollama_url() -> str:
    """Detecteer Ollama URL: probeer localhost:11434 first, dan Docker network."""
    # Probeer localhost:11434
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        if r.status_code == 200:
            return "http://localhost:11434"
    except Exception:
        pass

    # Probeer Docker network IP via inspect
    try:
        result = subprocess.run(
            ["docker", "inspect", "ollama", "--format", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}"],
            capture_output=True, text=True, timeout=10
        )
        ip = result.stdout.strip()
        if ip:
            url = f"http://{ip}:11434"
            r = requests.get(f"{url}/api/tags", timeout=5)
            if r.status_code == 200:
                return url
    except Exception:
        pass

    # Fallback: hardcoded Docker network range
    for ip in ["172.19.0.2", "172.17.0.2", "172.18.0.2"]:
        try:
            url = f"http://{ip}:11434"
            r = requests.get(f"{url}/api/tags", timeout=3)
            if r.status_code == 200:
                return url
        except Exception:
            continue

    raise RuntimeError("Ollama niet bereikbaar op localhost:11434 of Docker network")


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
# Imports van memory module
# ─────────────────────────────────────────────

sys.path.insert(0, str(WORKSPACE / "src"))
from memory.chunker import chunk_markdown

# ─────────────────────────────────────────────
# Ollama
# ─────────────────────────────────────────────

OLLAMA_BASE_URL = None  # wordt ingesteld in main()

def get_embedding(text: str) -> List[float]:
    """Genereer embedding via Ollama nomic-embed-text."""
    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/embeddings",
        json={"model": OLLAMA_MODEL, "prompt": text},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


# ─────────────────────────────────────────────
# ChromaDB
# ─────────────────────────────────────────────

def get_chroma_collection(reset: bool = False):
    """Verbind met ChromaDB en geef collection terug."""
    client = chromadb.HttpClient(
        host=CHROMA_HOST,
        port=CHROMA_PORT,
        settings=Settings(anonymized_telemetry=False),
    )

    try:
        hb = client.heartbeat()
        logger.info("ChromaDB bereikbaar ✓  heartbeat=%s", hb)
    except Exception as e:
        logger.error("ChromaDB niet bereikbaar: %s", e)
        raise

    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
            logger.info("Collection '%s' verwijderd (reset)", COLLECTION_NAME)
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    logger.info("Collection '%s' gereed — %d docs aanwezig", COLLECTION_NAME, collection.count())
    return collection


# ─────────────────────────────────────────────
# Docs laden
# ─────────────────────────────────────────────

def determine_lecture_type(filepath: Path) -> str:
    parts = filepath.parts
    if "lectures" in parts:
        return "lecture"
    elif "reviews" in parts:
        return "review"
    elif "reference" in parts:
        return "reference"
    return "other"


def load_strategy_docs() -> List[Dict]:
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
        except Exception as e:
            logger.error("Kan niet lezen: %s — %s", md_file, e)

    logger.info("Totaal %d bestanden geladen uit %s", len(docs), DOCS_DIR)
    return docs


# ─────────────────────────────────────────────
# Ingestie
# ─────────────────────────────────────────────

def ingest_docs(collection, docs: List[Dict]) -> Dict:
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
                logger.warning("Geen chunks voor %s", filename)
                stats["files_skipped"] += 1
                continue

            total_chunks = len(chunks)
            logger.info("  → %d chunks", total_chunks)

            ids = []
            embeddings_list = []
            metadatas = []
            texts = []

            for chunk_idx, chunk_text in enumerate(chunks):
                if not chunk_text.strip():
                    continue

                try:
                    embedding = get_embedding(chunk_text)
                except Exception as e:
                    err = f"Embedding mislukt {filename}[{chunk_idx}]: {e}"
                    logger.error(err)
                    stats["errors"].append(err)
                    continue

                doc_id = f"{filename}__chunk_{chunk_idx:04d}"
                ids.append(doc_id)
                embeddings_list.append(embedding)
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
                try:
                    collection.upsert(
                        ids=ids,
                        embeddings=embeddings_list,
                        documents=texts,
                        metadatas=metadatas,
                    )
                    stats["chunks_stored"] += len(ids)
                    logger.info("  → %d chunks opgeslagen ✓", len(ids))
                except Exception as e:
                    err = f"Upsert mislukt {filename}: {e}"
                    logger.error(err)
                    stats["errors"].append(err)

            stats["files_processed"] += 1

        except Exception as e:
            err = f"Fout bij {filename}: {e}"
            logger.error(err)
            stats["errors"].append(err)
            stats["files_skipped"] += 1

    return stats


# ─────────────────────────────────────────────
# Validatie
# ─────────────────────────────────────────────

def run_validation_queries(collection) -> List[Dict]:
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
                score = 1 - dist
                snippet = doc[:300].replace("\n", " ")
                if len(doc) > 300:
                    snippet += "…"
                hits.append({
                    "rank": i + 1,
                    "id": doc_id,
                    "source": meta.get("filename", "?"),
                    "lecture_type": meta.get("lecture_type", "?"),
                    "score": round(score, 4),
                    "snippet": snippet,
                })
                logger.info("  [%d] %.4f  %s", i + 1, score, meta.get("filename", "?"))

            results.append({"query": query, "hits": hits})

        except Exception as e:
            logger.error("Query mislukt '%s': %s", query, e)
            results.append({"query": query, "hits": [], "error": str(e)})

    return results


# ─────────────────────────────────────────────
# Rapport
# ─────────────────────────────────────────────

def write_report(stats: Dict, query_results: List[Dict], collection_count: int, ollama_url: str) -> Path:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    report_path = DOCS_DIR / "ingest_report.md"

    lines = [
        "# TCT Strategy Knowledge Base — Ingest Report",
        "",
        f"**Datum:** {now}  ",
        f"**Model:** {OLLAMA_MODEL}  ",
        f"**Ollama URL:** {ollama_url}  ",
        f"**Collection:** {COLLECTION_NAME}  ",
        "",
        "---",
        "",
        "## Statistieken",
        "",
        "| Metric | Waarde |",
        "|--------|--------|",
        f"| Bestanden verwerkt | {stats['files_processed']} |",
        f"| Bestanden overgeslagen | {stats['files_skipped']} |",
        f"| Chunks gegenereerd | {stats['chunks_total']} |",
        f"| Chunks opgeslagen in ChromaDB | {stats['chunks_stored']} |",
        f"| Totaal docs in collection | {collection_count} |",
        f"| Errors | {len(stats['errors'])} |",
        "",
    ]

    if stats["errors"]:
        lines += ["## Errors", ""]
        for err in stats["errors"]:
            lines.append(f"- {err}")
        lines.append("")

    lines += ["---", "", "## Validatie Query Resultaten", ""]

    for qr in query_results:
        lines += [f"### Query: \"{qr['query']}\"", ""]
        if "error" in qr:
            lines.append(f"❌ Error: {qr['error']}")
        elif not qr["hits"]:
            lines.append("Geen resultaten gevonden.")
        else:
            for hit in qr["hits"]:
                lines += [
                    f"**#{hit['rank']}** — `{hit['source']}` ({hit['lecture_type']}) — score: {hit['score']}",
                    f"> {hit['snippet']}",
                    "",
                ]
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Rapport geschreven: %s", report_path)
    return report_path


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    global OLLAMA_BASE_URL

    parser = argparse.ArgumentParser(description="Ingesteer TCT strategy docs in ChromaDB (VPS)")
    parser.add_argument("--reset", action="store_true", help="Reset de ChromaDB collection")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("TCT Strategy Ingestie (VPS)")
    logger.info("=" * 60)

    # Detecteer Ollama URL
    logger.info("Ollama URL detecteren…")
    OLLAMA_BASE_URL = get_ollama_url()
    logger.info("Ollama gevonden: %s ✓", OLLAMA_BASE_URL)

    # Test embedding
    logger.info("Embedding test…")
    test_emb = get_embedding("test")
    logger.info("Embedding dimensie: %d ✓", len(test_emb))

    # ChromaDB
    collection = get_chroma_collection(reset=args.reset)

    # Docs laden
    docs = load_strategy_docs()
    if not docs:
        logger.error("Geen docs gevonden in %s", DOCS_DIR)
        sys.exit(1)

    # Ingesteren
    t0 = time.time()
    stats = ingest_docs(collection, docs)
    elapsed = time.time() - t0
    logger.info("Ingestie klaar in %.1fs", elapsed)

    # Validatie
    logger.info("")
    logger.info("=" * 60)
    logger.info("Validatie queries")
    logger.info("=" * 60)
    query_results = run_validation_queries(collection)

    # Rapport
    collection_count = collection.count()
    report_path = write_report(stats, query_results, collection_count, OLLAMA_BASE_URL)

    # Output als JSON voor makkelijk parsen
    summary = {
        "files_processed": stats["files_processed"],
        "chunks_stored": stats["chunks_stored"],
        "collection_count": collection_count,
        "errors": len(stats["errors"]),
        "elapsed_seconds": round(elapsed, 1),
        "report": str(report_path),
    }
    print("\n" + "=" * 60)
    print("SAMENVATTING JSON:")
    print(json.dumps(summary, indent=2))

    # Print query resultaten ook als JSON
    print("\nQUERY RESULTATEN JSON:")
    print(json.dumps(query_results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
