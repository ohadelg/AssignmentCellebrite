# Project overview (for tooling, eval, and automation)

This document is **initialization context** for agents or scripts that need to **call the code-review “agent”**, parse its outputs, or benchmark it. It describes how the repo is wired, which contracts are stable, and where the logic lives.

## What “the agent” is in this repo

There is **no separate long-running agent process**. The intelligent review is a **single Gemini call** (with optional JSON repair) implemented in Python:

| Role | Location |
|------|----------|
| HTTP API | `backend/app/main.py` — `POST /api/review` |
| LLM review + schema | `backend/app/llm/gemini_review.py` — `review_code_async()` |
| Canonical data shapes | `backend/app/models.py` |
| Shared types with UI | `frontend/src/api.ts` (mirrors API JSON) |

The model is instructed to act as an expert reviewer and to emit **structured JSON** (summary, findings array, improved code + explanation). **Security vulnerabilities** appear as findings with `category: "security"` (alongside performance, logic, style).

## High-level architecture

- **Backend**: FastAPI (`backend/app/main.py`), loads settings from `.env` (repo root or `backend/`).
- **Frontend**: Vite + React; dev server proxies `/api` to the backend (see `README.md`).
- **Sandbox** (optional for eval): `POST /api/run` executes code in Docker or host fallback — **independent** from review; useful if you want runtime checks in addition to static/LLM findings.

For **evaluating how well the model finds vulnerabilities**, the primary surface is **`POST /api/review`** or a direct call to **`review_code_async`** with the same inputs the API uses.

## Review pipeline (what runs before the model)

Order matters for reproducibility and for what the model sees:

1. **Sanitize** — `app/sanitize.py` (`sanitize_code`): normalize newlines, strip most control characters, enforce `max_code_bytes` (default 100_000 UTF-8 bytes), reject empty code.
2. **Syntax check** — `app/syntax_check.py` (`check_syntax`): Python via `ast.parse`; TypeScript/Java via tree-sitter (or “unavailable” error if parser fails).
3. **Gemini** — User prompt includes language, syntax validity + errors, and full code. System instruction and JSON schema are in `gemini_review.py`.
4. **Parse** — `_parse_review_json` builds `Finding` list; invalid categories are dropped with warnings; malformed JSON triggers one **repair** generation with the same schema.

Eval harnesses should either **use the HTTP endpoint** (full pipeline) or **import and call** `review_code_async` with a real `Settings` instance if they need to avoid HTTP.

## HTTP integration

### Base URL

- Local default: `http://127.0.0.1:8000` (see `README.md` for `uvicorn` command).
- Health: `GET /health` → `{"status":"ok"}`.

### `POST /api/review`

**Request** (`application/json`):

```json
{
  "language": "python",
  "code": "<source text>"
}
```

`language` must be one of: `python`, `typescript`, `java` (see `Language` enum in `models.py`).

**Success (200)** — body matches `ReviewResponse`:

| Field | Type | Notes |
|-------|------|--------|
| `syntax` | object | `valid: boolean`, `errors: [{ line, column, message }]` |
| `findings` | array | See **Finding** below |
| `summary` | string | Overall review text |
| `better_implementation_code` | string | Model’s rewrite |
| `better_implementation_explanation` | string | Why the rewrite helps |

**Finding** (each element of `findings`):

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `category` | string | yes | `security` \| `performance` \| `logic` \| `style` |
| `title` | string | yes | Short label |
| `detail` | string | yes | Explanation |
| `suggestion` | string | yes | Actionable fix |
| `severity` | string | no | `high` \| `medium` \| `low` |
| `line_start` | integer | no | 1-based if present |
| `line_end` | integer | no | 1-based if present |

**Client errors**

- **400** — `{"error":"invalid_input","detail":"..."}` (sanitization/validation).
- **503** — `{"error":"review_unavailable","detail":"..."}` (missing key, timeout, Gemini API errors, etc.).

**Timeouts** — Server-side review is capped by `REVIEW_TIMEOUT_SEC` (default 120s). The frontend uses ~125s client timeout (`REVIEW_TIMEOUT_MS` in `frontend/src/api.ts`).

### `POST /api/run` (optional for eval)

Runs user code in a sandbox; body: `{ "language", "code", "stdin" }`. Response: exit code, stdout/stderr, timeout flag, duration. Not used by the review agent itself.

## Direct Python integration (for batch eval)

```text
from app.config import get_settings
from app.models import Language, SyntaxResult
from app.syntax_check import check_syntax
from app.sanitize import sanitize_code
from app.llm.gemini_review import review_code_async
```

Typical sequence (mirrors the route):

1. `code = sanitize_code(raw_code, settings)`
2. `syntax = check_syntax(language, code)`
3. `summary, findings, better_code, better_expl = await review_code_async(settings=settings, language=language, code=code, syntax=syntax)`

Requires `GEMINI_API_KEY` (and optionally `GEMINI_MODEL`, `REVIEW_TIMEOUT_SEC`) in the environment or `.env`.

## Configuration relevant to eval

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | Required for review |
| `GEMINI_MODEL` | e.g. `gemini-2.5-flash` |
| `REVIEW_TIMEOUT_SEC` | Per generate call (initial + repair) |
| `MAX_CODE_BYTES` | Request size limit |

See `.env.example` for defaults and sandbox-related vars (`SANDBOX_*`) if you combine run + review.

## Model-side contract (Gemini JSON schema)

The structured output schema sent to Gemini is defined in `_review_schema()` in `gemini_review.py`: top-level keys `summary`, `findings`, `better_implementation_code`, `better_implementation_explanation`; each finding has the same categories and optional `severity` / line fields as the API.

System and user prompts are in the same file (`SYSTEM_INSTRUCTION`, `REVIEW_USER_TEMPLATE`). Changing prompts or schema there changes agent behavior and output shape for evals.

## Suggested focus for vulnerability evals

- **Ground truth**: Define labeled issues per snippet (e.g. CWE, line ranges, expected category `security`).
- **Matching**: Compare model `findings` where `category == "security"` to labels (normalize titles/text; use line overlap if both specify lines).
- **Metrics**: Precision/recall/F1 on issues; optional severity calibration; false-positive rate on clean code.
- **Controls**: Same `GEMINI_MODEL` and temperature (if exposed later) across runs; record `syntax.valid` because invalid syntax may shift behavior.

## Repository map (quick reference)

| Path | Responsibility |
|------|----------------|
| `backend/app/main.py` | Routes, CORS, wiring |
| `backend/app/models.py` | Pydantic API models |
| `backend/app/llm/gemini_review.py` | Gemini client, prompts, parsing |
| `backend/app/syntax_check.py` | Static syntax |
| `backend/app/sanitize.py` | Input limits and cleanup |
| `backend/app/sandbox_run.py` | `POST /api/run` execution |
| `frontend/src/api.ts` | Fetch helpers + TypeScript types |
| `sandbox/` | Docker image for isolated runs |
| `README.md` | Run instructions and curl examples |

This should be enough for an **eval agent workflow** to locate the review entrypoint, reproduce the server pipeline, and consume **`ReviewResponse.findings`** in a consistent way.
