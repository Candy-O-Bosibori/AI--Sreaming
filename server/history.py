from typing import List, Dict

from db import get_pool


async def save_message(doc_id: int, user_id: str, role: str, content: str) -> None:
    async with get_pool().connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO messages (doc_id, user_id, role, content) VALUES (%s, %s, %s, %s)",
                (doc_id, user_id, role, content),
            )


async def get_history(doc_id: int, user_id: str, limit: int = 6) -> List[Dict]:
    """
    Fetch this student's own chat history for a document.

    Documents are a shared library, but chat history is private per
    student — scoping by both doc_id and user_id means one student
    never sees another's questions/answers on the same document.
    """
    async with get_pool().connection() as conn:
        async with conn.cursor() as cur:
            # Fetch the most recent `limit` messages, then return them oldest-first
            # so Claude sees the conversation in chronological order.
            await cur.execute(
                """
                SELECT role, content FROM (
                    SELECT role, content, created_at
                    FROM messages WHERE doc_id = %s AND user_id = %s
                    ORDER BY created_at DESC LIMIT %s
                ) sub ORDER BY created_at ASC
                """,
                (doc_id, user_id, limit),
            )
            rows = await cur.fetchall()
            return [{"role": row[0], "content": row[1]} for row in rows]


async def touch_document(doc_id: int) -> None:
    async with get_pool().connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE documents_meta SET last_accessed_at = NOW() WHERE id = %s",
                (doc_id,),
            )
