# ============================================================
# db.py — Async Postgres connection pool
# ============================================================
# One AsyncConnectionPool is created once, at app startup (see main.py's
# lifespan handler), and shared across every request. Routes borrow a
# connection for the duration of one query and return it, instead of
# opening/closing a brand-new TCP connection per query — the previous
# psycopg2-based version did the latter, which also blocked FastAPI's
# event loop (psycopg2 has no async mode at all).
#
# Usage in a route:
#   async with get_pool().connection() as conn:
#       async with conn.cursor() as cur:
#           await cur.execute("SELECT ...", (...))
#           rows = await cur.fetchall()
# ============================================================

import os

from psycopg_pool import AsyncConnectionPool

env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key, value)


def _connection_string() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    # Local fallback using individual DB_* vars, in libpq keyword=value form
    # (psycopg accepts this format directly, same as a URI).
    return (
        f"host={os.environ['DB_HOST']} "
        f"port={os.environ.get('DB_PORT', '5432')} "
        f"dbname={os.environ['DB_NAME']} "
        f"user={os.environ['DB_USER']} "
        f"password={os.environ['DB_PASSWORD']}"
    )


# Created lazily, opened explicitly during FastAPI's startup (lifespan),
# closed during shutdown. Not opened at import time — pool creation does
# real connection setup work that belongs in an async startup hook, not
# at module-import time (which runs before an event loop exists).
_pool: AsyncConnectionPool | None = None


def get_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(
            _connection_string(),
            open=False,
            # prepare_threshold=None disables psycopg's automatic server-side
            # statement preparation. We connect through Supabase's Transaction
            # Pooler (see DATABASE_URL), which recycles a physical connection
            # across different logical sessions between transactions — a
            # prepared statement created in one session can collide with
            # another's on the same recycled connection, raising
            # DuplicatePreparedStatement. Disabling prepare is the documented
            # fix for psycopg v3 behind a transaction-mode pooler (PgBouncer/
            # Supavisor); this app's queries aren't repeated often enough
            # per-connection for prepared-statement caching to matter anyway.
            kwargs={"prepare_threshold": None},
        )
    return _pool


async def open_pool() -> None:
    await get_pool().open()


async def close_pool() -> None:
    if _pool is not None:
        await _pool.close()
