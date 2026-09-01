# EphRead → Production-Ready Pilot for Williams Students

## Context

EphRead is a working RAG chat prototype: students upload a PDF, it's chunked, embedded (OpenAI), and stored in Postgres/pgvector on Supabase; a FastAPI backend does retrieval + streams a Claude answer over SSE; a React/Vite frontend renders the chat. This all works today (`server/main.py`, `server/query.py`, `server/store.py`, `client/src/components/ChatWindow.jsx`).

What's missing before this can be a real, safe-to-share product for Williams students:

1. **No auth at all.** Every endpoint is open to anyone with the URL. There's no concept of "a student" anywhere in the schema.
2. **No student-specific study features beyond raw Q&A** — no dedicated summary generation, no discussion-question generation.
3. **A 3-day auto-expiry** (`server/main.py` `cleanup_loop`) that was fine for a disposable prototype but would silently delete a shared course library.

This is a side project without confirmed adoption yet, so the mandate is: **build the cheapest version that is still real and safe**, using infra already in place (Supabase) rather than adding new paid services, and defer scaling/monitoring work until there's usage signal.

**Confirmed product decisions:**
- Auth: Google OAuth only, restricted to `@williams.edu` addresses, via **Supabase Auth** (already using Supabase for Postgres — this is free and reuses existing infra).
- The PDF library is **shared** — any logged-in student sees and can query every uploaded document (a study commons, not private folders).
- **Chat history is private per student per document** — same shared PDF, but each student's own Q&A thread is visible only to them.
- **No blob/object storage** — keep today's behavior of discarding the raw PDF after text extraction (only chunks + vectors persist). This avoids Railway's ephemeral-disk problem and avoids a new paid storage service entirely.
- Two new study features: **document summaries** and **discussion-question generation**, as first-class features (not just chat prompts).
- Remove/replace the 3-day auto-expiry now that this is a persistent shared library, not throwaway session data.
- Recruiter/portfolio visibility is a separate, non-blocking concern: the `@williams.edu` gate is built for real students, not adjusted for outside viewers. A public repo + README + demo video/screenshots is the intended way to show this off — not a bypass in the auth logic.

**Known follow-up, explicitly deferred (not part of this build):**
- Large-PDF handling. A 500-page PDF produces ~2,500–3,000 chunks. Two risks: (1) `POST /upload` processes synchronously today (parse → chunk → embed → store in one request) and will likely time out on a document that large; (2) storage adds up fast — ~20MB per 500-page PDF, so roughly 25 such PDFs would fill Supabase's free 500MB tier. Revisit with either async/background upload processing, a page/size cap at upload time, or both — once the core app below is built and there's a sense of real usage patterns.

---

## 1. Auth — Supabase Auth + Google OAuth restricted to @williams.edu

**Why Supabase Auth:** the project already runs Postgres on Supabase. Supabase Auth is bundled free (up to 50k MAU), issues standard JWTs, and supports Google as an OAuth provider — no new vendor, no new bill.

**Setup (Supabase dashboard, no code):**
- Enable the Google provider in Supabase Auth settings.
- **Enforce `@williams.edu` in two places (defense in depth) — don't rely on Google alone**, since students may use personal Gmail too:
  1. **Authoritative layer — Supabase "Before User Created" auth hook** (a Postgres function under Auth → Hooks) that rejects sign-ups where `email` doesn't end in `@williams.edu`. This blocks non-Williams accounts at the source.
  2. **Defense-in-depth layer — the FastAPI JWT dependency** (below) also asserts the email domain on every request, closing any gap if the Supabase hook is ever misconfigured or bypassed.

**Backend (`server/`):**
- Add `server/auth.py` with a FastAPI dependency `get_current_user`:
  ```python
  from fastapi import Header, HTTPException
  import jwt  # PyJWT

  SUPABASE_JWT_SECRET = os.environ["SUPABASE_JWT_SECRET"]  # Project Settings → API

  def get_current_user(authorization: str = Header(...)) -> dict:
      token = authorization.removeprefix("Bearer ").strip()
      try:
          payload = jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated")
      except jwt.PyJWTError:
          raise HTTPException(status_code=401, detail="Invalid or expired session.")
      email = payload.get("email", "")
      if not email.endswith("@williams.edu"):
          raise HTTPException(status_code=403, detail="Access restricted to @williams.edu accounts.")
      return {"id": payload["sub"], "email": email}
  ```
  Add `pyjwt` to `server/requirements.txt`.
- Apply via `Depends(get_current_user)` on every data-serving route: `POST /chat`, `GET /history`, `POST /upload`, `GET /documents`, `DELETE /documents/{id}` — the whole API gates behind auth since there's no anonymous use case.
- **Drop the legacy `GET /ask` endpoint entirely** rather than gating it — it's dead debug code that duplicates `/chat` without doc scoping.
- No separate `users` table needed — rely on Supabase's built-in `auth.users` as the source of truth; the JWT's `sub` claim is that UUID, and your own tables can FK straight to `auth.users(id)` since it's the same Postgres database.
- CORS needs no change — `allow_headers=["*"]` already covers `Authorization` (`server/main.py`).

**Frontend (`client/`):**
- Add `@supabase/supabase-js`; new `client/src/lib/supabase.js` creates a client from `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` env vars (anon key is safe client-side).
- New `client/src/components/Login.jsx` — single "Sign in with Google" button calling `supabase.auth.signInWithOAuth({ provider: 'google' })`. Supabase's client handles the OAuth redirect and session persistence (localStorage) automatically — no manual token plumbing.
- `App.jsx`: gate on `supabase.auth.getSession()` + `onAuthStateChange`; render `Login` when no session, the existing app shell otherwise.
- Add `client/src/lib/api.js` — an `apiFetch(path, opts)` wrapper that injects `Authorization: Bearer <access_token>` from `supabase.auth.getSession()`. Swap the existing raw `fetch('/api/...')` calls in `App.jsx`, `ChatWindow.jsx`, `UploadPage.jsx` to use it (mechanical find/replace).
- If the backend returns 403, show "This app is for Williams College students only" and sign the user out.

---

## 2. Database schema changes

No Alembic yet, and given the app is still pre-launch, **keep hand-editing `server/setup.sql`** rather than introducing a migrations tool now — Alembic is worth adding once the schema stabilizes post-launch, not before.

Changes to `server/setup.sql`:
- Add `user_id UUID NOT NULL REFERENCES auth.users(id)` to the `messages` table — this is the only table that needs per-user scoping, since documents are shared.
- Drop the `last_accessed_at`-driven expiry columns/logic, or keep the column but stop using it for deletion (see §5).
- No changes needed to `documents_meta` or `documents` (chunks/vectors) — they stay global/shared as designed.

Update `server/history.py`:
- `save_message(doc_id, role, content, user_id)` — add `user_id` to the INSERT.
- `get_history(doc_id, user_id, limit=6)` — add `WHERE doc_id = %s AND user_id = %s` so each student only sees their own thread.

Update `server/main.py`:
- `stream_chat` and `/history` need `user_id` threaded through from the new `get_current_user` dependency.
- Optionally add `uploaded_by UUID REFERENCES auth.users(id)` to `documents_meta` for a future "uploaded by X" UI credit — not required for scoping, treat as deferred/optional.

---

## 3. New endpoints: summaries + discussion questions

Both should be **plain JSON, not SSE-streamed** — these are single structured outputs (a summary, a list of N questions) generated once per click, not a long conversational reply the user watches token-by-token. Streaming would add frontend complexity (parsing a partial list mid-stream) for no real UX benefit; a brief loading state is fine. This deliberately diverges from `/chat`'s SSE pattern for a good reason, not by accident.

- New `server/prompts.py` — centralize system prompts here (move `SYSTEM_PROMPT_DEFAULT`/`SYSTEM_PROMPT_DEBATE` out of `main.py` too, so routing logic stays separate from prompt text):
  ```python
  SYSTEM_PROMPT_SUMMARY = (
      "Summarize the document below in 4-6 concise bullet points covering its main "
      "argument, key findings, and conclusions. Use only the information given."
  )
  SYSTEM_PROMPT_DISCUSSION_QUESTIONS = (
      "Generate 5 discussion questions a student could bring to a seminar/class "
      "discussion about the document below. Questions should probe assumptions, "
      "implications, and points of debate — not simple recall. "
      "Return ONLY a numbered list, one question per line."
  )
  ```

**`POST /documents/{doc_id}/summary`** and **`POST /documents/{doc_id}/discussion-questions`**
- Retrieval: a summary/question-set needs broad document coverage, not query-similarity search, so don't reuse `query_similar` (it needs a query string to embed against). Add a helper (e.g. in `server/query.py` or `server/store.py`, following the existing `get_conn()`/try-finally pattern) — `get_all_chunks(doc_id, limit=40)`: `SELECT content FROM documents WHERE doc_id = %s ORDER BY id LIMIT %s`. For a typical ~20-page course PDF (40-80 chunks × 500 chars) this comfortably fits Haiku's context window at low cost. For unusually long documents, sample evenly across the doc rather than just the first N chunks, so the summary isn't biased toward the introduction.
- Call `client.messages.create` (non-streaming Anthropic call, same `claude-haiku-4-5-20251001` model as chat) with the relevant prompt + retrieved context; return `{"summary": text}` or `{"questions": [...]}` (split Claude's numbered-list output on newlines server-side so the frontend gets a clean array).
- Both behind `Depends(get_current_user)` like other routes, but **not** scoped by `user_id` and **not** saved to `messages` — they're stateless, shared-library-level operations on the document, not private chat turns. (Caching a summary on `documents_meta` to avoid regenerating on every click is a reasonable later optimization — skip it for now per the "don't over-engineer" guidance.)

"Get clarification" is not a new endpoint — it's satisfied by the existing chat + Debate mode already in the app; no backend change needed there.

---

## 4. Frontend changes

- **Login gate** as described in §1.
- **Sidebar (`client/src/components/Sidebar.jsx`)**: structurally already correct for a shared library — it lists all `docs` from `GET /documents` with no per-user filtering, and that endpoint already returns everything unscoped. Only change needed is **cosmetic**: update the "No documents yet" empty state and section header ("Documents" → "Library" or similar) to signal this is a shared space, not "your" documents.
- **ChatWindow (`client/src/components/ChatWindow.jsx`)**: add two buttons in the sub-header row, next to the existing Debate toggle — "Summarize" and "Discussion Questions." Each calls the corresponding new endpoint, shows a loading state on the button (reuse the pattern already used for the `streaming`/`UploadPage.jsx` `loading` states), and renders the JSON result as a message-like card using the existing `ReactMarkdown` rendering block — tagged with a small label (e.g. "Summary") so students don't mistake it for a saved chat turn, since these aren't persisted.
- Add a sign-out control (e.g. in `Sidebar.jsx`'s header, next to the dark-mode toggle) calling `supabase.auth.signOut()`.

---

## 5. Remove the 3-day auto-expiry

`server/main.py`'s `EXPIRY_DAYS = 3` and `cleanup_loop()` were designed for an ephemeral single-session prototype; they're actively wrong for a persistent shared library — a document uploaded three days ago that nobody's queried since would get silently, permanently deleted mid-semester along with its chunks.

**Remove `cleanup_loop()`, `EXPIRY_DAYS`, and the `lifespan` background-task registration entirely**, rather than just lengthening the interval — there's no natural expiry policy for course material that should hold across a semester, and a silent background deletion job is exactly the kind of surprising behavior to avoid in something students rely on for actual coursework. `history.py`'s `touch_document()` can also be removed if nothing else needs `last_accessed_at` afterward — safe to leave the column even if the cleanup job goes, in case a future manual "archive old semester" admin action wants it (that would be an explicit admin-triggered action, not a silent timer — out of scope here). Also delete the now-obsolete `test_expiry_days_is_positive_int` test in `server/tests/test_chat.py`.

---

## 6. Sequencing (cheap-validation priority)

1. **Auth first** — nothing else matters until the app isn't wide open. Supabase Auth + Google OAuth + `@williams.edu` gate on backend and frontend.
2. **Schema + scoping** — add `user_id` to `messages`, update `history.py`, thread auth through `/chat` and `/history`.
3. **Remove auto-expiry** — one small change, immediately makes the shared-library model correct.
4. **Summarize endpoint** — highest-value new feature, most directly "prepare for class."
5. **Discussion-questions endpoint** — same pattern as summarize, should be fast once #4 is done.
6. **Frontend polish** — login screen, sign-out, new action buttons.

**Cost reality check:** All of this fits Supabase's free tier (Postgres + Auth) at Williams-pilot scale — no new bill. The only ongoing variable cost is OpenAI embedding calls (per PDF upload) and Anthropic tokens (per chat/summary/question-generation call), both already true of the app today; a handful of students piloting this costs cents to low dollars a month. Don't add rate limiting, usage caps, or billing alerts yet — revisit only if real adoption happens.

---

## 7. Testing

Extend `server/tests/test_chat.py`'s existing pattern (FastAPI `TestClient`, unit-style checks on request/response shape without a live DB, `@pytest.mark.integration` for anything needing one):
- Auth-gated routes: assert `401` when `Authorization` is missing on `/chat`, `/upload`, `/history`, `/documents`, `DELETE /documents/{id}`.
- Domain restriction: craft a JWT with a non-`@williams.edu` email (signed with a test secret) and call `get_current_user` directly — assert `403`. This is a pure unit test, no TestClient or live Supabase project needed.
- New endpoint shape tests: `/documents/{id}/summary` and `/documents/{id}/discussion-questions` return proper `401`/`422` for missing auth or bad `doc_id`.
- Integration tests (marked `@pytest.mark.integration`, run manually per existing convention): full flow with a valid JWT — chat, verify `messages.user_id` is set, verify a second user can't see the first user's history for the same `doc_id` (directly tests the private-per-student-history requirement). Also test summary/discussion-questions against `server/seed.py` data.

**Playwright cruft — flag, don't fix here.** `playwright.config.js` (`testDir: './tests'`) and `playwright.config.ts` (`testDir: './e2e'`) conflict, and the specs in `tests/` (`example.spec.js`, `test-1.spec.ts`) are unrelated boilerplate (hit playwright.dev and an unrelated site) — not real coverage of this app. Worth a follow-up pass (pick one config, delete the other, write real specs for login/upload/chat/summary flows) once auth exists to test against — explicitly deferred, not needed for validation-readiness.

---

## Verification

- Local: run `uvicorn main:app --reload` + `npm run dev`, sign in with a `@williams.edu` test Google account, confirm a non-Williams email is rejected.
- Upload a PDF, confirm it appears in the shared sidebar for a second test account.
- Chat as two different accounts on the same document, confirm each sees only their own history via `GET /history`.
- Hit `/documents/{id}/summary` and `/documents/{id}/discussion-questions`, confirm well-formed JSON output.
- Run `pytest server/tests -v` for the auth-gated endpoint tests.
- Confirm documents/chunks are no longer deleted after 3 days (inspect `cleanup_loop` removal / Supabase table row counts over time).
