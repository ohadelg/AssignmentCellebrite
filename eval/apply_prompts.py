#!/usr/bin/env python3
"""Apply prompt_proposal.json to gemini_review.py with validation (import + pytest)."""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_BACKEND = _REPO / "backend"
GEMINI_REVIEW = _BACKEND / "app" / "llm" / "gemini_review.py"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REQUIRED_PLACEHOLDERS = ("{language}", "{syntax_valid}", "{syntax_errors}", "{code}")


def replace_marked_block(text: str, begin: str, end: str, const: str, new_value: str) -> str:
    inner = json.dumps(new_value)
    block = f"{begin}\n{const} = {inner}\n{end}"
    pat = re.compile(
        rf"{re.escape(begin)}\n{re.escape(const)} = [\s\S]*?\n{re.escape(end)}",
        re.MULTILINE,
    )
    new_text, n = pat.subn(block, text, count=1)
    if n != 1:
        raise RuntimeError(f"Could not replace block for {const}")
    return new_text


def validate_template(tpl: str) -> None:
    for ph in REQUIRED_PLACEHOLDERS:
        if ph not in tpl:
            raise ValueError(f"REVIEW_USER_TEMPLATE missing placeholder {ph!r}")


def run_pytest() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=_BACKEND,
        check=False,
    )
    if r.returncode != 0:
        raise RuntimeError("pytest failed after prompt patch")


def import_check() -> None:
    r = subprocess.run(
        [sys.executable, "-c", "import app.llm.gemini_review"],
        cwd=_BACKEND,
        check=False,
    )
    if r.returncode != 0:
        raise RuntimeError("import app.llm.gemini_review failed")


def apply_proposal(run_dir: Path, *, dry_run: bool) -> bool:
    proposal_path = run_dir / "prompt_proposal.json"
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    if not proposal.get("change_prompts"):
        logger.info("proposal.change_prompts is false; nothing to apply")
        return False

    si = proposal.get("system_instruction") or ""
    tpl = proposal.get("review_user_template") or ""
    validate_template(tpl)

    original = GEMINI_REVIEW.read_text(encoding="utf-8")
    updated = replace_marked_block(
        original,
        "# BEGIN SYSTEM_INSTRUCTION",
        "# END SYSTEM_INSTRUCTION",
        "SYSTEM_INSTRUCTION",
        si,
    )
    updated = replace_marked_block(
        updated,
        "# BEGIN REVIEW_USER_TEMPLATE",
        "# END REVIEW_USER_TEMPLATE",
        "REVIEW_USER_TEMPLATE",
        tpl,
    )

    if dry_run:
        logger.info("Dry run: would patch %s", GEMINI_REVIEW)
        return True

    backup = GEMINI_REVIEW.with_suffix(".py.bak")
    shutil.copyfile(GEMINI_REVIEW, backup)
    try:
        GEMINI_REVIEW.write_text(updated, encoding="utf-8")
        import_check()
        run_pytest()
    except Exception:
        shutil.copyfile(backup, GEMINI_REVIEW)
        logger.exception("Reverted %s after failure", GEMINI_REVIEW)
        raise
    finally:
        if backup.is_file():
            backup.unlink(missing_ok=True)

    logger.info("Patched %s and tests passed", GEMINI_REVIEW)
    return True


def append_memory_applied(run_id: str, rationale: str) -> None:
    mem = _REPO / "eval" / "agent_changes_memory.md"
    line = (
        f"\n**Applied prompts** (run `{run_id}`): {rationale.strip()}\n\n"
    )
    with mem.open("a", encoding="utf-8") as f:
        f.write(line)


def main() -> None:
    p = argparse.ArgumentParser(description="Apply prompt proposal to gemini_review.py")
    p.add_argument("run_dir", type=Path)
    p.add_argument(
        "--apply",
        action="store_true",
        help="Actually write file and run pytest; default is dry-run",
    )
    args = p.parse_args()
    run_dir = args.run_dir.resolve()
    applied = apply_proposal(run_dir, dry_run=not args.apply)
    if args.apply and applied:
        prop = json.loads((run_dir / "prompt_proposal.json").read_text(encoding="utf-8"))
        append_memory_applied(run_dir.name, prop.get("rationale") or "")


if __name__ == "__main__":
    main()
