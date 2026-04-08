#!/usr/bin/env python3
"""Run the production review pipeline on every dataset row and write run artifacts."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_BACKEND = _REPO / "backend"
for _p in (_REPO, _BACKEND):
    s = str(_p)
    if s not in sys.path:
        sys.path.insert(0, s)

from app.config import get_settings
from app.llm.gemini_review import GeminiReviewError, review_code_async
from app.models import Language, ReviewResponse
from app.sanitize import sanitize_code
from app.syntax_check import check_syntax

from eval.align import build_summary
from eval.paths import DATASET_PATH, EVAL_DIR, RUNS_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_dataset(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def default_run_id(label: str | None) -> str:
    base = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{base}_{label}" if label else base


async def review_one(settings, row: dict) -> dict:
    cid = row["id"]
    lang_raw = row["language"]
    try:
        language = Language(lang_raw)
    except ValueError:
        return {
            "id": cid,
            "language": lang_raw,
            "error": f"invalid language: {lang_raw!r}",
            "review": None,
        }
    raw_code = row.get("code") or ""
    try:
        code = sanitize_code(raw_code, settings)
    except ValueError as e:
        return {
            "id": cid,
            "language": lang_raw,
            "error": str(e),
            "review": None,
        }
    syntax = check_syntax(language, code)
    try:
        summary, findings, better_code, better_expl = await review_code_async(
            settings=settings,
            language=language,
            code=code,
            syntax=syntax,
        )
        resp = ReviewResponse(
            syntax=syntax,
            findings=findings,
            summary=summary,
            better_implementation_code=better_code,
            better_implementation_explanation=better_expl,
        )
        return {
            "id": cid,
            "language": lang_raw,
            "error": None,
            "review": resp.model_dump(mode="json"),
        }
    except GeminiReviewError as e:
        logger.warning("case %s: review failed: %s", cid, e)
        return {
            "id": cid,
            "language": lang_raw,
            "error": str(e),
            "review": None,
        }


async def run_all(
    *,
    dataset_path: Path,
    run_dir: Path,
    label: str | None,
) -> Path:
    settings = get_settings()
    rows = load_dataset(dataset_path)
    run_id = default_run_id(label)
    out = run_dir / run_id
    out.mkdir(parents=True, exist_ok=True)

    manifest = {
        "run_id": run_id,
        "gemini_model": settings.gemini_model,
        "dataset_path": str(dataset_path.resolve()),
        "case_count": len(rows),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    results: list[dict] = []
    for row in rows:
        res = await review_one(settings, row)
        results.append(res)
        case_path = out / f"case_{res['id']}.json"
        case_path.write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")

    case_results_for_summary = []
    for r in results:
        if r.get("error"):
            case_results_for_summary.append(
                {"error": r["error"], "review": {"findings": []}}
            )
        else:
            case_results_for_summary.append({"error": None, "review": r["review"]})

    summary = build_summary(
        run_id,
        settings.gemini_model,
        rows,
        case_results_for_summary,
    )
    summary_path = out / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    manifest["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    latest = out.parent / "LATEST"
    latest.write_text(str(out.resolve()) + "\n", encoding="utf-8")
    logger.info("Wrote run to %s", out)
    print(out.resolve())
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Run eval batch against dataset.jsonl")
    p.add_argument(
        "--dataset",
        type=Path,
        default=DATASET_PATH,
        help="Path to dataset.jsonl",
    )
    p.add_argument(
        "--runs-dir",
        type=Path,
        default=RUNS_DIR,
        help="Directory for eval runs",
    )
    p.add_argument("--label", type=str, default=None, help="Optional suffix for run_id")
    args = p.parse_args()
    if not args.dataset.is_file():
        raise SystemExit(f"Dataset not found: {args.dataset}")
    args.runs_dir.mkdir(parents=True, exist_ok=True)
    asyncio.run(
        run_all(
            dataset_path=args.dataset,
            run_dir=args.runs_dir.resolve(),
            label=args.label,
        )
    )


if __name__ == "__main__":
    main()
