#!/usr/bin/env python3
"""LLM judges for extra findings and missed ground-truth tags."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_BACKEND = _REPO / "backend"
for _p in (_REPO, _BACKEND):
    s = str(_p)
    if s not in sys.path:
        sys.path.insert(0, s)

from app.config import get_settings

from eval.llm_json import generate_json_object
from eval.paths import DATASET_PATH

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EXTRAS_SYSTEM = """You are an evaluation judge. Given code and an extra finding from another model (not matched to benchmark tags), decide if the finding is a legitimate issue for its category or mostly noise/false positive.
Return JSON only matching the schema."""

MISSES_SYSTEM = """You are an evaluation judge. Given code and a ground-truth tag the reviewer model missed, decide if missing it is fair (ambiguous/hard) or the reviewer should have caught it.
Return JSON only matching the schema."""

EXTRAS_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "case_id": {"type": "string"},
                    "finding_index": {"type": "integer"},
                    "legitimate": {"type": "boolean"},
                    "rationale": {"type": "string"},
                    "suggested_prompt_delta": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "case_id",
                    "finding_index",
                    "legitimate",
                    "rationale",
                    "suggested_prompt_delta",
                ],
            },
        }
    },
    "required": ["verdicts"],
}

MISSES_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "case_id": {"type": "string"},
                    "tag_id": {"type": "string"},
                    "fair_miss": {"type": "boolean"},
                    "rationale": {"type": "string"},
                    "suggested_prompt_delta": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "case_id",
                    "tag_id",
                    "fair_miss",
                    "rationale",
                    "suggested_prompt_delta",
                ],
            },
        }
    },
    "required": ["verdicts"],
}

# Large verdict lists can exceed output token limits; judge in batches.
_JUDGE_CHUNK_SIZE = 10


def load_dataset_map(path: Path) -> dict[str, dict]:
    m: dict[str, dict] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            m[row["id"]] = row
    return m


def collect_items(
    summary: dict,
    dataset_by_id: dict[str, dict],
) -> tuple[list[dict], list[dict]]:
    extras_payload: list[dict] = []
    misses_payload: list[dict] = []
    for block in summary.get("per_case", []):
        cid = block["id"]
        row = dataset_by_id.get(cid, {})
        code = row.get("code", "")
        for ex in block.get("extras", []):
            fi = ex.get("finding_index")
            fi_int = fi if isinstance(fi, int) else int(fi) if fi is not None else -1
            fd = ex.get("finding") or {}
            extras_payload.append(
                {
                    "case_id": cid,
                    "finding_index": fi_int,
                    "language": row.get("language"),
                    "code": code,
                    "finding": fd,
                }
            )
        for miss in block.get("misses", []):
            misses_payload.append(
                {
                    "case_id": cid,
                    "tag_id": miss.get("tag_id"),
                    "category": miss.get("category"),
                    "signals": miss.get("signals"),
                    "code": code,
                }
            )
    return extras_payload, misses_payload


def run_judge(run_dir: Path, dataset_path: Path) -> Path:
    settings = get_settings()
    summary_path = run_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    ds = load_dataset_map(dataset_path)
    extras, misses = collect_items(summary, ds)

    out: dict = {"extras_verdicts": [], "misses_verdicts": [], "raw": {}}

    if extras:
        all_ex: list[dict] = []
        raw_extras: list[dict] = []
        for i in range(0, len(extras), _JUDGE_CHUNK_SIZE):
            chunk = extras[i : i + _JUDGE_CHUNK_SIZE]
            user = json.dumps({"items": chunk}, indent=2)
            ex = generate_json_object(
                settings=settings,
                system_instruction=EXTRAS_SYSTEM,
                user_text=user,
                schema=EXTRAS_SCHEMA,
            )
            all_ex.extend(ex.get("verdicts") or [])
            raw_extras.append(ex)
        out["extras_verdicts"] = all_ex
        out["raw"]["extras"] = {"verdicts": all_ex, "chunks": raw_extras}
    else:
        out["raw"]["extras"] = {"verdicts": []}

    if misses:
        all_ms: list[dict] = []
        raw_misses: list[dict] = []
        for i in range(0, len(misses), _JUDGE_CHUNK_SIZE):
            chunk = misses[i : i + _JUDGE_CHUNK_SIZE]
            user = json.dumps({"items": chunk}, indent=2)
            ms = generate_json_object(
                settings=settings,
                system_instruction=MISSES_SYSTEM,
                user_text=user,
                schema=MISSES_SCHEMA,
            )
            all_ms.extend(ms.get("verdicts") or [])
            raw_misses.append(ms)
        out["misses_verdicts"] = all_ms
        out["raw"]["misses"] = {"verdicts": all_ms, "chunks": raw_misses}
    else:
        out["raw"]["misses"] = {"verdicts": []}

    judge_path = run_dir / "judge.json"
    judge_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    logger.info("Wrote %s", judge_path)
    return judge_path


def main() -> None:
    p = argparse.ArgumentParser(description="Run eval judges on a run directory")
    p.add_argument("run_dir", type=Path, help="Path to eval/runs/<run_id>")
    p.add_argument(
        "--dataset",
        type=Path,
        default=DATASET_PATH,
    )
    args = p.parse_args()
    if not args.run_dir.is_dir():
        raise SystemExit(f"Not a directory: {args.run_dir}")
    run_judge(args.run_dir.resolve(), args.dataset.resolve())


if __name__ == "__main__":
    main()
