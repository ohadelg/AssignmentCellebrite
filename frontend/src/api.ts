const prefix = import.meta.env.VITE_API_BASE ?? ''

/** Slightly above backend default `review_timeout_sec` (120s). */
export const REVIEW_TIMEOUT_MS = 125_000
/** Above typical `SANDBOX_TIMEOUT_SEC` + docker margin. */
export const RUN_TIMEOUT_MS = 60_000

export type Language = 'python' | 'typescript' | 'java'

export interface SyntaxErrorItem {
  line: number | null
  column: number | null
  message: string
}

export interface SyntaxResult {
  valid: boolean
  errors: SyntaxErrorItem[]
}

export type FindingCategory = 'security' | 'performance' | 'logic' | 'style'

export interface Finding {
  category: FindingCategory
  title: string
  detail: string
  suggestion: string
  severity?: 'high' | 'medium' | 'low' | null
  line_start?: number | null
  line_end?: number | null
}

export interface ReviewResponse {
  syntax: SyntaxResult
  findings: Finding[]
  summary: string
  better_implementation_code?: string
  better_implementation_explanation?: string
}

export interface RunResponse {
  exit_code: number | null
  stdout: string
  stderr: string
  timed_out: boolean
  duration_ms: number
  error?: string | null
}

export interface ApiError {
  error: string
  detail?: string | null
}

export type ReviewResult =
  | { ok: true; data: ReviewResponse }
  | { ok: false; status: number; body: ApiError }

export type RunResult =
  | { ok: true; data: RunResponse }
  | { ok: false; status: number; body: ApiError }

async function parseResponseBody<T>(r: Response): Promise<T> {
  const text = await r.text()
  const trimmed = text.trim()
  const ct = r.headers.get('content-type') ?? ''
  const looksJson =
    ct.includes('application/json') || trimmed.startsWith('{') || trimmed.startsWith('[')
  if (looksJson && trimmed) {
    try {
      return JSON.parse(trimmed) as T
    } catch {
      return {
        error: 'invalid_json',
        detail: trimmed.slice(0, 500),
      } as T
    }
  }
  return {
    error: 'non_json_response',
    detail: trimmed ? trimmed.slice(0, 300) : '(empty body)',
  } as T
}

function networkErrorBody(e: unknown): ApiError {
  if (e instanceof DOMException && (e.name === 'AbortError' || e.name === 'TimeoutError')) {
    return { error: 'request_timeout', detail: 'The request was aborted or timed out.' }
  }
  if (e instanceof TypeError) {
    return { error: 'network_error', detail: e.message }
  }
  if (e instanceof Error) {
    return { error: 'request_failed', detail: e.message }
  }
  return { error: 'request_failed', detail: String(e) }
}

export async function reviewCode(language: Language, code: string): Promise<ReviewResult> {
  try {
    const r = await fetch(`${prefix}/api/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ language, code }),
      signal: AbortSignal.timeout(REVIEW_TIMEOUT_MS),
    })
    const body = await parseResponseBody<ReviewResponse | ApiError>(r)
    if (!r.ok) {
      return { ok: false as const, status: r.status, body: body as ApiError }
    }
    return { ok: true as const, data: body as ReviewResponse }
  } catch (e) {
    return { ok: false as const, status: 0, body: networkErrorBody(e) }
  }
}

export async function runSandbox(
  language: Language,
  code: string,
  stdin: string,
): Promise<RunResult> {
  try {
    const r = await fetch(`${prefix}/api/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ language, code, stdin }),
      signal: AbortSignal.timeout(RUN_TIMEOUT_MS),
    })
    const body = await parseResponseBody<RunResponse | ApiError>(r)
    if (!r.ok) {
      return { ok: false as const, status: r.status, body: body as ApiError }
    }
    return { ok: true as const, data: body as RunResponse }
  } catch (e) {
    return { ok: false as const, status: 0, body: networkErrorBody(e) }
  }
}
