from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Language(str, Enum):
    python = "python"
    typescript = "typescript"
    java = "java"


class SyntaxErrorItem(BaseModel):
    line: int | None = None
    column: int | None = None
    message: str


class SyntaxResult(BaseModel):
    valid: bool
    errors: list[SyntaxErrorItem] = Field(default_factory=list)


FindingCategory = Literal["security", "performance", "logic", "style"]
Severity = Literal["high", "medium", "low"]


class Finding(BaseModel):
    category: FindingCategory
    title: str
    detail: str
    suggestion: str
    severity: Severity | None = None
    line_start: int | None = None
    line_end: int | None = None


class ReviewRequest(BaseModel):
    language: Language
    code: str


class ReviewResponse(BaseModel):
    syntax: SyntaxResult
    findings: list[Finding]
    summary: str
    better_implementation_code: str = ""
    better_implementation_explanation: str = ""


class RunRequest(BaseModel):
    language: Language
    code: str
    stdin: str = ""


class RunResponse(BaseModel):
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    duration_ms: int = 0
    error: str | None = None


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
