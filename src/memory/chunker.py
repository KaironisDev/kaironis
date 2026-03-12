"""
Text chunking voor Kaironis memory module.

Splitst markdown documenten in semantisch zinvolle stukken voor
opslag in ChromaDB. Respecteert markdown headers als boundaries.
"""

import re
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Ruwe schatting: 1 token ≈ 4 tekens (voor Engelse/Nederlandse tekst)
_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    """Schat het aantal tokens in een tekst (rough approximation)."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _split_by_headers(text: str) -> List[Tuple[str, str]]:
    """
    Splits markdown tekst op headers (# ## ### etc.).

    Returns:
        Lijst van (header, body) tuples. De eerste entry kan een lege
        header hebben als er tekst vóór de eerste header staat.
    """
    # Patroon: regel die begint met één of meer #
    header_pattern = re.compile(r"^(#{1,6}\s.+)$", re.MULTILINE)
    parts: List[Tuple[str, str]] = []

    matches = list(header_pattern.finditer(text))
    if not matches:
        return [("", text.strip())]

    # Tekst vóór de eerste header
    pre_header = text[: matches[0].start()].strip()
    if pre_header:
        parts.append(("", pre_header))

    for i, match in enumerate(matches):
        header = match.group(0).strip()
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        parts.append((header, body))

    return parts


def chunk_markdown(
    text: str,
    max_tokens: int = 500,
    overlap: int = 50,
) -> List[str]:
    """
    Splits een markdown document in chunks van maximaal max_tokens tokens.

    Strategie:
    1. Split op markdown headers (##, ###, enz.) als primaire boundaries.
    2. Als een sectie groter is dan max_tokens, split verder op alinea's.
    3. Als een alinea nog groter is, split op zin-niveau.
    4. Voeg overlap toe vanuit de vorige chunk.

    Args:
        text: De volledige markdown tekst.
        max_tokens: Maximum aantal tokens per chunk (default: 500).
        overlap: Aantal tokens overlap met de vorige chunk (default: 50).

    Returns:
        Lijst van tekst-chunks.
    """
    if not text or not text.strip():
        return []

    sections = _split_by_headers(text)
    chunks: List[str] = []
    prev_tail = ""  # De laatste ~overlap tokens van de vorige chunk

    for header, body in sections:
        section_text = f"{header}\n\n{body}".strip() if header else body
        if not section_text:
            continue

        if _estimate_tokens(section_text) <= max_tokens:
            # Sectie past in één chunk
            chunk = _prepend_overlap(prev_tail, section_text, max_tokens)
            chunks.append(chunk)
            prev_tail = _extract_tail(section_text, overlap)
        else:
            # Sectie is te groot — splits verder
            sub_chunks = _split_large_section(
                header, body, max_tokens, overlap, prev_tail
            )
            chunks.extend(sub_chunks)
            if sub_chunks:
                prev_tail = _extract_tail(sub_chunks[-1], overlap)

    return [c for c in chunks if c.strip()]


def _split_large_section(
    header: str,
    body: str,
    max_tokens: int,
    overlap: int,
    initial_overlap: str,
) -> List[str]:
    """Splits een te-grote sectie op alinea/zin niveau."""
    # Split op dubbele newlines (alinea's)
    paragraphs = [p.strip() for p in re.split(r"\n\n+", body) if p.strip()]
    chunks: List[str] = []
    current_parts: List[str] = []
    current_tokens = 0
    prev_tail = initial_overlap

    # Voeg de header toe aan het eerste deel
    header_prefix = f"{header}\n\n" if header else ""
    header_tokens = _estimate_tokens(header_prefix)

    for para in paragraphs:
        para_tokens = _estimate_tokens(para)

        if para_tokens > max_tokens:
            # Alinea zelf is te groot — splits op zinnen
            if current_parts:
                # Flush huidige buffer eerst
                chunk_text = _prepend_overlap(
                    prev_tail,
                    header_prefix + "\n\n".join(current_parts),
                    max_tokens,
                )
                chunks.append(chunk_text)
                prev_tail = _extract_tail(chunk_text, overlap)
                current_parts = []
                current_tokens = 0
                header_prefix = ""
                header_tokens = 0

            sentence_chunks = _split_by_sentences(para, max_tokens, overlap, prev_tail)
            chunks.extend(sentence_chunks)
            if sentence_chunks:
                prev_tail = _extract_tail(sentence_chunks[-1], overlap)

        elif current_tokens + para_tokens + header_tokens > max_tokens and current_parts:
            # Huidige chunk is vol — flush
            chunk_text = _prepend_overlap(
                prev_tail,
                header_prefix + "\n\n".join(current_parts),
                max_tokens,
            )
            chunks.append(chunk_text)
            prev_tail = _extract_tail(chunk_text, overlap)
            current_parts = [para]
            current_tokens = para_tokens
            header_prefix = ""
            header_tokens = 0
        else:
            current_parts.append(para)
            current_tokens += para_tokens

    # Resterende inhoud
    if current_parts:
        chunk_text = _prepend_overlap(
            prev_tail,
            header_prefix + "\n\n".join(current_parts),
            max_tokens,
        )
        chunks.append(chunk_text)

    return chunks


def _split_by_sentences(
    text: str,
    max_tokens: int,
    overlap: int,
    initial_overlap: str,
) -> List[str]:
    """Splits tekst op zinnen als alinea's nog te groot zijn."""
    # Eenvoudige zin-splitter op ., !, ?
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: List[str] = []
    current_sents: List[str] = []
    current_tokens = 0
    prev_tail = initial_overlap

    for sent in sentences:
        sent_tokens = _estimate_tokens(sent)

        if sent_tokens > max_tokens:
            # Zin is groter dan max_tokens — split op woorden
            if current_sents:
                chunk_text = _prepend_overlap(prev_tail, " ".join(current_sents), max_tokens)
                chunks.append(chunk_text)
                prev_tail = _extract_tail(chunk_text, overlap)
                current_sents = []
                current_tokens = 0

            word_chunks = _split_by_words(sent, max_tokens, overlap, prev_tail)
            chunks.extend(word_chunks)
            if word_chunks:
                prev_tail = _extract_tail(word_chunks[-1], overlap)

        elif current_tokens + sent_tokens > max_tokens and current_sents:
            chunk_text = _prepend_overlap(prev_tail, " ".join(current_sents), max_tokens)
            chunks.append(chunk_text)
            prev_tail = _extract_tail(chunk_text, overlap)
            current_sents = [sent]
            current_tokens = sent_tokens
        else:
            current_sents.append(sent)
            current_tokens += sent_tokens

    if current_sents:
        chunk_text = _prepend_overlap(prev_tail, " ".join(current_sents), max_tokens)
        chunks.append(chunk_text)

    return chunks


def _split_by_words(
    text: str,
    max_tokens: int,
    overlap: int,
    initial_overlap: str,
) -> List[str]:
    """Splits tekst op woordgrenzen als laatste redmiddel."""
    max_chars = max_tokens * _CHARS_PER_TOKEN
    chunks: List[str] = []
    words = text.split()
    current_words: List[str] = []
    current_chars = 0
    prev_tail = initial_overlap

    for word in words:
        word_chars = len(word) + 1  # +1 voor spatie
        if current_chars + word_chars > max_chars and current_words:
            chunk_text = _prepend_overlap(prev_tail, " ".join(current_words), max_tokens)
            chunks.append(chunk_text)
            prev_tail = _extract_tail(chunk_text, overlap)
            current_words = [word]
            current_chars = word_chars
        else:
            current_words.append(word)
            current_chars += word_chars

    if current_words:
        chunk_text = _prepend_overlap(prev_tail, " ".join(current_words), max_tokens)
        chunks.append(chunk_text)

    return chunks


def _extract_tail(text: str, overlap_tokens: int) -> str:
    """Haal de laatste overlap_tokens uit een tekst."""
    chars = overlap_tokens * _CHARS_PER_TOKEN
    return text[-chars:] if len(text) > chars else text


def _prepend_overlap(overlap_text: str, new_text: str, max_tokens: int) -> str:
    """
    Voeg overlap toe aan het begin van een nieuw chunk, als er ruimte is.
    Zorgt ervoor dat het totaal niet boven max_tokens uitkomt.
    """
    if not overlap_text:
        return new_text

    new_tokens = _estimate_tokens(new_text)
    overlap_tokens = _estimate_tokens(overlap_text)
    available = max_tokens - new_tokens

    if available <= 0:
        return new_text

    # Neem zoveel overlap als er ruimte is
    chars_available = available * _CHARS_PER_TOKEN
    trimmed_overlap = overlap_text[-chars_available:] if len(overlap_text) > chars_available else overlap_text

    return f"[...]\n{trimmed_overlap}\n\n{new_text}"
