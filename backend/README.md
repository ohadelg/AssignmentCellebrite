# Code Review API

FastAPI service for syntax checks, Gemini-powered review, and sandboxed execution.

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example ../.env   # or create .env with GEMINI_API_KEY
```

## Run

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

OpenAPI docs: http://127.0.0.1:8000/docs
