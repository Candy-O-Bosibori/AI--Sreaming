// ============================================================
// supabase.js — Shared Supabase client for Auth (Google OAuth)
// ============================================================
// One client instance for the whole app. Supabase's client handles
// the OAuth redirect flow and persists the session in localStorage
// automatically — components just read supabase.auth.getSession()
// or subscribe via supabase.auth.onAuthStateChange().
// ============================================================

import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!supabaseUrl || !supabaseAnonKey) {
  // Fail loudly in dev rather than silently making unauthenticated requests.
  console.error(
    'Missing VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY — check client/.env'
  )
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey)
