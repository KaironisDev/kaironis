"""
Unit tests voor scripts/ingest_images.py

Alle externe calls (OpenRouter, Ollama, ChromaDB, pdf2image) worden gemockt.
Tests zijn volledig offline en idempotent.
"""

import base64
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Voeg de scripts directory toe zodat we ingest_images kunnen importeren
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

FAKE_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # minimale PNG header


def make_openrouter_response(content: str) -> dict:
    """Bouw een nep-OpenRouter API response."""
    return {
        "choices": [
            {
                "message": {
                    "content": content,
                }
            }
        ]
    }


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: describe_image — normale visuele content
# ─────────────────────────────────────────────────────────────────────────────

def test_describe_image_returns_description():
    """describe_image geeft een beschrijving terug bij normale visuele content."""
    expected = (
        "Pagina toont een PO3 schematic met supply zone bovenin "
        "en demand zone onderin. BOS pijl is zichtbaar naar rechts."
    )
    mock_response = MagicMock()
    mock_response.json.return_value = make_openrouter_response(expected)
    mock_response.raise_for_status = MagicMock()

    with patch("requests.post", return_value=mock_response) as mock_post:
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            # Herlaad module zodat env var wordt opgepikt
            import importlib
            import ingest_images
            importlib.reload(ingest_images)

            result = ingest_images.describe_image(FAKE_PNG_BYTES, "lecture_01.pdf", 3)

    assert result == expected
    mock_post.assert_called_once()

    # Controleer dat de payload de base64 image bevat
    call_kwargs = mock_post.call_args
    payload = call_kwargs[1]["json"]
    assert payload["model"] is not None
    content_parts = payload["messages"][0]["content"]
    image_part = next(p for p in content_parts if p["type"] == "image_url")
    assert "data:image/png;base64," in image_part["image_url"]["url"]


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: describe_image — lege/tekst pagina's worden overgeslagen
# ─────────────────────────────────────────────────────────────────────────────

def test_describe_image_skips_short_response():
    """describe_image geeft None terug als de response < 50 tekens is."""
    short_responses = [
        "Geen visuele content.",          # 22 tekens
        "OK",                             # 2 tekens
        "Pagina is leeg.",                # 16 tekens
        "Geen visuele trading content",   # 30 tekens
        "",                               # 0 tekens
    ]

    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
        import importlib
        import ingest_images
        importlib.reload(ingest_images)

        for short_text in short_responses:
            mock_response = MagicMock()
            mock_response.json.return_value = make_openrouter_response(short_text)
            mock_response.raise_for_status = MagicMock()

            with patch("requests.post", return_value=mock_response):
                result = ingest_images.describe_image(FAKE_PNG_BYTES, "doc.pdf", 1)

            assert result is None, (
                f"Verwachtte None voor response van {len(short_text)} tekens, "
                f"kreeg: {result!r}"
            )


def test_describe_image_accepts_long_enough_response():
    """describe_image geeft de tekst terug als response >= 50 tekens."""
    # Precies 50 tekens
    fifty_char_text = "A" * 50

    mock_response = MagicMock()
    mock_response.json.return_value = make_openrouter_response(fifty_char_text)
    mock_response.raise_for_status = MagicMock()

    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
        import importlib
        import ingest_images
        importlib.reload(ingest_images)

        with patch("requests.post", return_value=mock_response):
            result = ingest_images.describe_image(FAKE_PNG_BYTES, "doc.pdf", 1)

    assert result == fifty_char_text


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: get_ollama_embedding
# ─────────────────────────────────────────────────────────────────────────────

def test_get_ollama_embedding_returns_vector():
    """get_ollama_embedding geeft een lijst van floats terug."""
    fake_embedding = [0.1, 0.2, 0.3, -0.4, 0.5] * 76  # 380 dim

    mock_response = MagicMock()
    mock_response.json.return_value = {"embedding": fake_embedding}
    mock_response.raise_for_status = MagicMock()

    import importlib
    import ingest_images
    importlib.reload(ingest_images)

    with patch("requests.post", return_value=mock_response) as mock_post:
        result = ingest_images.get_ollama_embedding("TCT supply zone beschrijving")

    assert result == fake_embedding
    assert isinstance(result, list)
    assert all(isinstance(v, float) for v in result)

    # Controleer payload
    call_kwargs = mock_post.call_args
    payload = call_kwargs[1]["json"]
    assert payload["model"] == "nomic-embed-text"
    assert payload["prompt"] == "TCT supply zone beschrijving"


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: ingest_page — metadata structuur
# ─────────────────────────────────────────────────────────────────────────────

def test_ingest_page_metadata_structure():
    """ingest_page slaat de juiste metadata op in ChromaDB."""
    fake_embedding = [0.1] * 768
    mock_collection = MagicMock()
    description = "PO3 schematic met supply en demand zones zichtbaar op de grafiek van Bitcoin."

    metadata = {
        "filename": "lecture_03.pdf",
        "page_number": 7,
        "lecture_type": "lecture_03",
    }

    import importlib
    import ingest_images
    importlib.reload(ingest_images)

    with patch.object(ingest_images, "get_ollama_embedding", return_value=fake_embedding):
        ingest_images.ingest_page(mock_collection, description, metadata)

    mock_collection.add.assert_called_once()
    call_kwargs = mock_collection.add.call_args[1]

    # ID formaat check
    assert call_kwargs["ids"] == ["lecture_03.pdf::img::7"]

    # Document check
    assert call_kwargs["documents"] == [description]

    # Metadata check
    saved_metadata = call_kwargs["metadatas"][0]
    assert saved_metadata["filename"] == "lecture_03.pdf"
    assert saved_metadata["page_number"] == 7
    assert saved_metadata["source_type"] == "image"
    assert saved_metadata["lecture_type"] == "lecture_03"

    # Embedding check
    assert call_kwargs["embeddings"] == [fake_embedding]


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: duplicate pagina's worden overgeslagen
# ─────────────────────────────────────────────────────────────────────────────

def test_main_skips_duplicate_pages(tmp_path):
    """
    main() slaat pagina's over die al in ChromaDB staan
    (ID al aanwezig → geen Gemini call).
    """
    # Maak een fake PDF structuur
    docs_dir = tmp_path / "docs" / "strategy"
    docs_dir.mkdir(parents=True)

    # We mocken de PDF, niet een echte PDF aanmaken
    fake_pdf = docs_dir / "lecture_01.pdf"
    fake_pdf.write_bytes(b"fake pdf content")

    import importlib
    import ingest_images
    importlib.reload(ingest_images)

    # Stel in dat deze pagina al bestaat
    existing_id = "lecture_01.pdf::img::1"

    mock_collection = MagicMock()
    mock_collection.count.return_value = 1
    mock_collection.get.return_value = {"ids": [existing_id]}

    mock_client = MagicMock()
    mock_client.get_or_create_collection.return_value = mock_collection

    fake_pages = [(1, FAKE_PNG_BYTES), (2, FAKE_PNG_BYTES)]

    # Pagina 2 heeft content, pagina 1 is duplicate
    long_description = "Uitgebreide beschrijving van visuele TCT content op deze pagina met supply demand zones."

    # Patch de module-level constanten direct (env vars zijn al ingelezen bij import)
    with patch.object(ingest_images, "OPENROUTER_API_KEY", "test-key"):
        with patch.object(ingest_images, "DOCS_DIR", docs_dir):
            with patch("chromadb.HttpClient", return_value=mock_client):
                with patch.object(ingest_images, "pdf_to_images", return_value=fake_pages):
                    with patch.object(
                        ingest_images, "describe_image", return_value=long_description
                    ) as mock_describe:
                        with patch.object(
                            ingest_images, "get_ollama_embedding", return_value=[0.1] * 768
                        ):
                            ingest_images.main()

    # describe_image mag maar 1x aangeroepen zijn (pagina 2 — pagina 1 was duplicate)
    assert mock_describe.call_count == 1
    # Tweede argument is filename, derde is page_num
    assert mock_describe.call_args[0][2] == 2  # page_num=2


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: pdf_to_images — verwerkt pagina's correct in-memory
# ─────────────────────────────────────────────────────────────────────────────

def test_pdf_to_images_returns_page_tuples(tmp_path):
    """pdf_to_images geeft een lijst van (page_num, bytes) terug, geen bestanden."""
    fake_pdf = tmp_path / "test.pdf"
    fake_pdf.write_bytes(b"fake pdf")

    # Maak fake PIL images
    mock_page1 = MagicMock()
    mock_page2 = MagicMock()
    mock_page3 = MagicMock()

    def fake_save(buf, format):
        buf.write(b"PNG_DATA")

    mock_page1.save = fake_save
    mock_page2.save = fake_save
    mock_page3.save = fake_save

    import importlib
    import ingest_images
    importlib.reload(ingest_images)

    # pdf2image wordt inside de functie geïmporteerd, mock via sys.modules
    mock_pdf2image = MagicMock()
    mock_pdf2image.convert_from_path.return_value = [mock_page1, mock_page2, mock_page3]

    with patch.dict("sys.modules", {"pdf2image": mock_pdf2image}):
        result = ingest_images.pdf_to_images(fake_pdf, dpi=72)

    assert len(result) == 3

    # Page numbers zijn 1-gebaseerd
    assert result[0][0] == 1
    assert result[1][0] == 2
    assert result[2][0] == 3

    # Elk element is bytes
    for page_num, png_bytes in result:
        assert isinstance(page_num, int)
        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Test 7: describe_image — base64 encoding is correct
# ─────────────────────────────────────────────────────────────────────────────

def test_describe_image_encodes_bytes_as_base64():
    """describe_image stuurt de afbeelding als correcte base64 data URL."""
    test_bytes = b"\x89PNG\r\n\x1a\nFAKE_IMAGE_DATA"
    expected_b64 = base64.b64encode(test_bytes).decode("utf-8")
    expected_url = f"data:image/png;base64,{expected_b64}"

    long_response = "Gedetailleerde beschrijving van trading chart met meerdere zones en annotaties zichtbaar."
    mock_response = MagicMock()
    mock_response.json.return_value = make_openrouter_response(long_response)
    mock_response.raise_for_status = MagicMock()

    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
        import importlib
        import ingest_images
        importlib.reload(ingest_images)

        with patch("requests.post", return_value=mock_response) as mock_post:
            ingest_images.describe_image(test_bytes, "lecture.pdf", 5)

    call_kwargs = mock_post.call_args[1]
    payload = call_kwargs["json"]
    content_parts = payload["messages"][0]["content"]
    image_part = next(p for p in content_parts if p["type"] == "image_url")

    assert image_part["image_url"]["url"] == expected_url


# ─────────────────────────────────────────────────────────────────────────────
# Test 8: ingest_page — ID formaat is correct
# ─────────────────────────────────────────────────────────────────────────────

def test_ingest_page_id_format():
    """ingest_page gebruikt het correcte ID formaat: {filename}::img::{page_num}."""
    mock_collection = MagicMock()
    description = "Beschrijving van trading content met voldoende lengte voor verwerking."

    test_cases = [
        ("lecture_01.pdf", 1, "lecture_01.pdf::img::1"),
        ("advanced_concepts.pdf", 42, "advanced_concepts.pdf::img::42"),
        ("review session.pdf", 7, "review session.pdf::img::7"),
    ]

    import importlib
    import ingest_images
    importlib.reload(ingest_images)

    for filename, page_num, expected_id in test_cases:
        mock_collection.reset_mock()
        metadata = {
            "filename": filename,
            "page_number": page_num,
            "lecture_type": "test",
        }

        with patch.object(ingest_images, "get_ollama_embedding", return_value=[0.1] * 768):
            ingest_images.ingest_page(mock_collection, description, metadata)

        call_kwargs = mock_collection.add.call_args[1]
        assert call_kwargs["ids"] == [expected_id], (
            f"Voor {filename} pagina {page_num}: verwachtte {expected_id}, "
            f"kreeg {call_kwargs['ids']}"
        )
