import asyncio
import json
import logging

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.config import Settings
from app.models import Finding, Language, SyntaxResult

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = """You are an expert code reviewer. Analyze code systematically.
Output must be valid JSON only, matching the requested schema.
Categories: security (vulnerabilities, injection), performance (efficiency, algorithms), logic (bugs, edge cases), style (formatting, naming, maintainability, best practices).
Be specific and actionable. Reference line numbers when clear from the code.

Also produce better_implementation_code: a complete, idiomatic rewrite that addresses the main issues (same intent and public behavior where possible).
And better_implementation_explanation: a clear paragraph for a developer on what you changed and why (security, API choices, style). Use plain language."""

REVIEW_USER_TEMPLATE = """Programming language: {language}

--- Syntax validation (from static analysis) ---
Valid: {syntax_valid}
{syntax_errors}

--- Code ---
```
{code}
```

Produce a structured code review covering security, performance, logic, and style.
Include a concrete improved code sample and a short explanation of the improvements.
If syntax is invalid, still mention parse/syntax issues briefly under logic or style, but focus on what you can infer."""


class GeminiReviewError(Exception):
    pass


def _syntax_block(syntax: SyntaxResult) -> str:
    if syntax.valid:
        return "No syntax errors reported."
    lines = []
    for err in syntax.errors:
        loc = ""
        if err.line is not None:
            loc = f"line {err.line}"
            if err.column is not None:
                loc += f", col {err.column}"
            loc += ": "
        lines.append(f"- {loc}{err.message}")
    return "\n".join(lines) if lines else "Syntax errors reported."


def _review_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "better_implementation_code": {
                "type": "string",
                "description": "Full improved source in the same language as the input",
            },
            "better_implementation_explanation": {
                "type": "string",
                "description": "Why the rewrite is better",
            },
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "enum": ["security", "performance", "logic", "style"],
                        },
                        "title": {"type": "string"},
                        "detail": {"type": "string"},
                        "suggestion": {"type": "string"},
                        "severity": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                        },
                        "line_start": {"type": "integer"},
                        "line_end": {"type": "integer"},
                    },
                    "required": [
                        "category",
                        "title",
                        "detail",
                        "suggestion",
                    ],
                },
            },
        },
        "required": ["summary", "findings", "better_implementation_code", "better_implementation_explanation"],
    }


_FINDING_CATEGORIES = frozenset({"security", "performance", "logic", "style"})


def _parse_review_json(text: str) -> tuple[str, list[Finding], str, str]:
    data = json.loads(text)
    summary = data.get("summary") or ""
    better_code = (data.get("better_implementation_code") or "").strip()
    better_expl = (data.get("better_implementation_explanation") or "").strip()
    raw_findings = data.get("findings") or []
    findings: list[Finding] = []
    for idx, item in enumerate(raw_findings):
        if not isinstance(item, dict):
            logger.warning("gemini finding[%s]: not an object, skipping: %r", idx, item)
            continue
        cat = item.get("category")
        if cat not in _FINDING_CATEGORIES:
            logger.warning(
                "gemini finding[%s]: invalid category %r, keys=%s",
                idx,
                cat,
                list(item.keys()),
            )
            continue
        try:
            findings.append(
                Finding(
                    category=cat,
                    title=item.get("title", ""),
                    detail=item.get("detail", ""),
                    suggestion=item.get("suggestion", ""),
                    severity=item.get("severity"),
                    line_start=item.get("line_start"),
                    line_end=item.get("line_end"),
                )
            )
        except Exception as e:
            logger.warning("gemini finding[%s]: dropped (%s): %r", idx, e, item)
            continue
    return summary, findings, better_code, better_expl


def _generate_sync(
    client: genai.Client,
    model: str,
    contents: str,
    schema: dict,
) -> str:
    config = types.GenerateContentConfig(
        temperature=0.2,
        max_output_tokens=8192,
        system_instruction=SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_json_schema=schema,
    )
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=config,
    )
    if not response.text:
        raise GeminiReviewError("Empty response from model")
    return response.text


async def review_code_async(
    *,
    settings: Settings,
    language: Language,
    code: str,
    syntax: SyntaxResult,
) -> tuple[str, list[Finding], str, str]:
    if not settings.gemini_api_key.strip():
        raise GeminiReviewError("AI review is not configured (missing GEMINI_API_KEY)")

    client = genai.Client(api_key=settings.gemini_api_key)
    user_text = REVIEW_USER_TEMPLATE.format(
        language=language.value,
        syntax_valid=syntax.valid,
        syntax_errors=_syntax_block(syntax),
        code=code,
    )
    schema = _review_schema()
    timeout = max(5, settings.review_timeout_sec)

    try:
        text = await asyncio.wait_for(
            asyncio.to_thread(
                _generate_sync, client, settings.gemini_model, user_text, schema
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        raise GeminiReviewError(
            f"AI review timed out after {timeout}s (increase REVIEW_TIMEOUT_SEC if needed)."
        ) from None
    except genai_errors.APIError as e:
        logger.warning("gemini API error: %s", e)
        if e.code == 404:
            raise GeminiReviewError(
                "Gemini model was not found (often retired for new keys). "
                "Set GEMINI_MODEL to a current model, e.g. gemini-2.5-flash, in your .env."
            ) from e
        if e.code in (401, 403):
            raise GeminiReviewError(
                "Gemini API rejected the request (check GEMINI_API_KEY)."
            ) from e
        raise GeminiReviewError("AI review failed (Gemini API error).") from e
    except GeminiReviewError:
        raise
    except Exception as e:
        logger.warning("gemini call failed: %s", e)
        raise GeminiReviewError("AI review failed") from e

    try:
        return _parse_review_json(text)
    except json.JSONDecodeError:
        pass

    repair_prompt = f"""The following text should be a single JSON object with keys:
summary (string), findings (array), better_implementation_code (string), better_implementation_explanation (string).
Fix it to valid JSON only, no markdown. Findings items: category (security|performance|logic|style), title, detail, suggestion, optional severity, line_start, line_end.

Broken content:
{text[:12000]}"""

    try:
        fixed = await asyncio.wait_for(
            asyncio.to_thread(
                _generate_sync, client, settings.gemini_model, repair_prompt, schema
            ),
            timeout=timeout,
        )
        return _parse_review_json(fixed)
    except asyncio.TimeoutError:
        raise GeminiReviewError(
            f"AI review repair timed out after {timeout}s (increase REVIEW_TIMEOUT_SEC if needed)."
        ) from None
    except genai_errors.APIError as e:
        logger.warning("gemini repair API error: %s", e)
        raise GeminiReviewError("AI review returned invalid data (follow-up request failed).") from e
    except Exception as e:
        logger.warning("gemini repair failed: %s", e)
        raise GeminiReviewError("AI review returned invalid data") from e
