"""Small Gemini JSON helpers for eval-only calls (judge, summarize, expand)."""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

# Ensure backend app package is importable when running as a script
_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from google import genai
from google.genai import types

from app.config import Settings

logger = logging.getLogger(__name__)


def eval_model_name(settings: Settings) -> str:
    return (os.environ.get("EVAL_JUDGE_MODEL") or settings.gemini_model).strip()


def _generate_raw(
    client: genai.Client,
    model: str,
    *,
    system_instruction: str,
    user_text: str,
    schema: dict[str, Any],
    temperature: float,
    max_output_tokens: int,
) -> str:
    config = types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        system_instruction=system_instruction,
        response_mime_type="application/json",
        response_json_schema=schema,
    )
    response = client.models.generate_content(
        model=model,
        contents=user_text,
        config=config,
    )
    return (response.text or "").strip()


def generate_json_object(
    *,
    settings: Settings,
    system_instruction: str,
    user_text: str,
    schema: dict[str, Any],
    temperature: float = 0.2,
    max_output_tokens: int = 32768,
) -> dict[str, Any]:
    if not settings.gemini_api_key.strip():
        raise RuntimeError("GEMINI_API_KEY is required for eval LLM steps")
    client = genai.Client(api_key=settings.gemini_api_key)
    model = eval_model_name(settings)
    text = _generate_raw(
        client,
        model,
        system_instruction=system_instruction,
        user_text=user_text,
        schema=schema,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )
    if not text:
        raise RuntimeError("Empty JSON response from eval model")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("eval JSON parse failed (%s), attempting repair", e)
        repair_user = (
            "The following text must become one valid JSON object matching the given schema. "
            "Output JSON only, no markdown. Fix truncation, stray quotes, and commas.\n\n"
            f"Broken content (first 24000 chars):\n{text[:24000]}"
        )
        fixed = _generate_raw(
            client,
            model,
            system_instruction="You output only valid JSON matching the schema.",
            user_text=repair_user,
            schema=schema,
            temperature=0.0,
            max_output_tokens=max_output_tokens,
        )
        if not fixed:
            raise RuntimeError("Empty JSON from eval model (repair)") from e
        return json.loads(fixed)
