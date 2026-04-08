import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.llm.gemini_review import GeminiReviewError, review_code_async
from app.models import (
    ErrorResponse,
    ReviewRequest,
    ReviewResponse,
    RunRequest,
    RunResponse,
)
from app.sanitize import sanitize_code, sanitize_stdin
from app.sandbox_run import configure_java_environment, execute_sandboxed
from app.syntax_check import check_syntax

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    configure_java_environment(java_home_from_settings=s.java_home)
    yield


app = FastAPI(title="GenAI Code Review API", lifespan=lifespan)


def settings_dep() -> Settings:
    return get_settings()


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="internal_error",
            detail="An unexpected error occurred",
        ).model_dump(),
    )


def _configure_cors(application: FastAPI, settings: Settings) -> None:
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


_configure_cors(app, get_settings())


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/review", response_model=ReviewResponse)
async def review_code(
    body: ReviewRequest,
    settings: Settings = Depends(settings_dep),
):
    try:
        code = sanitize_code(body.code, settings)
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(error="invalid_input", detail=str(e)).model_dump(),
        )

    syntax = check_syntax(body.language, code)
    try:
        summary, findings, better_code, better_expl = await review_code_async(
            settings=settings,
            language=body.language,
            code=code,
            syntax=syntax,
        )
    except GeminiReviewError as e:
        return JSONResponse(
            status_code=503,
            content=ErrorResponse(
                error="review_unavailable",
                detail=str(e),
            ).model_dump(),
        )

    return ReviewResponse(
        syntax=syntax,
        findings=findings,
        summary=summary,
        better_implementation_code=better_code,
        better_implementation_explanation=better_expl,
    )


@app.post("/api/run", response_model=RunResponse)
async def run_code(
    body: RunRequest,
    settings: Settings = Depends(settings_dep),
):
    try:
        code = sanitize_code(body.code, settings)
        stdin = sanitize_stdin(body.stdin or "", settings)
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(error="invalid_input", detail=str(e)).model_dump(),
        )

    raw = execute_sandboxed(
        settings=settings,
        language=body.language,
        code=code,
        stdin=stdin,
    )
    return RunResponse(
        exit_code=raw["exit_code"],
        stdout=raw["stdout"],
        stderr=raw["stderr"],
        timed_out=raw["timed_out"],
        duration_ms=raw["duration_ms"],
        error=raw.get("error"),
    )
