# ============================================================
# main.py — FastAPI server
# ============================================================

import os

import anthropic
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth import get_current_user
from chunker import chunk_smart
from db import get_conn
from embedder import embed_chunks
from history import get_history, save_message, touch_document
from parse_pdf import parse_pdf
from query import query_similar
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


app = FastAPI()

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


SYSTEM_PROMPT_DEFAULT = (
    "Answer the user's question directly using only the information below. "
    "Do not say 'based on the context' or similar phrases — just answer. "
    "If the answer is not present, say so in one sentence."
)

SYSTEM_PROMPT_DEBATE = (
    "You will be given a document and a question. "
    "For any argument, claim, or position in the document relevant to the question, "
    "steelman BOTH the supporting and opposing positions with equal rigour. "
    "Present each side fairly before giving your own conclusion. "
    "Use only the information below — do not introduce outside knowledge."
)


# ── Streaming generator for /chat ─────────────────────────────────────
async def stream_chat(message: str, doc_id: int, user_id: str, debate_mode: bool = False):
    touch_document(doc_id)
    history = get_history(doc_id, user_id, limit=6)
    chunks = query_similar(message, top_k=12, doc_id=doc_id)
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

    save_message(doc_id, user_id, "user", message)
    save_message(doc_id, user_id, "assistant", "".join(full_reply))
    yield "data: [DONE]\n\n"


# ── Endpoints ─────────────────────────────────────────────────────────
# Every route below requires a valid @williams.edu Supabase session
# (see auth.py) — there is no anonymous/public use of this API.

@app.post("/chat")
async def chat(req: ChatRequest, user: dict = Depends(get_current_user)):
    return StreamingResponse(
        stream_chat(req.message, req.doc_id, user["id"], req.debate_mode),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/history")
async def history(doc_id: int, user: dict = Depends(get_current_user)):
    return get_history(doc_id, user["id"])


@app.get("/documents")
def list_documents(user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT dm.id, dm.filename, dm.created_at, COUNT(d.id) AS chunk_count
            FROM documents_meta dm
            LEFT JOIN documents d ON d.doc_id = dm.id
            GROUP BY dm.id
            ORDER BY dm.created_at DESC
        """)
        rows = cur.fetchall()
        return [
            {"id": r[0], "filename": r[1], "created_at": str(r[2]), "chunk_count": r[3]}
            for r in rows
        ]
    finally:
        conn.close()


@app.post("/upload")
async def upload(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    # Duplicate check — same filename already in the library
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM documents_meta WHERE filename = %s", (file.filename,))
        existing = cur.fetchone()
    finally:
        conn.close()
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

    doc_id = create_document(file.filename)
    chunks = chunk_smart(text, chunk_size=500, overlap=50)
    vectors = embed_chunks(chunks)
    store_chunks(chunks, vectors, doc_id)

    return {"doc_id": doc_id, "chunk_count": len(chunks), "status": "ready"}


@app.delete("/documents/{doc_id}")
def delete_document(doc_id: int, user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM messages WHERE doc_id = %s", (doc_id,))
        cur.execute("DELETE FROM documents WHERE doc_id = %s", (doc_id,))
        cur.execute("DELETE FROM documents_meta WHERE id = %s", (doc_id,))
        conn.commit()
        return {"status": "deleted"}
    finally:
        conn.close()
