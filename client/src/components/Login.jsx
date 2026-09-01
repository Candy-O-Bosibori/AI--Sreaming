import { useState } from 'react'
import { supabase } from '../lib/supabase'

export default function Login({ accessDenied }) {
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function signInWithGoogle() {
    setError('')
    setLoading(true)
    const { error: signInError } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: window.location.origin },
    })
    if (signInError) {
      setError(signInError.message || 'Could not start sign-in. Please try again.')
      setLoading(false)
    }
    // On success, Supabase redirects to Google and back — no further action here.
  }

  return (
    <div className="h-full bg-white dark:bg-brand-dark-bg flex items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <div className="bg-white dark:bg-brand-dark-card rounded-2xl shadow-purple-md p-8 border border-purple-100 dark:border-brand-purple text-center">
          <h1 className="text-2xl font-bold text-brand-purple dark:text-brand-gold mb-1">
            EphRead
          </h1>
          <p className="text-gray-500 dark:text-gray-400 text-sm mb-8">
            Sign in with your Williams email to access the shared reading library.
          </p>

          {accessDenied && (
            <div className="mb-6 px-4 py-3 rounded-xl bg-red-50 dark:bg-red-900/10 border border-red-200 dark:border-red-900/40">
              <p className="text-sm text-red-600 dark:text-red-400">
                This app is for Williams College students only — please sign in with a
                @williams.edu account.
              </p>
            </div>
          )}

          <button
            onClick={signInWithGoogle}
            disabled={loading}
            className="w-full flex items-center justify-center gap-3 bg-white dark:bg-white/5 border border-gray-300 dark:border-white/20 hover:bg-gray-50 dark:hover:bg-white/10 text-gray-700 dark:text-gray-200 font-medium py-3 px-6 rounded-full transition-all duration-200 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {loading ? (
              <span className="w-5 h-5 border-2 border-gray-300 border-t-brand-purple rounded-full animate-spin" />
            ) : (
              <svg className="w-5 h-5" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
              </svg>
            )}
            {loading ? 'Redirecting…' : 'Sign in with Google'}
          </button>

          {error && (
            <p className="mt-4 text-sm text-red-500">{error}</p>
          )}

          <p className="mt-6 text-xs text-gray-400">
            Access is restricted to @williams.edu accounts.
          </p>
        </div>
      </div>
    </div>
  )
}
