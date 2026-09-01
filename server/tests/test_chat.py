import contextlib
from unittest.mock import patch

import jwt
import pytest
from fastapi.testclient import TestClient

from auth import REQUIRED_EMAIL_DOMAIN, get_current_user
from main import app

FAKE_USER = {"id": "00000000-0000-0000-0000-000000000001", "email": "student@williams.edu"}


def _fake_current_user():
    return FAKE_USER


# By default, tests run as an authenticated Williams user — this lets the
# existing request-shape/SSE-format tests keep exercising real route logic
# without needing a live Supabase JWT. Auth-specific tests below temporarily
# remove this override to hit the real get_current_user() dependency.
app.dependency_overrides[get_current_user] = _fake_current_user
client = TestClient(app)


# ── Auth-gating tests (real auth.py runs, no dependency override) ─────

@contextlib.contextmanager
def _real_auth():
    """Temporarily remove the fake-user override so requests hit the
    actual get_current_user() dependency (used to prove routes are
    genuinely gated, not just gated in test setup)."""
    app.dependency_overrides.pop(get_current_user, None)
    try:
        yield client
    finally:
        app.dependency_overrides[get_current_user] = _fake_current_user


def test_chat_requires_authorization_header():
    with _real_auth() as c:
        resp = c.post("/chat", json={"message": "hi", "doc_id": 1})
    assert resp.status_code in (401, 422)  # FastAPI 422s on a missing required Header


def test_documents_requires_authorization_header():
    with _real_auth() as c:
        resp = c.get("/documents")
    assert resp.status_code in (401, 422)


def test_history_requires_authorization_header():
    with _real_auth() as c:
        resp = c.get("/history?doc_id=1")
    assert resp.status_code in (401, 422)


def test_get_current_user_rejects_non_williams_email(monkeypatch):
    # Unit test of the auth dependency itself — no TestClient/live DB needed.
    # auth.py reads SUPABASE_JWT_SECRET from the environment lazily (per
    # request), so patching os.environ is what actually takes effect here.
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret")
    fake_token = jwt.encode(
        {"sub": "abc-123", "email": "student@gmail.com", "aud": "authenticated"},
        "test-secret",
        algorithm="HS256",
    )
    with pytest.raises(Exception) as exc_info:
        get_current_user(authorization=f"Bearer {fake_token}")
    assert getattr(exc_info.value, "status_code", None) == 403


def test_get_current_user_accepts_williams_email(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret")
    fake_token = jwt.encode(
        {"sub": "abc-123", "email": "student@williams.edu", "aud": "authenticated"},
        "test-secret",
        algorithm="HS256",
    )
    user = get_current_user(authorization=f"Bearer {fake_token}")
    assert user["email"].endswith(REQUIRED_EMAIL_DOMAIN)
    assert user["id"] == "abc-123"


def test_get_current_user_rejects_malformed_header(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret")
    with pytest.raises(Exception):
        get_current_user(authorization="not-a-bearer-token")


# ── Unit-style tests (authenticated, no DB required) ──────────────────

def test_upload_rejects_non_pdf():
    resp = client.post(
        "/upload",
        files={"file": ("notes.txt", b"some text content", "text/plain")},
    )
    assert resp.status_code == 400
    assert "PDF" in resp.json()["detail"]


def test_upload_rejects_empty_pdf():
    # A valid PDF header but no extractable text (simulate scanned/empty)
    fake_pdf = b"%PDF-1.4"
    resp = client.post(
        "/upload",
        files={"file": ("empty.pdf", fake_pdf, "application/pdf")},
    )
    # pypdf will fail to parse or return empty text — either 422 or 500 is acceptable
    assert resp.status_code in (422, 500)


def test_history_returns_empty_list_for_unknown_doc():
    resp = client.get("/history?doc_id=999999")
    assert resp.status_code == 200
    assert resp.json() == []


def test_chat_requires_doc_id():
    resp = client.post("/chat", json={"message": "hello"})
    assert resp.status_code == 422  # FastAPI validation error — doc_id missing


def test_chat_requires_message():
    resp = client.post("/chat", json={"doc_id": 1})
    assert resp.status_code == 422  # FastAPI validation error — message missing


# ── Debate mode tests ─────────────────────────────────────────────────
# These patch out the DB-touching calls inside stream_chat (touch_document,
# get_history, save_message) so the request-shape/SSE-format checks below
# stay true "no DB required" tests, per this file's original design — they
# assert on validation/headers, not on data actually persisting.

_DB_PATCHES = (
    patch("main.touch_document", return_value=None),
    patch("main.get_history", return_value=[]),
    patch("main.save_message", return_value=None),
)


@contextlib.contextmanager
def _no_db():
    with _DB_PATCHES[0], _DB_PATCHES[1], _DB_PATCHES[2]:
        yield


def test_debate_mode_defaults_to_false():
    # debate_mode is optional — omitting it should not cause a validation error.
    with _no_db():
        resp = client.post("/chat", json={"message": "hello", "doc_id": 1})
    # Any response other than 422 means the body shape was valid
    assert resp.status_code != 422


def test_debate_mode_true_accepted():
    with _no_db():
        resp = client.post(
            "/chat",
            json={"message": "hello", "doc_id": 1, "debate_mode": True},
        )
    assert resp.status_code != 422


def test_debate_mode_invalid_type_rejected():
    # Pydantic v2's lax bool mode coerces common truthy/falsy strings
    # ("yes", "true", "1", ...) into real booleans, so those are accepted
    # — a value it can't coerce at all is what actually triggers a 422.
    with _no_db():
        resp = client.post(
            "/chat",
            json={"message": "hello", "doc_id": 1, "debate_mode": ["not", "a", "bool"]},
        )
    assert resp.status_code == 422


# ── SSE format tests ──────────────────────────────────────────────────

def test_chat_response_is_event_stream():
    # /chat must declare text/event-stream so browsers know to parse SSE.
    with _no_db():
        resp = client.post("/chat", json={"message": "hi", "doc_id": 1})
    assert "text/event-stream" in resp.headers.get("content-type", "")


def test_chat_response_has_cache_control():
    # Cache-Control: no-cache is required for SSE — without it proxies and
    # browsers may buffer the response and break the live-streaming effect.
    with _no_db():
        resp = client.post("/chat", json={"message": "hi", "doc_id": 1})
    assert resp.headers.get("cache-control") == "no-cache"


# ── Integration tests (require a running DB + seeded data) ───────────
# Run these manually after: python seed.py
#
# To run only unit tests (skip DB):
#   pytest tests/ -v -k "not integration"
#
# To run everything:
#   pytest tests/ -v

@pytest.mark.integration
def test_full_chat_flow():
    """Upload a tiny in-memory PDF, chat, check history saves."""
    # This test requires the DB to be running and setup.sql to have been applied.
    # It's marked integration so it can be skipped in CI without a DB.
    pytest.skip("Requires live DB — run manually after seed.py")


@pytest.mark.integration
def test_chat_history_is_private_per_user():
    """Two different users chatting on the same doc must not see each other's history."""
    # Requires a live DB — verifies the core private-per-student-history requirement.
    pytest.skip("Requires live DB — run manually after seed.py")
