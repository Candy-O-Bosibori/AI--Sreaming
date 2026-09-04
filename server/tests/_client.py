# ============================================================
# _client.py — Shared TestClient construction for the test suite
# ============================================================
# TestClient(app) used as a plain object never runs FastAPI's lifespan
# (see main.py) — so the async DB connection pool (db.py) never opens,
# and any route touching the database fails with psycopg_pool.PoolClosed.
#
# Entering the client as a context manager triggers lifespan startup
# within the same event loop TestClient itself uses for requests later
# (this matters — an AsyncConnectionPool is bound to the event loop it
# was opened in; opening it via a separate asyncio.run() call, as an
# earlier version of this fix tried, hangs because that loop is gone
# by the time a real request needs the pool).
#
# __enter__() is called once, at import time, and never explicitly
# exited — the pool stays open for the life of the test process, which
# is fine for a test run (it's an in-process resource, not something
# that needs cleanup mid-suite).
# ============================================================

from fastapi.testclient import TestClient

from main import app


def make_client() -> TestClient:
    return TestClient(app).__enter__()
