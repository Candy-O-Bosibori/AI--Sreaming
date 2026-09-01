import { useState } from 'react'

export default function Sidebar({ docs, activeDocId, onNewChat, onSelectDoc, onDeleteDoc, dark, onToggleDark, open, userEmail, onSignOut }) {
  const [confirmId, setConfirmId] = useState(null)

  function handleDelete(e, id) {
    e.stopPropagation()
    if (confirmId === id) {
      onDeleteDoc(id)
      setConfirmId(null)
    } else {
      setConfirmId(id)
    }
  }

  function cancelDelete(e) {
    e.stopPropagation()
    setConfirmId(null)
  }

  return (
    <aside className={`
      flex-shrink-0 flex flex-col h-full
      w-64
      bg-brand-purple dark:bg-[#1a0030]
      border-r border-white/10 dark:border-brand-purple/30
      transition-transform duration-300 ease-in-out
      fixed md:relative inset-y-0 left-0 z-30 md:z-auto
      ${open ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
    `}>

      {/* Header */}
      <div className="flex items-center justify-between px-4 py-4 border-b border-white/10 flex-shrink-0">
        <span className="text-white font-bold tracking-tight text-lg select-none">EphRead</span>
        <button
          onClick={onToggleDark}
          className="w-8 h-8 rounded-lg flex items-center justify-center text-white/60 hover:text-brand-gold hover:bg-white/10 transition-all duration-150"
          title="Toggle dark mode"
        >
          {dark ? (
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364l-.707.707M6.343 17.657l-.707.707M18.364 17.657l-.707-.707M6.343 6.343l-.707-.707M12 8a4 4 0 100 8 4 4 0 000-8z" />
            </svg>
          ) : (
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
            </svg>
          )}
        </button>
      </div>

      {/* New chat button */}
      <div className="px-3 pt-3 pb-2 flex-shrink-0">
        <button
          onClick={onNewChat}
          className="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl border border-white/20 text-white/80 hover:bg-white/10 hover:text-white hover:border-white/30 transition-all duration-150 text-sm font-medium"
        >
          <svg className="w-4 h-4 text-brand-gold" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New chat
        </button>
      </div>

      {/* Document list */}
      <div className="flex-1 overflow-y-auto px-3 pb-4 min-h-0">
        {docs.length > 0 && (
          <p className="text-white/30 text-[10px] font-semibold uppercase tracking-wider px-2 pt-3 pb-1.5">
            Shared Library
          </p>
        )}
        <div className="space-y-0.5">
          {docs.map(doc => (
            <div
              key={doc.id}
              className={`group relative flex items-center rounded-lg transition-all duration-150
                ${doc.id === activeDocId ? 'bg-white/20' : 'hover:bg-white/10'}
                ${confirmId === doc.id ? 'bg-red-500/20' : ''}
              `}
            >
              {confirmId === doc.id ? (
                /* Inline delete confirmation */
                <div className="flex items-center justify-between w-full px-3 py-2 gap-2">
                  <span className="text-xs text-white/80 truncate">Delete?</span>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button
                      onClick={(e) => handleDelete(e, doc.id)}
                      className="text-xs bg-red-500 hover:bg-red-400 text-white px-2 py-0.5 rounded font-medium transition-colors"
                    >
                      Yes
                    </button>
                    <button
                      onClick={cancelDelete}
                      className="text-xs text-white/60 hover:text-white px-2 py-0.5 rounded transition-colors"
                    >
                      No
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <button
                    onClick={() => onSelectDoc(doc.id, doc.filename)}
                    title={doc.filename}
                    className={`flex-1 min-w-0 text-left px-3 py-2 text-sm truncate
                      ${doc.id === activeDocId ? 'text-white font-medium' : 'text-white/55 group-hover:text-white'}
                    `}
                  >
                    {doc.filename.replace(/\.pdf$/i, '')}
                  </button>
                  <button
                    onClick={(e) => handleDelete(e, doc.id)}
                    className="flex-shrink-0 opacity-0 group-hover:opacity-100 mr-2 p-1 text-white/40 hover:text-red-300 rounded transition-all duration-150"
                    title="Delete document"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </>
              )}
            </div>
          ))}
        </div>

        {docs.length === 0 && (
          <p className="text-white/25 text-xs px-2 pt-4">
            The library is empty — upload a PDF to share it with everyone.
          </p>
        )}
      </div>

      {/* Account footer */}
      {userEmail && (
        <div className="px-3 py-3 border-t border-white/10 flex-shrink-0">
          <div className="flex items-center justify-between gap-2 px-2">
            <span className="text-xs text-white/50 truncate" title={userEmail}>
              {userEmail}
            </span>
            <button
              onClick={onSignOut}
              className="flex-shrink-0 text-xs font-medium text-white/50 hover:text-brand-gold transition-colors"
            >
              Sign out
            </button>
          </div>
        </div>
      )}
    </aside>
  )
}
