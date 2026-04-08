#!/usr/bin/env python3
"""Append results.md, agent_changes_memory.md, and write prompt_proposal.json."""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
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
from app.llm.gemini_review import REVIEW_USER_TEMPLATE, SYSTEM_INSTRUCTION

from eval.llm_json import generate_json_object
from eval.paths import DATASET_PATH, EVAL_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RESULTS_MD = EVAL_DIR / "results.md"
MEMORY_MD = EVAL_DIR / "agent_changes_memory.md"

PROPOSAL_SCHEMA = {
    "type": "object",
    "properties": {
        "change_prompts": {"type": "boolean"},
        "rationale": {"type": "string"},
        "highlights": {
            "type": "array",
            "items": {"type": "string"},
        },
        "system_instruction": {"type": "string"},
        "review_user_template": {"type": "string"},
    },
    "required": [
        "change_prompts",
        "rationale",
        "highlights",
        "system_instruction",
        "review_user_template",
    ],
}

SUMMARIZER_SYSTEM = """You improve a code-review agent by proposing prompt updates.
You are given metrics, per-case alignment, and judge verdicts. Propose updated SYSTEM_INSTRUCTION and REVIEW_USER_TEMPLATE strings for the reviewer.
The REVIEW_USER_TEMPLATE MUST keep Python str.format placeholders exactly: {language}, {syntax_valid}, {syntax_errors}, {code} — do not remove or rename them.
If small tweaks are enough, set change_prompts true and provide full replacement strings. If no change is warranted, set change_prompts false and repeat the current prompts unchanged.
Return JSON only matching the schema."""


def _git_sha() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_REPO,
            capture_output=True,
            text=True,
            check=False,
        )
        return (r.stdout or "").strip() or "unknown"
    except OSError:
        return "unknown"


def _dataset_size(path: Path) -> int:
    n = 0
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def build_markdown_table(per_case: list[dict]) -> str:
    lines = ["| case | match | miss | extra |", "| --- | ---: | ---: | ---: |"]
    for b in per_case:
        c = b["counts"]
        lines.append(
            f"| {b['id']} | {c['match']} | {c['miss']} | {c['extra']} |"
        )
    return "\n".join(lines) + "\n"


def summarize_run(
    run_dir: Path,
    dataset_path: Path,
    *,
    skip_llm_proposal: bool = False,
) -> Path:
    settings = get_settings()
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    judge_path = run_dir / "judge.json"
    judge = (
        json.loads(judge_path.read_text(encoding="utf-8"))
        if judge_path.is_file()
        else {"extras_verdicts": [], "misses_verdicts": []}
    )

    run_id = summary["run_id"]
    model = summary.get("model", settings.gemini_model)
    agg = summary.get("aggregate", {})
    n_cases = len(summary.get("per_case", []))
    ds_size = _dataset_size(dataset_path)
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    extras_v = judge.get("extras_verdicts") or []
    misses_v = judge.get("misses_verdicts") or []
    legit_extras = sum(1 for v in extras_v if v.get("legitimate"))
    unfair_misses = sum(1 for v in misses_v if not v.get("fair_miss"))

    md = []
    md.append(f"## Run `{run_id}`")
    md.append("")
    md.append(f"- **When**: {when}")
    md.append(f"- **Model**: `{model}`")
    md.append(f"- **Git**: `{_git_sha()}`")
    md.append(f"- **Dataset rows**: {ds_size} (evaluated cases this run: {n_cases})")
    md.append("")
    md.append("### Aggregate (tag-level)")
    md.append("")
    md.append(
        f"- TP (matches): {int(agg.get('tp', 0))}, FP (extras): {int(agg.get('fp', 0))}, FN (misses): {int(agg.get('fn', 0))}"
    )
    md.append(
        f"- Precision: {agg.get('precision', 0):.3f}, Recall: {agg.get('recall', 0):.3f}, F1: {agg.get('f1', 0):.3f}"
    )
    md.append("")
    md.append("### Judge rollup")
    md.append("")
    md.append(
        f"- Extras judged legitimate: {legit_extras} / {len(extras_v) if extras_v else 0}"
    )
    md.append(
        f"- Misses judged unfair (should have caught): {unfair_misses} / {len(misses_v) if misses_v else 0}"
    )
    md.append("")
    md.append("### Per case")
    md.append("")
    md.append(build_markdown_table(summary.get("per_case", [])))
    md.append("### Highlights (from judge deltas)")
    md.append("")
    bullets: list[str] = []
    for v in extras_v[:12]:
        for b in v.get("suggested_prompt_delta") or []:
            if b and b not in bullets:
                bullets.append(b)
    for v in misses_v[:12]:
        for b in v.get("suggested_prompt_delta") or []:
            if b and b not in bullets:
                bullets.append(b)
    if not bullets:
        md.append("- _(none)_\n")
    else:
        for b in bullets[:20]:
            md.append(f"- {b}")
        md.append("")

    RESULTS_MD.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_MD.open("a", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")

    proposal_path = run_dir / "prompt_proposal.json"

    if skip_llm_proposal:
        proposal = {
            "change_prompts": False,
            "rationale": "LLM proposal skipped (--skip-llm-proposal).",
            "highlights": bullets[:20],
            "system_instruction": SYSTEM_INSTRUCTION,
            "review_user_template": REVIEW_USER_TEMPLATE,
        }
        proposal_path.write_text(json.dumps(proposal, indent=2) + "\n", encoding="utf-8")
    else:
        ctx = {
            "current_system_instruction": SYSTEM_INSTRUCTION,
            "current_review_user_template": REVIEW_USER_TEMPLATE,
            "aggregate": agg,
            "per_case": summary.get("per_case", []),
            "extras_verdicts": extras_v,
            "misses_verdicts": misses_v,
        }
        user = json.dumps(ctx, indent=2)[:120000]
        proposal = generate_json_object(
            settings=settings,
            system_instruction=SUMMARIZER_SYSTEM,
            user_text=user,
            schema=PROPOSAL_SCHEMA,
            temperature=0.3,
        )
        proposal_path.write_text(json.dumps(proposal, indent=2) + "\n", encoding="utf-8")

    mem = []
    mem.append(f"### {when} — run `{run_id}`")
    mem.append("")
    mem.append(
        f"Metrics: P={agg.get('precision', 0):.3f} R={agg.get('recall', 0):.3f} F1={agg.get('f1', 0):.3f} "
        f"(TP={int(agg.get('tp', 0))} FP={int(agg.get('fp', 0))} FN={int(agg.get('fn', 0))})."
    )
    mem.append(
        f"Judge: {legit_extras}/{len(extras_v) or 0} legitimate extras; "
        f"{unfair_misses}/{len(misses_v) or 0} unfair misses."
    )
    mem.append(
        f"Prompt proposal: `prompt_proposal.json` (change_prompts="
        f"{proposal.get('change_prompts')}). Use `eval/apply_prompts.py` with `--apply` to validate and patch."
    )
    mem.append("")
    with MEMORY_MD.open("a", encoding="utf-8") as f:
        f.write("\n".join(mem) + "\n")

    logger.info("Appended %s and %s; wrote %s", RESULTS_MD, MEMORY_MD, proposal_path)
    return proposal_path


def main() -> None:
    p = argparse.ArgumentParser(description="Summarize an eval run")
    p.add_argument("run_dir", type=Path)
    p.add_argument("--dataset", type=Path, default=DATASET_PATH)
    p.add_argument(
        "--skip-llm-proposal",
        action="store_true",
        help="Do not call Gemini; write a no-op proposal using current prompts",
    )
    args = p.parse_args()
    summarize_run(
        args.run_dir.resolve(),
        args.dataset.resolve(),
        skip_llm_proposal=args.skip_llm_proposal,
    )


if __name__ == "__main__":
    main()
