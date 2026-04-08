import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_review_without_gemini_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    with TestClient(app) as client:
        r = client.post("/api/review", json={"language": "python", "code": "x = 1"})
    assert r.status_code == 503
    body = r.json()
    assert body.get("error") == "review_unavailable"
    assert "GEMINI" in (body.get("detail") or "").upper() or "not configured" in (
        body.get("detail") or ""
    ).lower()


def test_run_sandbox_disabled(monkeypatch):
    monkeypatch.setenv("SANDBOX_ENABLED", "false")
    with TestClient(app) as client:
        r = client.post(
            "/api/run",
            json={"language": "python", "code": "print(1)", "stdin": ""},
        )
    assert r.status_code == 200
    body = r.json()
    assert body.get("error") == "Sandbox is disabled"


def test_run_empty_code_400(client):
    r = client.post(
        "/api/run",
        json={"language": "python", "code": "  \n\t  ", "stdin": ""},
    )
    assert r.status_code == 400
    assert r.json().get("error") == "invalid_input"
