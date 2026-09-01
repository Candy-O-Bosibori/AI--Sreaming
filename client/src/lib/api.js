// ============================================================
// api.js — fetch() wrapper that attaches the Supabase session token
// ============================================================
// Every call to our FastAPI backend needs `Authorization: Bearer <jwt>`
// now that all routes are auth-gated (see server/auth.py). Components
// should use apiFetch(path, opts) instead of raw fetch('/api/...').
// ============================================================

import { supabase } from './supabase'

export async function apiFetch(path, options = {}) {
  const {
    data: { session },
  } = await supabase.auth.getSession()

  const headers = new Headers(options.headers || {})
  if (session?.access_token) {
    headers.set('Authorization', `Bearer ${session.access_token}`)
  }

  return fetch(path, { ...options, headers })
}
