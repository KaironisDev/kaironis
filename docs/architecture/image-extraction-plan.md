# Image Extraction Plan — TCT PDF Vision

**Goal:** Extract visual content from TCT PDFs and store it in ChromaDB
so Kaironis can also query schematics, charts, and diagrams.

**Why:** PO3 schematics, supply/demand zone drawings, and cycle
diagrams are mostly in images — not in text.

---

## Approach

### Step 1: PDF → Images
- Tool: `pdf2image` (poppler backend)
- Each page → PNG at **150 DPI** (lower than 300 for speed, still readable)
- Processing is **fully in-memory** — no image files are saved to disk

### Step 2: Image → Description (Gemini Vision)
- Model: `google/gemini-2.0-flash-001` via OpenRouter
- Prompt per image:
```
You are analyzing page {page_num} of the TCT (Time-Cycle Trading)
strategy document '{filename}'.

Describe all visual elements in detail:
- Price charts: structure, zones, labels, arrows, patterns
  (PO3, BOS, ranges, supply/demand)
- Diagrams: describe the structure and what it shows
- Text in images: titles, annotations, numbers, legends
- Empty pages or text-only pages: indicate "No visual trading content"

Use TCT terminology. Be specific and detailed.
Language: Dutch. Maximum 800 words.
```

### Step 3: Description → ChromaDB
- Chunk: one description per page (no further chunking needed)
- Metadata:
  - `source_type: image`
  - `filename: {doc_name}`
  - `rel_path: {relative path within DOCS_DIR}`
  - `page_number: {n}`
  - `lecture_type: {lectures/reviews/reference}`
- Collection: `tct_strategy` (same as text chunks)
- Embedding: Ollama nomic-embed-text (768 dim)
- **Doc ID format:** `{rel_path}::img::{page_num}` (uses relative path to avoid collisions)

---

## Script: scripts/ingest_images.py

```python
# Key implementation details
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
DOCS_DIR = Path(os.getenv("DOCS_DIR", "docs/strategy"))
DPI = 150  # in-memory conversion, no files saved to disk

def pdf_to_images(pdf_path, dpi=DPI):
    """Convert PDF pages to (page_number, png_bytes) tuples. Fully in-memory."""
    ...

def describe_image(image_bytes, filename, page_num):
    """Send image to Gemini Vision via OpenRouter. Returns None for short responses."""
    ...

def ingest_page(collection, description, metadata):
    """Store description in ChromaDB with Ollama embeddings.
    ID uses rel_path (relative to DOCS_DIR) to avoid collisions."""
    ...
```

---

## Dependencies
- `pdf2image` (pip)
- `poppler-utils` (apt on VPS)
- Existing: `chromadb`, `requests`, Ollama nomic-embed-text

## Estimated scope
- ~25 PDFs × ~20 pages average = ~500 images
- Gemini Vision: ~$0.001 per image = ~$0.50 total
- Processing time: ~15-20 min on VPS

## Priority
High — PO3 schematics are the core of the TCT strategy and are
mostly in images.

## Implementation Notes
- **No image files on disk:** pages are converted in-memory and sent directly to the API
- **No `docs/strategy/images/` directory** is created or used
- **Idempotent:** pages already in ChromaDB are skipped (duplicate check by doc_id)
- **OLLAMA_HOST normalization:** handles both `localhost` and `http://ollama:11434` formats
