import { useCallback, useState } from 'react'
import Editor from '@monaco-editor/react'
import type { editor } from 'monaco-editor'
import './App.css'
import {
  type Finding,
  type Language,
  type ReviewResponse,
  type RunResponse,
  reviewCode,
  runSandbox,
} from './api'
import { pickRandomExample } from './codeExamples'

const MONACO_LANG: Record<Language, string> = {
  python: 'python',
  typescript: 'typescript',
  java: 'java',
}

function chipClass(cat: Finding['category']): string {
  switch (cat) {
    case 'security':
      return 'chip chip-security'
    case 'performance':
      return 'chip chip-performance'
    case 'logic':
      return 'chip chip-logic'
    default:
      return 'chip chip-style'
  }
}

export default function App() {
  const [language, setLanguage] = useState<Language>('python')
  const [code, setCode] = useState(() => pickRandomExample('python'))
  const [reviewLoading, setReviewLoading] = useState(false)
  const [runLoading, setRunLoading] = useState(false)
  const [review, setReview] = useState<ReviewResponse | null>(null)
  const [runResult, setRunResult] = useState<RunResponse | null>(null)
  const [banner, setBanner] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<number | null>(null)
  const [implementationCopied, setImplementationCopied] = useState(false)
  const [runStdin, setRunStdin] = useState('')

  const onLanguageChange = useCallback((lang: Language) => {
    setLanguage(lang)
    setCode(pickRandomExample(lang))
    setReview(null)
    setRunResult(null)
    setExpanded(null)
    setBanner(null)
    setImplementationCopied(false)
  }, [])

  const copySuggestedCode = useCallback(async () => {
    const text = review?.better_implementation_code?.trim()
    if (!text) return
    try {
      await navigator.clipboard.writeText(text)
      setImplementationCopied(true)
      window.setTimeout(() => setImplementationCopied(false), 2000)
    } catch {
      try {
        const ta = document.createElement('textarea')
        ta.value = text
        ta.style.position = 'fixed'
        ta.style.left = '-9999px'
        document.body.appendChild(ta)
        ta.select()
        document.execCommand('copy')
        document.body.removeChild(ta)
        setImplementationCopied(true)
        window.setTimeout(() => setImplementationCopied(false), 2000)
      } catch {
        setBanner('Could not copy to clipboard')
      }
    }
  }, [review?.better_implementation_code])

  const onReview = useCallback(async () => {
    setBanner(null)
    setReview(null)
    setReviewLoading(true)
    try {
      const res = await reviewCode(language, code)
      if (res.ok === false) {
        setBanner(res.body.detail || res.body.error || 'Review failed')
        return
      }
      setReview(res.data)
      setExpanded(null)
      setImplementationCopied(false)
    } catch (e) {
      setBanner(e instanceof Error ? e.message : 'Review failed')
    } finally {
      setReviewLoading(false)
    }
  }, [language, code])

  const onRun = useCallback(async () => {
    setBanner(null)
    setRunResult(null)
    setRunLoading(true)
    try {
      const res = await runSandbox(language, code, runStdin)
      if (res.ok === false) {
        setBanner(res.body.detail || res.body.error || 'Run failed')
        return
      }
      setRunResult(res.data)
    } catch (e) {
      setBanner(e instanceof Error ? e.message : 'Run failed')
    } finally {
      setRunLoading(false)
    }
  }, [language, code, runStdin])

  const handleMount = useCallback((_: editor.IStandaloneCodeEditor, monaco: typeof import('monaco-editor')) => {
    monaco.editor.defineTheme('sentinel', {
      base: 'vs-dark',
      inherit: true,
      rules: [],
      colors: {
        'editor.background': '#0d0d0e',
        'editorLineNumber.foreground': '#5a5a62',
        'editorCursor.foreground': '#00e5ff',
      },
    })
    monaco.editor.setTheme('sentinel')
  }, [])

  return (
    <div className="app">
      <header className="app-header">
        <h1 className="app-title">Digital Sentinel</h1>
        <p className="app-tagline">GenAI code review — tactical analysis</p>
      </header>

      {banner ? <div className="alert">{banner}</div> : null}

      <div className="bento">
        <section className="cell cell-editor" aria-label="Code editor">
          <div className="cell-head">
            <h2>Command buffer</h2>
            <div className="toolbar">
              <select
                className="lang-select"
                value={language}
                onChange={(e) => onLanguageChange(e.target.value as Language)}
                aria-label="Language"
              >
                <option value="python">Python</option>
                <option value="typescript">TypeScript</option>
                <option value="java">Java</option>
              </select>
              <button
                type="button"
                className="btn btn-primary"
                onClick={onReview}
                disabled={reviewLoading}
              >
                {reviewLoading ? 'Processing…' : 'Review code'}
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={onRun}
                disabled={runLoading}
              >
                {runLoading ? 'Running…' : 'Run in sandbox'}
              </button>
            </div>
          </div>
          <div className="editor-wrap">
            <Editor
              height="100%"
              language={MONACO_LANG[language]}
              value={code}
              onChange={(v) => setCode(v ?? '')}
              onMount={handleMount}
              options={{
                minimap: { enabled: false },
                fontSize: 13,
                fontFamily: 'JetBrains Mono, monospace',
                scrollBeyondLastLine: false,
                padding: { top: 12 },
                automaticLayout: true,
              }}
            />
          </div>
        </section>

        <section className="cell cell-run glass-panel" aria-label="Sandbox output">
          <div className="cell-head">
            <h2>Execution</h2>
          </div>
          <div className="stdin-block">
            <label htmlFor="run-stdin" className="stdin-label">
              Program stdin (optional)
            </label>
            <textarea
              id="run-stdin"
              className="stdin-input mono"
              value={runStdin}
              onChange={(e) => setRunStdin(e.target.value)}
              placeholder="Passed to the process on run…"
              rows={2}
              spellCheck={false}
            />
          </div>
          {runLoading ? (
            <div className="run-loading" role="status" aria-live="polite">
              <div className="spinner" aria-hidden />
              <span>Executing in sandbox…</span>
            </div>
          ) : !runResult ? (
            <p className="empty-hint">
              Run your snippet in an isolated sandbox (Docker when available; Python falls back to the host if the
              image is missing or the daemon is down).
            </p>
          ) : (
            <>
              <div className="terminal-panel">
                {runResult.error ? (
                  <span className="stderr">{runResult.error}</span>
                ) : null}
                {runResult.timed_out ? (
                  <span className="stderr">Timed out.</span>
                ) : null}
                {runResult.stdout ? (
                  <div className="stdout">{runResult.stdout}</div>
                ) : null}
                {runResult.stderr ? (
                  <div className="stderr">{runResult.stderr}</div>
                ) : null}
                {!runResult.stdout && !runResult.stderr && !runResult.error && !runResult.timed_out ? (
                  <span className="muted">(no output)</span>
                ) : null}
              </div>
              <div className="terminal-meta">
                exit: {runResult.exit_code === null ? '—' : runResult.exit_code} · {runResult.duration_ms} ms
              </div>
            </>
          )}
        </section>

        <section className="cell cell-feedback glass-panel" aria-label="AI feedback">
          <div className="cell-head">
            <h2>Intelligence</h2>
          </div>
          {reviewLoading ? (
            <div className="intelligence-processing" role="status" aria-live="polite">
              <div className="spinner" aria-hidden />
              <div className="review-loading-text">Processing…</div>
              <p className="empty-hint" style={{ margin: 0 }}>
                Waiting for structured review from the model.
              </p>
            </div>
          ) : !review ? (
            <p className="empty-hint">Submit code for security, performance, logic, and style findings.</p>
          ) : (
            <>
              <div className={`syntax-strip${review.syntax.valid ? '' : ' invalid'}`}>
                <strong className="mono">Syntax</strong>{' '}
                {review.syntax.valid ? (
                  <span className="muted">valid</span>
                ) : (
                  <span>
                    {review.syntax.errors.map((e, i) => (
                      <span key={i} className="mono">
                        {e.line != null ? `L${e.line}: ` : ''}
                        {e.message}
                        {i < review.syntax.errors.length - 1 ? ' · ' : ''}
                      </span>
                    ))}
                  </span>
                )}
              </div>
              {review.summary ? <p className="summary">{review.summary}</p> : null}
              <div className="findings-list">
                {review.findings.map((f, i) => (
                  <button
                    key={i}
                    type="button"
                    className={`finding-card${expanded === i ? ' expanded' : ''}`}
                    onClick={() => setExpanded(expanded === i ? null : i)}
                  >
                    <div className="finding-top">
                      <span className={chipClass(f.category)}>{f.category}</span>
                      {f.severity ? (
                        <span className="chip chip-style">{f.severity}</span>
                      ) : null}
                      <span className="finding-title">{f.title}</span>
                    </div>
                    {expanded === i ? (
                      <div className="finding-body">
                        <p>{f.detail}</p>
                        <p>
                          <strong>Suggestion</strong>
                          <br />
                          {f.suggestion}
                        </p>
                        {f.line_start != null ? (
                          <p className="mono muted">
                            Lines {f.line_start}
                            {f.line_end != null && f.line_end !== f.line_start
                              ? `–${f.line_end}`
                              : ''}
                          </p>
                        ) : null}
                      </div>
                    ) : null}
                  </button>
                ))}
              </div>
              {(review.better_implementation_code?.trim() ||
                review.better_implementation_explanation?.trim()) ? (
                <div className="implementation-offer implementation-offer-below">
                  <div className="implementation-header">
                    <h3 className="implementation-title">Suggested implementation</h3>
                    {review.better_implementation_code?.trim() ? (
                      <button
                        type="button"
                        className="btn btn-copy-code"
                        onClick={copySuggestedCode}
                        aria-label="Copy suggested code to clipboard"
                      >
                        {implementationCopied ? 'Copied' : 'Copy code'}
                      </button>
                    ) : null}
                  </div>
                  {review.better_implementation_explanation?.trim() ? (
                    <p className="implementation-explanation">{review.better_implementation_explanation}</p>
                  ) : null}
                  {review.better_implementation_code?.trim() ? (
                    <pre className="implementation-code mono">
                      <code>{review.better_implementation_code}</code>
                    </pre>
                  ) : null}
                </div>
              ) : null}
            </>
          )}
        </section>
      </div>
    </div>
  )
}
