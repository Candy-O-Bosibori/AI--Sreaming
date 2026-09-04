import pytest

from auth import get_current_user
from main import _parse_numbered_list, app

from ._client import make_client

FAKE_USER = {"id": "00000000-0000-0000-0000-000000000001", "email": "student@williams.edu"}
app.dependency_overrides[get_current_user] = lambda: FAKE_USER
client = make_client()


# ── _parse_numbered_list — verified against real Claude output ────────
# These cases include a real failure found during manual end-to-end
# testing: Claude sometimes prepends a markdown heading (e.g. "# Discussion
# Questions") despite the prompt asking for only the list. A line is only
# kept if it has a real list marker (number/bullet) or ends in "?".

def test_parse_standard_numbered_list():
    text = "1. First question?\n2. Second question?\n3. Third question?"
    assert _parse_numbered_list(text) == [
        "First question?", "Second question?", "Third question?",
    ]


def test_parse_parens_style_numbering():
    text = "1) First one\n2) Second one"
    assert _parse_numbered_list(text) == ["First one", "Second one"]


def test_parse_bullet_style():
    text = "- First\n- Second"
    assert _parse_numbered_list(text) == ["First", "Second"]


def test_parse_ignores_blank_lines():
    text = "1. Question one\n\n2. Question two\n\n\n3. Question three"
    assert _parse_numbered_list(text) == ["Question one", "Question two", "Question three"]


def test_parse_drops_unmarked_non_question_lines():
    # A bare line with no list marker and no "?" isn't a real list item.
    text = "Just a plain line\nAnother plain line"
    assert _parse_numbered_list(text) == []


def test_parse_drops_leading_markdown_heading():
    # The actual bug found in manual testing: Claude prepended
    # "# Discussion Questions" before a correctly-formatted list.
    text = (
        "# Discussion Questions\n"
        "1. Why might this happen?\n"
        "2. What does this reveal?"
    )
    assert _parse_numbered_list(text) == [
        "Why might this happen?", "What does this reveal?",
    ]


def test_parse_keeps_unmarked_question_lines():
    # A line with no number/bullet is still kept if it ends in "?" —
    # covers Claude occasionally dropping numbering on one line.
    text = "1. First question?\nSecond question with no number?"
    assert _parse_numbered_list(text) == [
        "First question?", "Second question with no number?",
    ]


def test_parse_empty_input():
    assert _parse_numbered_list("") == []


# ── Endpoint shape tests (no live DB / Anthropic call needed) ─────────

def test_summary_requires_auth():
    app.dependency_overrides.pop(get_current_user, None)
    try:
        resp = client.post("/documents/1/summary")
    finally:
        app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    assert resp.status_code in (401, 422)


def test_discussion_questions_requires_auth():
    app.dependency_overrides.pop(get_current_user, None)
    try:
        resp = client.post("/documents/1/discussion-questions")
    finally:
        app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    assert resp.status_code in (401, 422)


def test_summary_404s_for_nonexistent_document():
    resp = client.post("/documents/999999999/summary")
    assert resp.status_code == 404


def test_discussion_questions_404s_for_nonexistent_document():
    resp = client.post("/documents/999999999/discussion-questions")
    assert resp.status_code == 404


# ── Integration tests (require a live DB + real Anthropic call) ──────

@pytest.mark.integration
def test_summary_returns_real_content():
    """Verified manually end-to-end against spongebob.pdf during
    development — a real Claude call producing a genuine multi-point
    summary covering distinct sections of the document, not just the
    most similar chunk to some query. Marked integration since it costs
    a real API call and needs a live DB with an uploaded document."""
    pytest.skip("Requires live DB + uploaded document — run manually")


@pytest.mark.integration
def test_discussion_questions_returns_real_questions():
    pytest.skip("Requires live DB + uploaded document — run manually")
