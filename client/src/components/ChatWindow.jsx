import { useState, useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { apiFetch } from '../lib/api'

const SUGGESTIONS = [
  'Summarise this document in 3 bullet points',
  'What are the key findings?',
  'What questions does this raise?',
]

export default function ChatWindow({ docId, filename }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [debateMode, setDebateMode] = useState(false)
  const [error, setError] = useState('')
  const bottomRef = useRef(null)
  const textareaRef = useRef(null)

  useEffect(() => {
    apiFetch(`/api/history?doc_id=${docId}`)
      .then(r => r.json())
      .then(setMessages)
      .catch(() => {})
  }, [docId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 160) + 'px'
  }, [input])

  async function sendMessage(text = input.trim()) {
    if (!text || streaming) return
    setInput('')
    setError('')
    setMessages(prev => [...prev, { role: 'user', content: text }])
    setMessages(prev => [...prev, { role: 'assistant', content: '' }])
    setStreaming(true)

    try {
      const res = await apiFetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, doc_id: docId, debate_mode: debateMode }),
      })

      if (!res.ok) {
        const data = await res.json()
        setError(data.detail || 'Chat request failed.')
        setMessages(prev => prev.slice(0, -1))
        setStreaming(false)
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const raw = decoder.decode(value, { stream: true })
        for (const line of raw.split('\n\n')) {
          const token = line.replace(/^data: /, '')
          if (!token || token === '[DONE]') continue
          setMessages(prev => {
            const updated = [...prev]
            updated[updated.length - 1] = {
              role: 'assistant',
              content: updated[updated.length - 1].content + token,
            }
            return updated
          })
        }
      }
    } catch {
      setError('Stream interrupted. Is the server running?')
      setMessages(prev => prev.slice(0, -1))
    } finally {
      setStreaming(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="h-full bg-white dark:bg-brand-dark-bg flex flex-col overflow-hidden">

      {/* ── Slim sub-header ── */}
      <div className="flex-shrink-0 border-b border-gray-200 dark:border-brand-purple/30 px-5 py-2.5 flex items-center justify-between bg-white dark:bg-brand-dark-bg">
        <span className="text-sm text-gray-500 dark:text-gray-400 truncate max-w-[200px] md:max-w-xs pl-8 md:pl-0">
          {filename}
        </span>
        <label className="flex items-center gap-2 cursor-pointer select-none flex-shrink-0">
          <span className={`text-xs transition-colors ${debateMode ? 'text-brand-purple dark:text-brand-gold font-semibold' : 'text-gray-400'}`}>
            Debate
          </span>
          <button
            onClick={() => setDebateMode(d => !d)}
            className={`relative w-9 h-5 rounded-full transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-brand-gold
              ${debateMode ? 'bg-brand-gold' : 'bg-gray-200 dark:bg-white/20'}`}
          >
            <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform duration-200
              ${debateMode ? 'translate-x-4' : 'translate-x-0'}`} />
          </button>
        </label>
      </div>

      {/* ── Debate mode badge ── */}
      {debateMode && (
        <div className="flex-shrink-0 bg-brand-gold/10 border-b border-brand-gold/30 px-5 py-1.5 flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-brand-gold animate-pulse" />
          <p className="text-xs text-brand-purple dark:text-brand-gold font-medium">
            Debate mode on — Claude will steelman both sides before concluding
          </p>
        </div>
      )}

      {/* ── Message list ── */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-2xl mx-auto space-y-4">

          {messages.length === 0 && !streaming && (
            <div className="text-center mt-12">
              <div className="w-12 h-12 rounded-full bg-brand-purple/10 flex items-center justify-center mx-auto mb-3">
                <svg className="w-6 h-6 text-brand-purple dark:text-brand-gold" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                </svg>
              </div>
              <p className="text-gray-400 dark:text-gray-500 text-sm mb-5">
                Ask anything about <span className="text-brand-purple dark:text-brand-gold font-medium">{filename}</span>
              </p>
              <div className="flex flex-col gap-2">
                {SUGGESTIONS.map(s => (
                  <button
                    key={s}
                    onClick={() => sendMessage(s)}
                    className="text-sm text-brand-purple dark:text-brand-gold/80 border border-brand-purple/20 dark:border-brand-gold/20 rounded-xl px-4 py-2 hover:bg-brand-purple/5 dark:hover:bg-brand-gold/5 transition text-left"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`flex msg-enter ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[78%] rounded-2xl px-4 py-3 text-sm leading-relaxed break-words
                ${msg.role === 'user'
                  ? 'bg-brand-purple text-white rounded-br-sm shadow-purple-sm whitespace-pre-wrap'
                  : 'bg-gray-100 dark:bg-brand-dark-card text-gray-800 dark:text-gray-100 rounded-bl-sm border border-gray-200 dark:border-brand-purple/30'
                }`}
              >
                {msg.role === 'user' ? (
                  msg.content || (streaming && i === messages.length - 1 ? '' : '…')
                ) : (
                  <>
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        h1: ({children}) => <h1 className="text-lg font-bold mt-4 mb-2 first:mt-0">{children}</h1>,
                        h2: ({children}) => <h2 className="text-base font-bold mt-3 mb-1.5 first:mt-0">{children}</h2>,
                        h3: ({children}) => <h3 className="text-sm font-bold mt-2 mb-1 first:mt-0">{children}</h3>,
                        p: ({children}) => <p className="mb-2 leading-relaxed font-normal">{children}</p>,
                        strong: ({children}) => <strong className="font-semibold">{children}</strong>,
                        em: ({children}) => <em className="italic">{children}</em>,
                        ul: ({children}) => <ul className="list-disc pl-5 my-2 space-y-1">{children}</ul>,
                        ol: ({children}) => <ol className="list-decimal pl-5 my-2 space-y-1">{children}</ol>,
                        li: ({children}) => <li className="leading-relaxed">{children}</li>,
                        code: ({children, className}) => className
                          ? <pre className="bg-black/10 dark:bg-white/10 rounded p-2 my-2 text-xs font-mono overflow-x-auto whitespace-pre"><code>{children}</code></pre>
                          : <code className="bg-black/10 dark:bg-white/10 rounded px-1 py-0.5 text-xs font-mono">{children}</code>,
                        blockquote: ({children}) => <blockquote className="border-l-2 border-brand-purple/30 pl-3 my-2 italic opacity-80">{children}</blockquote>,
                      }}
                    >
                      {msg.content || (streaming && i === messages.length - 1 ? '' : '…')}
                    </ReactMarkdown>
                    {streaming && i === messages.length - 1 && (
                      <span className="inline-block w-1.5 h-[14px] bg-brand-gold ml-0.5 align-middle animate-pulse rounded-sm" />
                    )}
                  </>
                )}
              </div>
            </div>
          ))}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* ── Error ── */}
      {error && (
        <div className="flex-shrink-0 px-5 py-2 bg-red-50 dark:bg-red-900/20 border-t border-red-200 dark:border-red-800">
          <p className="text-xs text-red-600 dark:text-red-400 text-center">{error}</p>
        </div>
      )}

      {/* ── Input bar ── */}
      <div className="flex-shrink-0 border-t border-gray-200 dark:border-brand-purple/30 bg-white dark:bg-brand-dark-bg px-4 py-3">
        <div className="max-w-2xl mx-auto flex gap-3 items-end">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={streaming}
            placeholder={streaming ? 'Claude is thinking…' : 'Ask a question  ·  Enter to send'}
            rows={1}
            className="flex-1 resize-none rounded-2xl border border-gray-300 dark:border-brand-purple/40 bg-white dark:bg-brand-dark-card text-gray-800 dark:text-white placeholder-gray-400 dark:placeholder-gray-600 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-purple dark:focus:ring-brand-gold transition-all duration-150 disabled:opacity-50 overflow-hidden"
          />
          <button
            onClick={() => sendMessage()}
            disabled={streaming || !input.trim()}
            className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center transition-all duration-200
              ${streaming || !input.trim()
                ? 'bg-gray-200 dark:bg-brand-dark-card text-gray-400 cursor-not-allowed'
                : 'bg-brand-gold hover:bg-brand-gold-light shadow-gold-glow text-black hover:scale-105'
              }`}
          >
            {streaming
              ? <span className="w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
              : <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
            }
          </button>
        </div>
        <p className="text-center text-gray-300 dark:text-gray-700 text-xs mt-2">Shift+Enter for new line</p>
      </div>

    </div>
  )
}
