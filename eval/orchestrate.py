#!/usr/bin/env python3
"""Run the full eval pipeline: batch → align (in batch) → judge → summarize → optional apply → optional expand."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_BACKEND = _REPO / "backend"
EVAL_DIR = _REPO / "eval"
RUNS_DIR = EVAL_DIR / "runs"
DATASET_PATH = EVAL_DIR / "dataset.jsonl"


def _env() -> dict[str, str]:
    pp = str(_REPO)
    if _BACKEND.exists():
        pp = pp + os.pathsep + str(_BACKEND)
    return {**os.environ, "PYTHONPATH": pp}


def _run(cmd: list[str], *, cwd: Path | None = None) -> None:
    r = subprocess.run(cmd, cwd=cwd or _REPO, env=_env(), check=False)
    if r.returncode != 0:
        raise SystemExit(r.returncode)


def _read_latest_run() -> Path:
    p = RUNS_DIR / "LATEST"
    if not p.is_file():
        raise SystemExit("No LATEST pointer; run_batch did not complete")
    return Path(p.read_text(encoding="utf-8").strip())


def _dataset_line_count(path: Path) -> int:
    n = 0
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def _append_expand_note(run_dir: Path, before: int, after: int, new_ids: list[str]) -> None:
    results = EVAL_DIR / "results.md"
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    block = (
        f"\n### Dataset expansion ({when}, run `{run_dir.name}`)\n\n"
        f"- Rows before: **{before}**, after: **{after}** (+{after - before})\n"
        f"- New ids: {', '.join(new_ids)}\n\n"
    )
    with results.open("a", encoding="utf-8") as f:
        f.write(block)


def main() -> None:
    p = argparse.ArgumentParser(description="Eval orchestrator (/loop)")
    p.add_argument(
        "--loop",
        action="store_true",
        help="Full cycle including dataset expansion (+5) unless --no-expand",
    )
    p.add_argument(
        "--no-expand",
        action="store_true",
        help="Skip expand_dataset step",
    )
    p.add_argument(
        "--skip-judge",
        action="store_true",
        help="Skip judge.py (summarize will see empty verdicts unless judge.json exists)",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Run apply_prompts.py --apply after summarize",
    )
    p.add_argument(
        "--skip-llm-proposal",
        action="store_true",
        help="Summarize without calling Gemini for prompt_proposal",
    )
    p.add_argument("--label", type=str, default=None, help="Suffix for run_id (run_batch)")
    p.add_argument(
        "--dataset",
        type=Path,
        default=DATASET_PATH,
    )
    p.add_argument(
        "--expand-only",
        action="store_true",
        help="Only run expand_dataset.py on the latest run (advanced)",
    )
    args = p.parse_args()

    py = sys.executable

    if args.expand_only:
        run_dir = _read_latest_run()
        _run([py, str(EVAL_DIR / "expand_dataset.py"), str(run_dir), "--dataset", str(args.dataset)])
        return

    ds_before = _dataset_line_count(args.dataset)

    batch_cmd = [
        py,
        "-m",
        "eval.run_batch",
        "--dataset",
        str(args.dataset),
        "--runs-dir",
        str(RUNS_DIR),
    ]
    if args.label:
        batch_cmd += ["--label", args.label]
    _run(batch_cmd)

    run_dir = _read_latest_run()

    if not args.skip_judge:
        _run(
            [
                py,
                str(EVAL_DIR / "judge.py"),
                str(run_dir),
                "--dataset",
                str(args.dataset),
            ]
        )

    _run(
        [
            py,
            str(EVAL_DIR / "summarize.py"),
            str(run_dir),
            "--dataset",
            str(args.dataset),
        ]
        + (["--skip-llm-proposal"] if args.skip_llm_proposal else [])
    )

    if args.apply:
        _run([py, str(EVAL_DIR / "apply_prompts.py"), str(run_dir), "--apply"])

    if args.loop and not args.no_expand:
        _run(
            [
                py,
                str(EVAL_DIR / "expand_dataset.py"),
                str(run_dir),
                "--dataset",
                str(args.dataset),
                "--run-id",
                run_dir.name,
            ]
        )
        expand_manifest = run_dir / "expand.json"
        new_ids: list[str] = []
        if expand_manifest.is_file():
            new_ids = json.loads(expand_manifest.read_text(encoding="utf-8")).get(
                "new_ids", []
            )
        ds_after = _dataset_line_count(args.dataset)
        _append_expand_note(run_dir, ds_before, ds_after, new_ids)


if __name__ == "__main__":
    # expand-only path does not need asyncio; run_batch uses asyncio internally via subprocess
    main()
