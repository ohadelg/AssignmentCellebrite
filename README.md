# GenAI Code Review

Full-stack app: **FastAPI** backend (syntax validation, **Google Gemini** review, **sandboxed** code run) and **React + TypeScript** frontend (Monaco editor, tactical UI aligned with [DESIGN.md](DESIGN.md)).

## Prerequisites

- Python 3.11+
- Node.js 20+
- **Docker** (optional but recommended for multi-language sandbox). Build the runner image:

  ```bash
  docker build -t cellebrite-code-sandbox:local ./sandbox
  # or: docker compose build sandbox
  ```

  Rebuild the image after changes under `sandbox/` (Dockerfile, `runner_entry.py`, timeouts, non-root user).

  If Docker is not running or the daemon is down, the API **skips `docker run`** and uses **host fallbacks** (weaker isolation): **Python** via the same interpreter as the API, **TypeScript** via `tsx` on `PATH` or `npx tsx@4`, **Java** via `javac` / `java` on `PATH`. Start Docker Desktop to use the isolated container instead.

## Configuration

Copy [`.env.example`](.env.example) to `.env` and set secrets **only in the environment** (never commit `.env`):

- **`GEMINI_API_KEY`** — from [Google AI Studio](https://aistudio.google.com/apikey)
- **`GEMINI_MODEL`** — e.g. `gemini-2.5-flash` (older IDs like `gemini-2.0-flash` may return 404 for new API keys)
- **`REVIEW_TIMEOUT_SEC`** — optional; caps each Gemini call (default 120). Frontend uses a slightly higher client timeout.
- **`SANDBOX_*`** — see `.env.example`

In production, inject the same variables from your secret manager.

## Run locally

**Terminal 1 — API**

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 — UI**

```bash
cd frontend
npm install
node scripts/vite-dev.mjs
```

From the repo root you can also run **`./dev-frontend.sh`** (same as `node scripts/vite-dev.mjs`; avoids `npm run dev`).

Use **`node scripts/vite-dev.mjs`** or **`./dev-frontend.sh`** instead of **`npm run dev`** so npm does not print `Unknown env config "devdir"` (that warning comes from npm itself when it starts, not from Vite).

Open http://localhost:5173 — the dev server proxies `/api` to the backend.

### Troubleshooting

- **`npm warn Unknown env config "devdir"`** — Something (often the IDE) sets `npm_config_devdir`. **Run the UI with `node scripts/vite-dev.mjs`** after `npm install` so npm is not involved in starting Vite. To fix globally: `unset npm_config_devdir NPM_CONFIG_DEVDIR` or remove them from your shell/IDE env.
- **Java sandbox / “No working JDK”** — Install a JDK (e.g. [Temurin 17](https://adoptium.net)) or set **`JAVA_HOME`** in `.env` to the JDK root (folder that contains `bin/javac`). On macOS the API also runs **`/usr/libexec/java_home`** at startup to set **`JAVA_HOME`** when unset, and it skips **`/usr/bin/java`** / **`javac`** (the install stub) when probing the JDK. The API still prepends common paths (`/Library/Java/...`, Homebrew `openjdk`) for `javac`/`java`. Or use Docker + `docker compose build sandbox`.

To call the API from another origin, set `VITE_API_BASE` (e.g. `http://127.0.0.1:8000`) in `frontend/.env` and adjust `CORS_ORIGINS` on the server.

## Tests (backend)

```bash
cd backend && source .venv/bin/activate
pip install -r requirements.txt
pytest
```

If the tree-sitter parser fails to load for TypeScript/Java, syntax is reported as invalid with an explanatory message (reviews still run).

## API examples

```bash
curl -s http://127.0.0.1:8000/health

curl -s -X POST http://127.0.0.1:8000/api/review \
  -H 'Content-Type: application/json' \
  -d '{"language":"python","code":"def x():\n    pass\n"}'

curl -s -X POST http://127.0.0.1:8000/api/run \
  -H 'Content-Type: application/json' \
  -d '{"language":"python","code":"print(42)","stdin":""}'
```

## Project layout

- [`backend/`](backend/) — FastAPI app
- [`frontend/`](frontend/) — Vite + React + Monaco
- [`sandbox/`](sandbox/) — Docker image for isolated `POST /api/run`

## License

See [LICENSE](LICENSE).
