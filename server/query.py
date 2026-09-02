# ============================================================
# query.py — Find the most relevant chunks for a user's question
# ============================================================
# This is the "retrieval" part of RAG (Retrieval-Augmented Generation).
# The user asks a question → we embed it → we search the database
# for the chunks whose vectors are closest to the question's vector
# → we return those chunks as context for the LLM to answer from.
# ============================================================

from typing import List, Optional
from embedder import embed_chunks
from db import get_conn


def query_similar(question: str, top_k: int = 5, doc_id: Optional[int] = None) -> List[str]:
    """
    Find the top_k most relevant text chunks for a given question.

    Args:
        question: The user's question in plain English.
        top_k:    How many chunks to return (default 5).
        doc_id:   If provided, only search chunks from this document.
                  If omitted, search across all documents (Phase 1 behaviour).

    Returns:
        A list of text strings — the most relevant chunks from the database.
    """

    # Embed the question into a 1536-dim vector.
    # We pass it as a list because embed_chunks() expects a list;
    # [0] pulls the single vector back out.
    question_vector = embed_chunks([question])[0]
    vector_str = str(question_vector)

    conn = get_conn()
    try:
        cur = conn.cursor()

        if doc_id is not None:
            # Scoped search: only return chunks that belong to this document.
            # The WHERE clause filters rows BEFORE the cosine distance is ranked,
            # so we never compare against chunks from other documents.
            cur.execute(
                """
                SELECT content
                FROM documents
                WHERE doc_id = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (doc_id, vector_str, top_k),
            )
        else:
            # Unscoped search: compare against every chunk in the database.
            cur.execute(
                """
                SELECT content
                FROM documents
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (vector_str, top_k),
            )

        # fetchall() returns [("chunk text",), ...] — row[0] extracts the string.
        results = [row[0] for row in cur.fetchall()]

    finally:
        conn.close()

    return results


def get_all_chunks(doc_id: int, limit: int = 40) -> List[str]:
    """
    Fetch up to `limit` chunks for a document, in original document order
    — not ranked by similarity to any question. Used for tasks that need
    broad coverage of the whole document (summaries, discussion questions)
    rather than chunks relevant to a specific query.

    Why not query_similar() for this: similarity search needs a question
    to embed and compare against, and "summarize this document" isn't
    reliably close in embedding-space to the chunks that actually cover
    the document's full range of topics — it tends to cluster around
    whatever's most central, missing entire sections. Pulling chunks in
    document order instead guarantees real coverage.

    Args:
        doc_id: The document to fetch chunks for.
        limit:  Max chunks to return (default 40 — comfortably covers a
                typical ~20-page course PDF within Claude's context window
                at low cost; a longer document is truncated, not sampled,
                which is an accepted tradeoff for now).

    Returns:
        A list of chunk text strings, in the same order they were
        originally stored (which matches document reading order — see
        store.py's store_chunks()).
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT content FROM documents WHERE doc_id = %s ORDER BY id LIMIT %s",
            (doc_id, limit),
        )
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


# ── Quick test ────────────────────────────────────────────────────────
# Run this file directly to test: python query.py
if __name__ == "__main__":
    question = "What was the retrieval accuracy of NeuroSearch-7?"
    print(f"Question: {question}\n")

    chunks = query_similar(question, top_k=3)
    print(f"Top {len(chunks)} relevant chunks (all docs):\n")
    for i, chunk in enumerate(chunks, 1):
        print(f"--- Chunk {i} ---")
        print(chunk)
        print()
