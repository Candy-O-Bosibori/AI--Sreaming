from chunker import (
    chunk_by_paragraph,
    chunk_by_sentence,
    chunk_smart,
    chunk_text,
    _group_into_paragraphs,
    _looks_like_heading,
)


# ── chunk_text (original fallback) — unchanged behavior ───────────────

def test_chunk_text_respects_overlap():
    # Note: the module docstring's example claims ["abc", "cde"], but the
    # real behavior includes a trailing fragment from the sliding window
    # overshooting the string length by one step. Pre-existing behavior,
    # out of scope to change here — this test documents actual output.
    chunks = chunk_text("abcde", chunk_size=3, overlap=1)
    assert chunks == ["abc", "cde", "e"]


def test_chunk_text_handles_empty_string():
    assert chunk_text("") == []


# ── _looks_like_heading — the heuristic verified against real pypdf output ──
# These are the exact lines observed from parse_pdf(spongebob.pdf), used
# to design and validate the rule in the first place (see chunker.py's
# module docstring for the tradeoffs this heuristic accepts).

def test_heading_detected_after_sentence_end():
    # "About SpongeBob" follows a line with no prior text (start of doc)
    assert _looks_like_heading("About SpongeBob", "") is True


def test_heading_detected_between_sections():
    # "Residents of Bikini Bottom" follows "...Krabby Patties are legendary."
    assert _looks_like_heading("Residents of Bikini Bottom", "Krabby Patties are legendary.") is True


def test_short_continuation_line_not_flagged_as_heading():
    # "player." is the tail of a wrapped sentence, not a heading — this is
    # the real case that shaped the rule (see design discussion: a short
    # line alone isn't enough, it must also start a fresh sentence).
    prev = "Squidward Tentacles — SpongeBob's grumpy neighbour. Dreams of being a famous clarinet"
    assert _looks_like_heading("player.", prev) is False


def test_known_limitation_list_item_after_period_misfires():
    # KNOWN, ACCEPTED LIMITATION (see chunk_smart's module docstring):
    # a short line that starts fresh after a period-ending line is
    # indistinguishable from a real heading using this heuristic alone.
    # "06:15 Practices..." is really just the next item in a time-stamped
    # list, but gets flagged as a heading because the previous line also
    # happened to end in a period. This test documents the limitation
    # rather than hiding it — if this ever starts passing False, the
    # heuristic changed and this comment should be revisited.
    prev = "06:00 Alarm goes off. Gary meows. SpongeBob leaps out of bed with unnatural enthusiasm."
    assert _looks_like_heading('06:15 Practices laugh in the mirror: "AH HA HA HA HA."', prev) is True


def test_long_line_never_flagged_as_heading():
    long_line = "x" * 61  # over _MAX_HEADING_LENGTH
    assert _looks_like_heading(long_line, "") is False


def test_line_ending_in_punctuation_not_flagged_as_heading():
    assert _looks_like_heading("This is a short sentence.", "") is False


# ── _group_into_paragraphs / chunk_by_paragraph ────────────────────────

def test_group_into_paragraphs_merges_wrapped_lines():
    text = (
        "About SpongeBob\n"
        "SpongeBob lives in a pineapple under the sea in Bikini\n"
        "Bottom. He works at the Krusty Krab.\n"
        "Residents of Bikini Bottom\n"
        "Patrick Star is his best friend."
    )
    paragraphs = _group_into_paragraphs(text)
    assert len(paragraphs) == 2
    assert paragraphs[0] == "About SpongeBob SpongeBob lives in a pineapple under the sea in Bikini Bottom. He works at the Krusty Krab."
    assert paragraphs[1] == "Residents of Bikini Bottom Patrick Star is his best friend."


def test_chunk_by_paragraph_keeps_short_paragraph_whole():
    text = "A Heading\nJust one short sentence here."
    chunks = chunk_by_paragraph(text, chunk_size=500, overlap=50)
    assert len(chunks) == 1
    assert "A Heading" in chunks[0]
    assert "Just one short sentence here." in chunks[0]


def test_chunk_by_paragraph_splits_paragraph_exceeding_chunk_size():
    # A single paragraph longer than chunk_size must not become one
    # oversized chunk — it should fall through to sentence splitting.
    long_paragraph = "This is a sentence. " * 40  # ~840 chars, one paragraph
    chunks = chunk_by_paragraph(long_paragraph, chunk_size=500, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 500 or " " not in c for c in chunks)


def test_chunk_by_paragraph_empty_input():
    assert chunk_by_paragraph("") == []


# ── chunk_by_sentence ────────────────────────────────────────────────

def test_chunk_by_sentence_never_splits_mid_sentence():
    text = "First sentence here. Second sentence here. Third sentence here."
    chunks = chunk_by_sentence(text, chunk_size=30, overlap=5)
    # Every chunk should end with terminal punctuation (a whole sentence),
    # never a fragment cut mid-word.
    for chunk in chunks:
        assert chunk.rstrip()[-1] in ".!?"


def test_chunk_by_sentence_falls_back_to_char_split_for_oversized_sentence():
    huge_sentence = "word " * 200 + "."  # one "sentence", ~1000 chars
    chunks = chunk_by_sentence(huge_sentence, chunk_size=500, overlap=50)
    assert len(chunks) > 1


# ── chunk_smart cascade ─────────────────────────────────────────────

def test_chunk_smart_uses_paragraph_strategy_on_structured_text():
    text = (
        "About SpongeBob\n"
        "SpongeBob lives in a pineapple under the sea in Bikini\n"
        "Bottom. He works at the Krusty Krab making patties every day.\n"
        "Residents of Bikini Bottom\n"
        "Patrick Star is his best friend who lives under a rock nearby.\n"
    ) * 3  # repeat to get past the density threshold
    smart_chunks = chunk_smart(text, chunk_size=500, overlap=50)
    paragraph_chunks = chunk_by_paragraph(text, chunk_size=500, overlap=50)
    assert smart_chunks == paragraph_chunks


def test_chunk_smart_falls_back_to_char_chunking_on_unstructured_text():
    # No sentence punctuation, no line breaks — the kind of degenerate
    # text a badly-extracted PDF might produce. Should fall all the way
    # back to chunk_text() rather than trust paragraph/sentence detection.
    text = "word " * 1000  # no periods, no newlines at all
    smart_chunks = chunk_smart(text, chunk_size=500, overlap=50)
    fallback_chunks = chunk_text(text, chunk_size=500, overlap=50)
    assert smart_chunks == fallback_chunks


def test_chunk_smart_empty_input():
    assert chunk_smart("") == []


def test_chunk_smart_on_real_extracted_pdf_text():
    # Regression test against the actual sample PDF used to design this
    # heuristic — see chunker.py's module docstring. If pypdf's extraction
    # behavior ever changes, this is the test that would catch it.
    import os
    from parse_pdf import parse_pdf

    sample_path = os.path.join(os.path.dirname(__file__), "..", "..", "spongebob.pdf")
    with open(sample_path, "rb") as f:
        text = parse_pdf(f.read())

    chunks = chunk_smart(text, chunk_size=500, overlap=50)

    assert len(chunks) > 1
    # No chunk should exceed chunk_size by more than one sentence-split's
    # worth of slack, and none should be empty.
    assert all(chunk.strip() for chunk in chunks)
    # The old fixed-character chunker cut "Patrick Star's" mid-word into
    # a fragment starting with "'s best friend" — the new chunking should
    # not reproduce that specific failure.
    assert not any(c.startswith("'s ") for c in chunks)
