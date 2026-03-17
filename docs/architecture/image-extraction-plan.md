# Image Extraction Plan — TCT PDF Vision

**Doel:** Visuele content uit TCT PDFs extracten en opslaan in ChromaDB
zodat Kaironis ook schema's, grafieken en diagrammen kan raadplegen.

**Waarom:** PO3 schematics, supply/demand zone tekeningen en cycle
diagrammen zitten grotendeels in afbeeldingen — niet in tekst.

---

## Aanpak

### Stap 1: PDF → Afbeeldingen
- Tool: `pdf2image` (poppler backend)
- Elke pagina → PNG (300 DPI voor leesbaarheid)
- Output: `docs/strategy/images/{doc_name}/page_{n}.png`

### Stap 2: Afbeelding → Beschrijving (Gemini Vision)
- Model: `google/gemini-2.0-flash-001` via OpenRouter
- Prompt per afbeelding:
```
Je analyseert een pagina uit een TCT (Time-Cycle Trading) strategie document.
Beschrijf alle visuele elementen in detail:
- Prijsgrafieken: structuur, zones, labels, pijlen, patronen
- Schema's: PO3 schematics, cycle diagrammen, flow charts
- Tekst in afbeeldingen: titels, annotaties, nummers
- Trading concepten: supply/demand zones, BOS, liquidity levels

Wees specifiek en gebruik TCT terminologie waar van toepassing.
Taal: Nederlands.
```

### Stap 3: Beschrijving → ChromaDB
- Chunk: één beschrijving per pagina (geen verdere chunking nodig)
- Metadata:
  - `source_type: image`
  - `filename: {doc_name}`
  - `page_number: {n}`
  - `lecture_type: {lectures/reviews/reference}`
- Collection: `tct_strategy` (zelfde als tekst chunks)
- Embedding: Ollama nomic-embed-text (768 dim)

---

## Script: scripts/ingest_images.py

```python
# Pseudocode structuur
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
PDF_DIR = Path("docs/strategy")
IMAGE_DIR = Path("docs/strategy/images")

def pdf_to_images(pdf_path, output_dir, dpi=300):
    """Converteer PDF pagina's naar PNG afbeeldingen."""
    ...

def describe_image_with_gemini(image_path):
    """Stuur afbeelding naar Gemini Vision via OpenRouter."""
    # Base64 encode afbeelding
    # POST naar openrouter.ai/api/v1/chat/completions
    # Model: google/gemini-2.0-flash-001
    # Content: [{"type": "image_url", ...}, {"type": "text", ...}]
    ...

def ingest_image_descriptions(collection, descriptions):
    """Sla beschrijvingen op in ChromaDB met Ollama embeddings."""
    ...
```

---

## Afhankelijkheden
- `pdf2image` (pip)
- `poppler-utils` (apt op VPS)
- Bestaande: `chromadb`, `requests`, Ollama nomic-embed-text

## Geschatte omvang
- ~25 PDFs × gemiddeld 20 pagina's = ~500 afbeeldingen
- Gemini Vision: ~$0.001 per afbeelding = ~$0.50 totaal
- Verwerkingstijd: ~15-20 min op VPS

## Prioriteit
Hoog — PO3 schematics zijn kern van TCT strategie en zitten
grotendeels in afbeeldingen.
