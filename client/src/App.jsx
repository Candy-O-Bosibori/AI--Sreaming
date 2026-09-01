import { useState, useEffect } from 'react'
import Sidebar from './components/Sidebar'
import UploadPage from './components/UploadPage'
import ChatWindow from './components/ChatWindow'
import Login from './components/Login'
import { supabase } from './lib/supabase'
import { apiFetch } from './lib/api'

function useDarkMode() {
  const [dark, setDark] = useState(() => localStorage.getItem('darkMode') === 'true')
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    localStorage.setItem('darkMode', dark)
  }, [dark])
  return [dark, setDark]
}

const REQUIRED_EMAIL_DOMAIN = '@williams.edu'

export default function App() {
  const [dark, setDark] = useDarkMode()
  const [docs, setDocs] = useState([])
  const [sidebarOpen, setSidebarOpen] = useState(false)

  // ── Auth state ────────────────────────────────────────────────────
  // authChecked distinguishes "still checking for an existing session"
  // from "checked, and there isn't one" so we don't flash the login
  // screen before Supabase has had a chance to restore a session.
  const [session, setSession] = useState(null)
  const [authChecked, setAuthChecked] = useState(false)
  const [accessDenied, setAccessDenied] = useState(false)

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session)
      setAuthChecked(true)
    })

    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session)
      setAuthChecked(true)
    })

    return () => listener.subscription.unsubscribe()
  }, [])

  // Defense-in-depth: the backend already rejects non-@williams.edu tokens
  // (see server/auth.py), but checking here too means a non-Williams user
  // never even sees the app shell flash before being signed back out.
  useEffect(() => {
    const email = session?.user?.email || ''
    if (session && !email.toLowerCase().endsWith(REQUIRED_EMAIL_DOMAIN)) {
      setAccessDenied(true)
      supabase.auth.signOut()
    }
  }, [session])

  function signOut() {
    supabase.auth.signOut()
  }

  const [docId, setDocId] = useState(() => {
    const saved = localStorage.getItem('docId')
    return saved ? Number(saved) : null
  })
  const [filename, setFilename] = useState(
    () => localStorage.getItem('docFilename') || ''
  )
  const [view, setView] = useState(() =>
    localStorage.getItem('docId') ? 'chat' : 'upload'
  )

  function refreshDocs() {
    apiFetch('/api/documents')
      .then(r => r.ok ? r.json() : Promise.reject(new Error(`${r.status}`)))
      .then(docs => Array.isArray(docs) ? setDocs(docs) : setDocs([]))
      .catch(() => setDocs([]))
  }

  useEffect(() => {
    if (session) refreshDocs()
  }, [session])

  function openDoc(id, name) {
    setDocId(id)
    setFilename(name)
    setView('chat')
    localStorage.setItem('docId', id)
    localStorage.setItem('docFilename', name)
    refreshDocs()
    setSidebarOpen(false)
  }

  function newChat() {
    setDocId(null)
    setFilename('')
    setView('upload')
    localStorage.removeItem('docId')
    localStorage.removeItem('docFilename')
    setSidebarOpen(false)
  }

  function selectDoc(id, name) {
    setDocId(id)
    setFilename(name)
    setView('chat')
    localStorage.setItem('docId', id)
    localStorage.setItem('docFilename', name)
    setSidebarOpen(false)
  }

  async function deleteDoc(id) {
    await apiFetch(`/api/documents/${id}`, { method: 'DELETE' })
    refreshDocs()
    if (id === docId) {
      setDocId(null)
      setFilename('')
      setView('upload')
      localStorage.removeItem('docId')
      localStorage.removeItem('docFilename')
    }
  }

  if (!authChecked) {
    return (
      <div className="h-screen flex items-center justify-center bg-white dark:bg-brand-dark-bg">
        <span className="w-8 h-8 border-[3px] border-brand-purple/30 border-t-brand-purple rounded-full animate-spin" />
      </div>
    )
  }

  if (!session) {
    return <Login accessDenied={accessDenied} />
  }

  return (
    <div className="flex h-screen bg-white dark:bg-brand-dark-bg overflow-hidden">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="md:hidden fixed inset-0 bg-black/50 z-20"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <Sidebar
        docs={docs}
        activeDocId={docId}
        onNewChat={newChat}
        onSelectDoc={selectDoc}
        onDeleteDoc={deleteDoc}
        dark={dark}
        onToggleDark={() => setDark(d => !d)}
        open={sidebarOpen}
        userEmail={session.user?.email}
        onSignOut={signOut}
      />

      {/* Main area */}
      <div className="flex-1 min-w-0 flex flex-col overflow-hidden relative">
        {/* Mobile hamburger */}
        <button
          className="md:hidden absolute top-3 left-3 z-10 bg-brand-purple text-white w-8 h-8 rounded-lg flex items-center justify-center shadow-purple-sm"
          onClick={() => setSidebarOpen(true)}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>

        {view === 'chat' && docId ? (
          <ChatWindow docId={docId} filename={filename} />
        ) : (
          <UploadPage onUpload={openDoc} />
        )}
      </div>
    </div>
  )
}
