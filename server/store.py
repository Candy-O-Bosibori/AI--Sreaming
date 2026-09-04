# ============================================================
# store.py — Save chunks + their embedding vectors to PostgreSQL
# ============================================================
# Two functions:
#   create_document(filename) → registers a new document, returns its id
#   store_chunks(chunks, vectors, doc_id) → stores all chunks for that document
#
# Always call create_document() first to get a doc_id, then pass
# that doc_id into store_chunks().
# ============================================================

from db import get_pool


async def create_document(filename: str) -> int:
    """
    Register a new document in documents_meta and return its ID.

    This must be called before store_chunks() — you need a doc_id
    to attach chunks to. The doc_id is the auto-incremented primary
    key that PostgreSQL assigns when the row is inserted.

    Args:
        filename: The original filename, e.g. "paper.pdf".

    Returns:
        The new document's integer ID.
    """
    async with get_pool().connection() as conn:
        async with conn.cursor() as cur:
            # RETURNING id tells PostgreSQL to give back the new row's id
            # immediately after the INSERT, without needing a second query.
            await cur.execute(
                "INSERT INTO documents_meta (filename) VALUES (%s) RETURNING id",
                (filename,),
            )
            row = await cur.fetchone()
            return row[0]


async def store_chunks(chunks: list[str], vectors: list[list[float]], doc_id: int) -> None:
    """
    Insert a list of text chunks and their vectors into the database,
    all linked to the given document ID.

    Args:
        chunks:  List of text strings from chunker.py.
        vectors: List of 1536-float vectors from embedder.py.
                 Must be the same length as chunks.
        doc_id:  The document ID from create_document() — links every
                 chunk back to its source document.

    Example:
        doc_id = await create_document("paper.pdf")
        await store_chunks(["chunk one", "chunk two"], [vec1, vec2], doc_id)
    """
    async with get_pool().connection() as conn:
        async with conn.cursor() as cur:
            # executemany pipelines all rows in one round-trip-efficient batch
            # (psycopg v3's async pipeline mode), rather than one INSERT per
            # chunk waited on individually.
            await cur.executemany(
                "INSERT INTO documents (content, embedding, doc_id) VALUES (%s, %s::vector, %s)",
                [(chunk, str(vector), doc_id) for chunk, vector in zip(chunks, vectors)],
            )
            print(f"Stored {len(chunks)} chunks for doc_id={doc_id}.")
