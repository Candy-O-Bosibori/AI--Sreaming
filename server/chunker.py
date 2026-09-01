# ============================================================
# chunker.py — Split a long text into overlapping chunks
# ============================================================
# The AI assistant can't search one giant wall of text efficiently.
# Instead, we cut the text into small pieces (chunks) and store
# each chunk separately. At query time, we find the most relevant
# chunks and send only those to the LLM — not the whole document.
#
# Three strategies, tried in order (each one falls back to the next
# if it can't produce reasonable chunks):
#
#   1. chunk_by_paragraph — groups wrapped lines into paragraphs using
#      a heuristic on pypdf's flattened text (no real layout data is
#      available — see note on _looks_like_heading below).
#   2. chunk_by_sentence   — splits an over-long paragraph on sentence
#      boundaries, so at least a single idea isn't cut mid-thought.
#   3. chunk_text          — the original fixed-character-count cut.
#      Used whenever 1 and 2 don't find enough real structure to work
#      with (e.g. badly-extracted text with no punctuation/line breaks).
# ============================================================

import re
from typing import List


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """
    Split `text` into a list of overlapping chunks, purely by character
    count — no awareness of sentences, paragraphs, or words.

    This is the fallback strategy: always available, never fails, but
    can cut a chunk mid-sentence or mid-word. See chunk_smart() for the
    paragraph/sentence-aware strategies that try this only as a last resort.

    Args:
        text:       The full document text to split.
        chunk_size: How many characters per chunk (default 500).
        overlap:    How many characters to repeat between chunks (default 50).

    Returns:
        A list of strings, each up to chunk_size characters long.

    Example:
        chunk_text("abcde", chunk_size=3, overlap=1)
        → ["abc", "cde", "e"]
              ↑ the "c" is shared — that's the overlap.
              Note the trailing "e": the sliding window can overshoot the
              end of the text by one step, producing a small final
              fragment. Pre-existing behavior, not changed here.
    """

    chunks = []   # We'll collect all chunks here
    start = 0     # Start position of the current chunk in the text

    # Keep slicing until we've covered the whole text
    while start < len(text):

        # Calculate the end position of this chunk
        end = start + chunk_size  # e.g. start=0, chunk_size=500 → end=500

        # Slice the text from start to end.
        # If end goes past the end of the text, Python just takes what's left.
        chunk = text[start:end]

        # Only add non-empty chunks (safety check for trailing whitespace)
        if chunk.strip():
            chunks.append(chunk)

        # Move start forward by (chunk_size - overlap).
        # Subtracting the overlap means the next chunk begins overlap chars
        # BEFORE where this chunk ended — creating the shared region.
        # e.g. chunk_size=500, overlap=50 → advance by 450 each time
        start += chunk_size - overlap

    return chunks  # Return the full list of chunks


# ── Sentence-boundary detection ─────────────────────────────────────
# Splits after ., !, or ? followed by whitespace and a capital letter —
# a deliberately simple heuristic. It will over-split on abbreviations
# ("Dr. Smith") and under-split on some edge cases, but false splits
# just mean slightly smaller chunks, which is a minor quality cost,
# not a correctness bug.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def _split_sentences(text: str) -> List[str]:
    sentences = _SENTENCE_BOUNDARY.split(text.strip())
    return [s.strip() for s in sentences if s.strip()]


def chunk_by_sentence(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """
    Pack whole sentences into chunks up to chunk_size, so a chunk never
    cuts a sentence in half. Falls back to chunk_text() for any single
    sentence that's already longer than chunk_size on its own.
    """
    sentences = _split_sentences(text)
    if not sentences:
        return []

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for sentence in sentences:
        if len(sentence) > chunk_size:
            # One sentence alone exceeds the limit — flush what we have,
            # then fall back to a raw character cut for this sentence only.
            if current:
                chunks.append(" ".join(current))
                current, current_len = [], 0
            chunks.extend(chunk_text(sentence, chunk_size=chunk_size, overlap=overlap))
            continue

        # +1 accounts for the space that will join sentences together.
        added_len = len(sentence) + (1 if current else 0)
        if current and current_len + added_len > chunk_size:
            chunks.append(" ".join(current))
            current, current_len = [sentence], len(sentence)
        else:
            current.append(sentence)
            current_len += added_len

    if current:
        chunks.append(" ".join(current))

    return chunks


# ── Paragraph detection ─────────────────────────────────────────────
# A PDF file has no stored concept of "paragraph" — pypdf's extract_text()
# just returns flattened lines with no layout/spacing information (unlike
# a library such as pdfplumber, which exposes real page coordinates and
# could measure actual vertical gaps between lines). This is a heuristic
# on that flattened text, not a measurement of real document structure —
# it will misfire on some inputs (e.g. a short list item that happens to
# follow a line ending in a period can be mistaken for a heading). That's
# an accepted, low-stakes tradeoff: a misfire just splits a paragraph
# slightly early, it doesn't lose or corrupt any content.

_MAX_HEADING_LENGTH = 60


def _looks_like_heading(line: str, prev_line: str) -> bool:
    line = line.strip()
    if not line or len(line) > _MAX_HEADING_LENGTH:
        return False
    if line[-1] in ".!?,;:":
        return False
    prev = (prev_line or "").strip()
    prev_ended_a_sentence = (not prev) or prev[-1] in ".!?:"
    return prev_ended_a_sentence


def _group_into_paragraphs(text: str) -> List[str]:
    lines = [ln for ln in text.split("\n")]
    paragraphs: List[str] = []
    current: List[str] = []
    prev_line = ""

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if _looks_like_heading(stripped, prev_line) and current:
            paragraphs.append(" ".join(current))
            current = []

        current.append(stripped)
        prev_line = stripped

    if current:
        paragraphs.append(" ".join(current))

    return paragraphs


def chunk_by_paragraph(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """
    Group lines into paragraphs (see _group_into_paragraphs), then pack
    whole paragraphs into chunks up to chunk_size. A paragraph longer
    than chunk_size on its own is split by chunk_by_sentence() instead
    of being cut mid-sentence.
    """
    paragraphs = _group_into_paragraphs(text)
    if not paragraphs:
        return []

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for para in paragraphs:
        if len(para) > chunk_size:
            if current:
                chunks.append("\n\n".join(current))
                current, current_len = [], 0
            chunks.extend(chunk_by_sentence(para, chunk_size=chunk_size, overlap=overlap))
            continue

        added_len = len(para) + (2 if current else 0)  # "\n\n" join
        if current and current_len + added_len > chunk_size:
            chunks.append("\n\n".join(current))
            current, current_len = [para], len(para)
        else:
            current.append(para)
            current_len += added_len

    if current:
        chunks.append("\n\n".join(current))

    return chunks


# ── Cascade entry point ──────────────────────────────────────────────
# Minimum density thresholds below which a strategy is considered to
# have found "not enough real structure" to trust, and we fall back to
# the next strategy. Expressed as characters-per-break so the check
# scales with document length rather than using a fixed count.

_MIN_CHARS_PER_PARAGRAPH_BREAK = 2000
_MIN_CHARS_PER_SENTENCE_BREAK = 2000


def chunk_smart(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """
    Chunk `text` using the best available strategy: paragraph-aware,
    falling back to sentence-aware, falling back to fixed-character
    chunking (chunk_text) if the text doesn't have enough detectable
    structure for the smarter strategies to be trustworthy.
    """
    if not text.strip():
        return []

    paragraphs = _group_into_paragraphs(text)
    if len(paragraphs) >= max(1, len(text) // _MIN_CHARS_PER_PARAGRAPH_BREAK):
        return chunk_by_paragraph(text, chunk_size=chunk_size, overlap=overlap)

    sentences = _split_sentences(text)
    if len(sentences) >= max(1, len(text) // _MIN_CHARS_PER_SENTENCE_BREAK):
        return chunk_by_sentence(text, chunk_size=chunk_size, overlap=overlap)

    return chunk_text(text, chunk_size=chunk_size, overlap=overlap)
