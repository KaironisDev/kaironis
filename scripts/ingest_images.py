"""
TCT Strategy Image Ingestion Script
====================================

Converteert PDF pagina's naar afbeeldingen, beschrijft ze via Gemini Vision
(OpenRouter), en slaat de beschrijvingen op in ChromaDB naast tekst chunks.

Werking:
1. Scant DOCS_DIR recursief voor .pdf bestanden
2. Per pagina: converteert naar PNG (in-memory, geen bestanden op schijf)
3. Beschrijft visuele content via Gemini Vision API (OpenRouter)
4. Genereert embeddings via Ollama nomic-embed-text
5. Slaat op in ChromaDB collection "tct_strategy" (zelfde als tekst)
6. Slaat rapport op als docs/strategy/image_ingest_report.md

Gebruik:
    python scripts/ingest_images.py

Environment variabelen:
    OPENROUTER_API_KEY   - Verplicht voor Gemini Vision calls
    OPENROUTER_MODEL     - Standaard: google/gemini-2.0-flash-001
    CHROMADB_HOST        - Standaard: localhost
    CHROMADB_PORT        - Standaard: 8000
    OLLAMA_HOST          - Standaard: localhost
    OLLAMA_PORT          - Standaard: 11434
    DOCS_DIR             - Standaard: docs/strategy

Idempotent: pagina's die al ingeësteerd zijn worden overgeslagen.
"""

import base64
import io
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import requests
import chromadb
from chromadb.config import Settings

# ─────────────────────────────────────────────
# Configuratie
# ─────────────────────────────────────────────

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")
CHROMADB_HOST = os.getenv("CHROMADB_HOST", "localhost")
CHROMADB_PORT = int(os.getenv("CHROMADB_PORT", "8000"))
# OLLAMA_HOST may be a full URL like "http://ollama:11434" — strip the scheme and port.
_raw_ollama_host = os.getenv("OLLAMA_HOST", "localhost")
OLLAMA_HOST = _raw_ollama_host.replace("http://", "").replace("https://", "").split(":")[0]
OLLAMA_PORT = (
    int(_raw_ollama_host.replace("http://", "").replace("https://", "").split(":")[-1])
    if ":" in _raw_ollama_host
    else int(os.getenv("OLLAMA_PORT", "11434"))
)
DOCS_DIR = Path(os.getenv("DOCS_DIR", "docs/strategy"))
IMAGE_COLLECTION = "tct_strategy"  # same collection as text chunks
DPI = 150  # lower than 300 for speed, still readable

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OLLAMA_URL = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/embeddings"

EXCLUDE_FILES = {"ingest_report.md"}

# Vision prompt template — {page_num} en {filename} worden ingevuld
VISION_PROMPT_TEMPLATE = (
    "Je analyseert pagina {page_num} van het TCT (Time-Cycle Trading) "
    "strategie document '{filename}'.\n\n"
    "Beschrijf alle visuele elementen in detail:\n"
    "- Prijsgrafieken: structuur, zones, labels, pijlen, patronen "
    "(PO3, BOS, ranges, supply/demand)\n"
    "- Schema's en diagrammen: beschrijf de structuur en wat het toont\n"
    "- Tekst in afbeeldingen: titels, annotaties, nummers, legendas\n"
    "- Lege pagina's of pagina's met alleen tekst: geef aan "
    "\"Geen visuele trading content\"\n\n"
    "Gebruik TCT terminologie. Wees specifiek en gedetailleerd.\n"
    "Taal: Nederlands. Maximum 800 woorden."
)

# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Functies
# ─────────────────────────────────────────────


def pdf_to_images(pdf_path: Path, dpi: int = DPI) -> List[Tuple[int, bytes]]:
    """
    Converteert een PDF naar een lijst van (page_number, png_bytes) tuples.

    Werkt volledig in-memory — slaat geen bestanden op schijf op.
    Page numbers zijn 1-gebaseerd.

    Args:
        pdf_path: Pad naar het PDF bestand
        dpi: Resolutie voor de conversie (standaard 150)

    Returns:
        Lijst van (page_number, png_bytes) tuples
    """
    from pdf2image import convert_from_path

    log.info(f"Converteer {pdf_path.name} naar afbeeldingen (DPI={dpi})...")
    pages = convert_from_path(str(pdf_path), dpi=dpi, fmt="png")

    results = []
    for i, page in enumerate(pages, start=1):
        buf = io.BytesIO()
        page.save(buf, format="PNG")
        png_bytes = buf.getvalue()
        results.append((i, png_bytes))

    log.info(f"  → {len(results)} pagina's geconverteerd")
    return results


def describe_image(image_bytes: bytes, filename: str, page_num: int) -> Optional[str]:
    """
    Beschrijft een afbeelding via Gemini Vision (OpenRouter).

    Args:
        image_bytes: PNG bytes van de pagina
        filename: Naam van het bronbestand (voor prompt context)
        page_num: Paginanummer (voor prompt context)

    Returns:
        Beschrijving van de visuele content, of None als er geen
        visuele trading content is (response < 50 tekens).
    """
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is niet ingesteld")

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    vision_prompt = VISION_PROMPT_TEMPLATE.format(
        page_num=page_num, filename=filename
    )

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                    {"type": "text", "text": vision_prompt},
                ],
            }
        ],
        "max_tokens": 1000,
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/KaironisDev/kaironis",
        "X-Title": "Kaironis TCT Image Ingestion",
    }

    response = requests.post(
        OPENROUTER_URL,
        headers=headers,
        json=payload,
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()
    description = data["choices"][0]["message"]["content"].strip()

    if len(description) < 50:
        log.debug(f"  Pagina {page_num}: te kort ({len(description)} tekens) → overgeslagen")
        return None

    return description


def get_ollama_embedding(text: str) -> List[float]:
    """
    Genereert een embedding vector via Ollama nomic-embed-text.

    Args:
        text: De tekst om te embedden

    Returns:
        Embedding vector als lijst van floats
    """
    payload = {
        "model": "nomic-embed-text",
        "prompt": text,
    }

    response = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()
    return data["embedding"]


def ingest_page(
    collection,
    description: str,
    metadata: dict,
) -> None:
    """
    Adds a description of a PDF page to ChromaDB.

    ID format: {rel_path}::img::{page_num}
    Uses the relative path within DOCS_DIR to avoid doc_id collisions
    when files with the same name exist in different subdirectories.
    Metadata contains: filename, page_number, source_type="image", lecture_type

    Args:
        collection: ChromaDB collection object
        description: Description of the visual content
        metadata: Dict with filename, page_number, lecture_type, and rel_path
    """
    rel_path = metadata.get("rel_path", metadata["filename"])
    page_num = metadata["page_number"]
    doc_id = f"{rel_path}::img::{page_num}"

    embedding = get_ollama_embedding(description)

    # Zorg dat source_type altijd "image" is
    full_metadata = {
        **metadata,
        "source_type": "image",
    }

    collection.add(
        ids=[doc_id],
        documents=[description],
        embeddings=[embedding],
        metadatas=[full_metadata],
    )

    log.debug(f"  Opgeslagen: {doc_id}")


def _get_existing_ids(collection) -> set:
    """Haal alle bestaande IDs op uit de collection."""
    try:
        result = collection.get(include=[])
        return set(result["ids"])
    except Exception as e:
        log.warning(f"Kon bestaande IDs niet ophalen: {e}")
        return set()


def _detect_lecture_type(pdf_path: Path) -> str:
    """
    Detecteer het type lecture op basis van het pad.
    Zelfde logica als in ingest_strategy.py voor consistentie.
    """
    parts = pdf_path.parts
    for part in parts:
        part_lower = part.lower()
        if "lecture" in part_lower:
            return part
        if "review" in part_lower:
            return "review"
        if "reference" in part_lower:
            return "reference"
    return "unknown"


def main() -> None:
    """
    Hoofdfunctie: scant DOCS_DIR voor PDFs en ingesteert alle pagina's.

    - Idempotent: pagina's die al in ChromaDB staan worden overgeslagen
    - Rate limiting: 0.5s sleep tussen Gemini calls
    - Rapportage: schrijft image_ingest_report.md
    """
    if not OPENROUTER_API_KEY:
        log.error("OPENROUTER_API_KEY is niet ingesteld. Stop.")
        sys.exit(1)

    log.info("=== TCT Strategy Image Ingestion ===")
    log.info(f"DOCS_DIR: {DOCS_DIR}")
    log.info(f"Model: {OPENROUTER_MODEL}")
    log.info(f"ChromaDB: {CHROMADB_HOST}:{CHROMADB_PORT}")
    log.info(f"Ollama: {OLLAMA_HOST}:{OLLAMA_PORT}")

    # ── ChromaDB verbinding ──────────────────
    log.info("Verbinding maken met ChromaDB...")
    client = chromadb.HttpClient(
        host=CHROMADB_HOST,
        port=CHROMADB_PORT,
        settings=Settings(anonymized_telemetry=False),
    )

    try:
        client.heartbeat()
        log.info("  ✓ ChromaDB bereikbaar")
    except Exception as e:
        log.error(f"ChromaDB niet bereikbaar: {e}")
        sys.exit(1)

    # ── Collection ophalen of aanmaken ───────
    collection = client.get_or_create_collection(
        name=IMAGE_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )
    log.info(f"  Collection '{IMAGE_COLLECTION}' heeft {collection.count()} items")

    existing_ids = _get_existing_ids(collection)
    log.info(f"  {len(existing_ids)} bestaande items in collection")

    # ── PDF bestanden zoeken ─────────────────
    docs_path = Path(DOCS_DIR)
    if not docs_path.exists():
        log.error(f"DOCS_DIR bestaat niet: {docs_path}")
        sys.exit(1)

    pdf_files = [
        p for p in docs_path.rglob("*.pdf")
        if p.name not in EXCLUDE_FILES
    ]
    log.info(f"  {len(pdf_files)} PDF bestanden gevonden")

    # ── Statistieken ─────────────────────────
    stats = {
        "bestanden_verwerkt": 0,
        "paginas_verwerkt": 0,
        "paginas_overgeslagen_duplicate": 0,
        "paginas_overgeslagen_geen_content": 0,
        "errors": 0,
        "error_details": [],
    }

    start_time = datetime.now()

    # ── Per PDF ──────────────────────────────
    for pdf_path in sorted(pdf_files):
        log.info(f"\nVerwerk: {pdf_path.relative_to(docs_path)}")
        filename = pdf_path.name
        lecture_type = _detect_lecture_type(pdf_path)

        try:
            pages = pdf_to_images(pdf_path, dpi=DPI)
        except Exception as e:
            log.error(f"  Fout bij PDF conversie: {e}")
            stats["errors"] += 1
            stats["error_details"].append(f"{filename}: PDF conversie mislukt: {e}")
            continue

        stats["bestanden_verwerkt"] += 1

        # Use relative path within DOCS_DIR to avoid doc_id collisions
        rel_path = str(pdf_path.relative_to(docs_path)).replace("\\", "/")

        for page_num, png_bytes in pages:
            doc_id = f"{rel_path}::img::{page_num}"

            # Duplicate check
            if doc_id in existing_ids:
                log.debug(f"  Page {page_num}: already ingested → skip")
                stats["paginas_overgeslagen_duplicate"] += 1
                continue

            # Rate limiting
            time.sleep(0.5)

            # Describe via Gemini
            try:
                description = describe_image(png_bytes, filename, page_num)
            except Exception as e:
                log.error(f"  Page {page_num}: Gemini error: {e}")
                stats["errors"] += 1
                stats["error_details"].append(
                    f"{filename} page {page_num}: Gemini error: {e}"
                )
                continue

            if description is None:
                log.info(f"  Page {page_num}: no visual content → skipped")
                stats["paginas_overgeslagen_geen_content"] += 1
                continue

            # Ingest into ChromaDB
            try:
                metadata = {
                    "filename": filename,
                    "rel_path": rel_path,
                    "page_number": page_num,
                    "lecture_type": lecture_type,
                }
                ingest_page(collection, description, metadata)
                existing_ids.add(doc_id)
                stats["paginas_verwerkt"] += 1
                log.info(
                    f"  ✓ Page {page_num}: ingested "
                    f"({len(description)} chars)"
                )
            except Exception as e:
                log.error(f"  Page {page_num}: ChromaDB error: {e}")
                stats["errors"] += 1
                stats["error_details"].append(
                    f"{filename} page {page_num}: ChromaDB error: {e}"
                )

    # ── Rapport ──────────────────────────────
    duration = (datetime.now() - start_time).total_seconds()

    log.info("\n=== Rapportage ===")
    log.info(f"Bestanden verwerkt:          {stats['bestanden_verwerkt']}")
    log.info(f"Pagina's ingeësteerd:        {stats['paginas_verwerkt']}")
    log.info(f"Pagina's overgeslagen (dup): {stats['paginas_overgeslagen_duplicate']}")
    log.info(f"Pagina's overgeslagen (leeg):{stats['paginas_overgeslagen_geen_content']}")
    log.info(f"Errors:                      {stats['errors']}")
    log.info(f"Tijd:                        {duration:.1f}s")

    report_lines = [
        "# Image Ingest Report",
        f"\nGegenereerd: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"\n## Samenvatting",
        f"- Bestanden verwerkt: {stats['bestanden_verwerkt']}",
        f"- Pagina's ingeësteerd: {stats['paginas_verwerkt']}",
        f"- Pagina's overgeslagen (al aanwezig): {stats['paginas_overgeslagen_duplicate']}",
        f"- Pagina's overgeslagen (geen visuele content): {stats['paginas_overgeslagen_geen_content']}",
        f"- Errors: {stats['errors']}",
        f"- Totale tijd: {duration:.1f}s",
        f"- Model: {OPENROUTER_MODEL}",
    ]

    if stats["error_details"]:
        report_lines.append("\n## Errors")
        for detail in stats["error_details"]:
            report_lines.append(f"- {detail}")

    report_path = docs_path / "image_ingest_report.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    log.info(f"\nRapport opgeslagen: {report_path}")


if __name__ == "__main__":
    main()
