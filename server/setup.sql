-- ============================================================
-- setup.sql — Run this once to prepare your PostgreSQL database
-- ============================================================
-- Run with:
--   psql -U your_user -d your_database -f setup.sql
--
-- To reset everything (drops all data — note the order due to FK constraints):
--   psql -U your_user -d your_database -c "
--     DROP TABLE IF EXISTS messages;
--     DROP TABLE IF EXISTS documents;
--     DROP TABLE IF EXISTS documents_meta;"
--   psql -U your_user -d your_database -f setup.sql
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- One row per uploaded document.
-- last_accessed_at is updated every time the doc is queried via /chat.
-- The auto-expiry background task uses this to delete stale documents.
CREATE TABLE IF NOT EXISTS documents_meta (
    id               SERIAL PRIMARY KEY,
    filename         TEXT NOT NULL,
    created_at       TIMESTAMP DEFAULT NOW(),
    last_accessed_at TIMESTAMP DEFAULT NOW()
);

-- One row per text chunk from a document.
CREATE TABLE IF NOT EXISTS documents (
    id          SERIAL PRIMARY KEY,
    doc_id      INTEGER NOT NULL REFERENCES documents_meta(id),
    content     TEXT NOT NULL,
    embedding   vector(1536) NOT NULL,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- One row per chat message turn (user or assistant).
-- user_id scopes each message to the student who sent/received it —
-- documents are a shared library, but chat history is private per student.
CREATE TABLE IF NOT EXISTS messages (
    id         SERIAL PRIMARY KEY,
    doc_id     INTEGER NOT NULL REFERENCES documents_meta(id),
    user_id    UUID NOT NULL REFERENCES auth.users(id),
    role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content    TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Speeds up the common lookup: "this student's history for this document".
CREATE INDEX IF NOT EXISTS messages_doc_user_idx ON messages (doc_id, user_id);

-- IVFFlat index for fast similarity search at scale.
-- Only add this once you have at least 1000 rows — on small datasets it
-- returns 0 results because the query lands in an empty cluster.
-- Sequential scan (no index) is correct and faster below ~1000 rows.
--
-- Run this manually when your documents table has real data:
--
--   CREATE INDEX documents_embedding_idx
--       ON documents
--       USING ivfflat (embedding vector_cosine_ops)
--       WITH (lists = 100);
