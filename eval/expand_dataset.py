#!/usr/bin/env python3
"""Append five benchmark rows to dataset.jsonl using Gemini (gap-focused)."""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_BACKEND = _REPO / "backend"
for _p in (_REPO, _BACKEND):
    s = str(_p)
    if s not in sys.path:
        sys.path.insert(0, s)

from app.config import Settings, get_settings
from app.models import Language
from app.sanitize import sanitize_code
from app.syntax_check import check_syntax

from eval.llm_json import generate_json_object
from eval.paths import DATASET_PATH

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EXPAND_SYSTEM = """You are building a code-review evaluation dataset.
Given aggregate metrics, judge notes, and existing benchmark ids, propose exactly 5 NEW code snippets with ground-truth tags.
Each snippet should target weaknesses implied by misses/unfair-misses: diverse security, performance, logic, and style issues.
Use realistic code. IDs must be unique kebab-case, not colliding with existing_ids.
Return JSON only matching the schema."""

EXPAND_SCHEMA = {
    "type": "object",
    "properties": {
        "cases": {
            "type": "array",
            "minItems": 5,
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "language": {
                        "type": "string",
                        "enum": ["python", "typescript", "java"],
                    },
                    "code": {"type": "string"},
                    "ground_truth": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "properties": {
                                "category": {
                                    "type": "string",
                                    "enum": ["security", "performance", "logic", "style"],
                                },
                                "tag_id": {"type": "string"},
                                "signals": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "minItems": 1,
                                },
                            },
                            "required": ["category", "tag_id", "signals"],
                        },
                    },
                },
                "required": ["id", "language", "code", "ground_truth"],
            },
        }
    },
    "required": ["cases"],
}

def load_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    if not path.is_file():
        return ids
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            ids.add(row["id"])
    return ids


def validate_case(row: dict, settings: Settings, existing: set[str]) -> str | None:
    cid = row.get("id") or ""
    if not cid or not re.match(r"^[a-z0-9][a-z0-9_-]*$", cid):
        return "invalid id"
    if cid in existing:
        return "duplicate id"
    try:
        Language(row["language"])
    except ValueError:
        return "invalid language"
    code = row.get("code") or ""
    try:
        sanitized = sanitize_code(code, settings)
    except ValueError as e:
        return f"sanitize: {e}"
    lang = Language(row["language"])
    syn = check_syntax(lang, sanitized)
    if not syn.valid:
        return "syntax invalid"
    gt = row.get("ground_truth") or []
    if not gt:
        return "empty ground_truth"
    for t in gt:
        if t.get("category") not in (
            "security",
            "performance",
            "logic",
            "style",
        ):
            return "bad tag category"
        if not (t.get("signals") or []):
            return "empty signals"
    return None


def append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def expand_from_run(
    run_dir: Path,
    dataset_path: Path,
    *,
    added_in_run: str,
    settings: Settings | None = None,
) -> list[str]:
    settings = settings or get_settings()
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    judge_path = run_dir / "judge.json"
    judge = (
        json.loads(judge_path.read_text(encoding="utf-8"))
        if judge_path.is_file()
        else {}
    )
    existing = load_ids(dataset_path)
    ctx = {
        "aggregate": summary.get("aggregate", {}),
        "per_case": summary.get("per_case", []),
        "extras_verdicts": judge.get("extras_verdicts", []),
        "misses_verdicts": judge.get("misses_verdicts", []),
        "existing_ids": sorted(existing),
    }
    user = json.dumps(ctx, indent=2)[:120000]
    raw = generate_json_object(
        settings=settings,
        system_instruction=EXPAND_SYSTEM,
        user_text=user,
        schema=EXPAND_SCHEMA,
        temperature=0.4,
    )
    cases = raw.get("cases") or []
    if len(cases) != 5:
        raise RuntimeError(f"Expected 5 cases, got {len(cases)}")

    accepted: list[dict] = []
    new_ids: list[str] = []
    for c in cases:
        err = validate_case(c, settings, existing)
        if err:
            logger.warning("drop case %r: %s", c.get("id"), err)
            continue
        row = {
            "id": c["id"],
            "language": c["language"],
            "code": c["code"],
            "ground_truth": c["ground_truth"],
            "source": "loop_expand",
            "added_in_run": added_in_run,
        }
        accepted.append(row)
        existing.add(c["id"])
        new_ids.append(c["id"])

    if len(accepted) < 5:
        raise RuntimeError(
            f"Fewer than 5 valid cases after validation ({len(accepted)}). "
            "Re-run expand or edit dataset manually."
        )

    append_jsonl(dataset_path, accepted)
    logger.info("Appended %s new ids: %s", len(new_ids), new_ids)
    return new_ids


def write_expand_manifest(run_dir: Path, new_ids: list[str], dataset_path: Path) -> None:
    payload = {
        "new_ids": new_ids,
        "dataset_path": str(dataset_path.resolve()),
    }
    (run_dir / "expand.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Expand dataset by 5 cases from a run")
    p.add_argument("run_dir", type=Path)
    p.add_argument("--dataset", type=Path, default=DATASET_PATH)
    p.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Label stored as added_in_run (default: run folder name)",
    )
    args = p.parse_args()
    run_dir = args.run_dir.resolve()
    rid = args.run_id or run_dir.name
    ds = args.dataset.resolve()
    new_ids = expand_from_run(run_dir, ds, added_in_run=rid)
    write_expand_manifest(run_dir, new_ids, ds)


if __name__ == "__main__":
    main()
