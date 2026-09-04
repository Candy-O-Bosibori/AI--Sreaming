# ============================================================
# main.py — FastAPI server
# ============================================================

import os
import re
from contextlib import asynccontextmanager

import anthropic
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth import get_current_user
from chunker import chunk_smart
from db import close_pool, get_pool, open_pool
from embedder import embed_chunks
from history import get_history, save_message, touch_document
from parse_pdf import parse_pdf
from prompts import (
    SYSTEM_PROMPT_DEBATE,
    SYSTEM_PROMPT_DEFAULT,
    SYSTEM_PROMPT_DISCUSSION_QUESTIONS,
    SYSTEM_PROMPT_SUMMARY,
)
from query import get_all_chunks, query_similar
from store import create_document, store_chunks

# Load API keys from .env for local development
# In production (Railway) env vars are injected directly — no .env file needed
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key, value)

# Shared Anthropic async client
client = anthropic.AsyncAnthropic()


# ── Lifespan — open/close the async DB connection pool with the app ───
# The pool is created once here (not per-request) and shared across
# every route, so requests borrow-and-return a connection instead of
# opening a brand-new one each time. See db.py for the pool itself.
@asynccontextmanager
async def lifespan(app: FastAPI):
    await open_pool()
    yield
    await close_pool()


app = FastAPI(lifespan=lifespan)

ALLOWED_ORIGINS = [
    "http://localhost:5173",                          # local dev
    os.environ.get("FRONTEND_URL", ""),               # set this in Railway to your Vercel URL
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in ALLOWED_ORIGINS if o],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request model ─────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    doc_id: int
    debate_mode: bool = False


# ── Streaming generator for /chat ─────────────────────────────────────
async def stream_chat(message: str, doc_id: int, user_id: str, debate_mode: bool = False):
    await touch_document(doc_id)
    history = await get_history(doc_id, user_id, limit=6)
    chunks = await query_similar(message, top_k=12, doc_id=doc_id)
    context = "\n\n".join(chunks)

    system_prompt = SYSTEM_PROMPT_DEBATE if debate_mode else SYSTEM_PROMPT_DEFAULT
    messages_payload = history + [{"role": "user", "content": message}]
    full_reply = []

    async with client.messages.stream(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=f"{system_prompt}\n\n{context}",
        messages=messages_payload,
    ) as stream:
        async for text in stream.text_stream:
            full_reply.append(text)
            yield f"data: {text}\n\n"

    await save_message(doc_id, user_id, "user", message)
    await save_message(doc_id, user_id, "assistant", "".join(full_reply))
    yield "data: [DONE]\n\n"


# ── Endpoints ─────────────────────────────────────────────────────────
# Every route below requires a valid @williams.edu Supabase session
# (see auth.py) — there is no anonymous/public use of this API.
#
# Every route is `async def`, and every call inside genuinely `await`s —
# the DB pool (db.py) and OpenAI client (embedder.py) are both real async
# clients now, not blocking calls hidden inside an async-labeled function.
# A route with no I/O of its own (there are none left here) could stay
# plain `def`, but keeping all routes async is simpler to reason about
# once nothing inside blocks the event loop.

@app.post("/chat")
async def chat(req: ChatRequest, user: dict = Depends(get_current_user)):
    return StreamingResponse(
        stream_chat(req.message, req.doc_id, user["id"], req.debate_mode),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/history")
async def history(doc_id: int, user: dict = Depends(get_current_user)):
    return await get_history(doc_id, user["id"])


@app.get("/documents")
async def list_documents(user: dict = Depends(get_current_user)):
    async with get_pool().connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT dm.id, dm.filename, dm.created_at, COUNT(d.id) AS chunk_count
                FROM documents_meta dm
                LEFT JOIN documents d ON d.doc_id = dm.id
                GROUP BY dm.id
                ORDER BY dm.created_at DESC
            """)
            rows = await cur.fetchall()
            return [
                {"id": r[0], "filename": r[1], "created_at": str(r[2]), "chunk_count": r[3]}
                for r in rows
            ]


@app.post("/upload")
async def upload(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    # Duplicate check — same filename already in the library
    async with get_pool().connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT id FROM documents_meta WHERE filename = %s", (file.filename,))
            existing = await cur.fetchone()
    if existing:
        raise HTTPException(
            status_code=409,
            detail={"message": f"'{file.filename}' is already in your library.", "doc_id": existing[0]},
        )

    file_bytes = await file.read()
    try:
        text = parse_pdf(file_bytes)
    except Exception:
        raise HTTPException(status_code=422, detail="Could not parse PDF — file may be corrupt or image-only.")

    if not text.strip():
        raise HTTPException(status_code=422, detail="No extractable text found in PDF.")

    doc_id = await create_document(file.filename)
    chunks = chunk_smart(text, chunk_size=500, overlap=50)
    vectors = await embed_chunks(chunks)
    await store_chunks(chunks, vectors, doc_id)

    return {"doc_id": doc_id, "chunk_count": len(chunks), "status": "ready"}


@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: int, user: dict = Depends(get_current_user)):
    async with get_pool().connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM messages WHERE doc_id = %s", (doc_id,))
            await cur.execute("DELETE FROM documents WHERE doc_id = %s", (doc_id,))
            await cur.execute("DELETE FROM documents_meta WHERE id = %s", (doc_id,))
            return {"status": "deleted"}


async def _require_document_exists(doc_id: int) -> None:
    async with get_pool().connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT 1 FROM documents_meta WHERE id = %s", (doc_id,))
            if (await cur.fetchone()) is None:
                raise HTTPException(status_code=404, detail="Document not found.")


# Splits Claude's numbered-list output ("1. Question one\n2. Question two")
# into a clean array. Claude sometimes prepends a markdown heading (e.g.
# "# Discussion Questions") despite the prompt asking for only the list —
# _LIST_ITEM_MARKER distinguishes a real list entry (has a number/bullet
# prefix) from stray text, and lines without a marker are only kept if
# they end in "?", since these are specifically meant to be questions.
_LIST_ITEM_MARKER = re.compile(r"^\s*(\d+[.)]|[-*•])\s*")


def _parse_numbered_list(text: str) -> list[str]:
    items = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        match = _LIST_ITEM_MARKER.match(line)
        if match:
            items.append(line[match.end():].strip())
        elif line.endswith("?"):
            items.append(line)
    return items


@app.post("/documents/{doc_id}/summary")
async def summarize_document(doc_id: int, user: dict = Depends(get_current_user)):
    await _require_document_exists(doc_id)
    chunks = await get_all_chunks(doc_id, limit=40)
    if not chunks:
        raise HTTPException(status_code=422, detail="Document has no content to summarize.")
    context = "\n\n".join(chunks)

    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=f"{SYSTEM_PROMPT_SUMMARY}\n\n{context}",
        messages=[{"role": "user", "content": "Summarize this document."}],
    )
    return {"summary": response.content[0].text}


@app.post("/documents/{doc_id}/discussion-questions")
async def generate_discussion_questions(doc_id: int, user: dict = Depends(get_current_user)):
    await _require_document_exists(doc_id)
    chunks = await get_all_chunks(doc_id, limit=40)
    if not chunks:
        raise HTTPException(status_code=422, detail="Document has no content to generate questions from.")
    context = "\n\n".join(chunks)

    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=f"{SYSTEM_PROMPT_DISCUSSION_QUESTIONS}\n\n{context}",
        messages=[{"role": "user", "content": "Generate discussion questions for this document."}],
    )
    return {"questions": _parse_numbered_list(response.content[0].text)}
