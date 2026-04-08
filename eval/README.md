# Code-review eval harness

This folder benchmarks the Gemini reviewer in [`backend/app/llm/gemini_review.py`](../backend/app/llm/gemini_review.py) using the same pipeline as `POST /api/review` (sanitize → syntax → review). See also [`../overview.md`](../overview.md).

## Layout

| Path | Role |
|------|------|
| `dataset.jsonl` | One JSON object per line: `id`, `language`, `code`, `ground_truth[]` with `category`, `tag_id`, `signals[]`. Optional `source`, `added_in_run`. |
| `align.py` | Deterministic **match** / **miss** / **extra** (signal substring in finding text, same category). |
| `run_batch.py` | Calls `review_code_async` for every row; writes `runs/<run_id>/case_*.json`, `summary.json`, updates `runs/LATEST`. |
| `judge.py` | Gemini JSON: verdicts for **extras** and **misses**. |
| `summarize.py` | Appends `results.md`, `agent_changes_memory.md`; writes `prompt_proposal.json`. |
| `apply_prompts.py` | Optional `--apply`: patch prompt markers in `gemini_review.py`, then `import` + `pytest`. |
| `expand_dataset.py` | Appends **5** validated rows to `dataset.jsonl` (Gemini). |
| `orchestrate.py` | **Full pipeline**; use **`--loop`** to include dataset expansion. |

## Prerequisites

- Backend venv with `requirements.txt` installed.
- `GEMINI_API_KEY` in repo or `backend` `.env` (see `.env.example`).
- Optional: `EVAL_JUDGE_MODEL` to override the model for judge/summarize/expand (defaults to `GEMINI_MODEL`).

## Commands (from repository root)

Set `PYTHONPATH` to the repo root so `eval` and `app` resolve:

```bash
export PYTHONPATH="$(pwd)"
```

### One-off batch (no dataset growth)

```bash
python3 -m eval.run_batch
python3 eval/judge.py "$(cat eval/runs/LATEST)"
python3 eval/summarize.py "$(cat eval/runs/LATEST)"
# Optional: apply proposed prompts (mutates gemini_review.py after tests pass)
python3 eval/apply_prompts.py "$(cat eval/runs/LATEST)" --apply
```

Same steps in one command (still **no** dataset expansion):

```bash
python3 eval/orchestrate.py
```

### Full loop (batch + judge + summarize + **+5 dataset rows**)

```bash
python3 eval/orchestrate.py --loop
```

`/loop` in Cursor means: run the same as `python3 eval/orchestrate.py --loop` from the repo root with `PYTHONPATH` set.

### Flags

| Flag | Effect |
|------|--------|
| `--loop` | After summarize (and optional `--apply`), run `expand_dataset.py` and append a note to `results.md`. |
| `--no-expand` | With `--loop`, skip the +5 append. |
| `--skip-judge` | Skip `judge.py`. |
| `--skip-llm-proposal` | Summarize without calling Gemini for `prompt_proposal.json`. |
| `--apply` | After summarize, run `apply_prompts.py --apply`. |
| `--expand-only` | Only run expansion using the latest `eval/runs/LATEST` run artifacts. |

## Metrics

- **Match**: ground-truth tag aligned to a finding (same `category`, at least one `signals` phrase found in `title`+`detail`+`suggestion`).
- **Miss**: tag with no matching finding.
- **Extra**: finding not consumed by any tag.

Aggregate precision / recall / F1 are **tag-level** (TP = matches, FP = extras, FN = misses).

## Human edits

- Remove or fix bad rows in `dataset.jsonl` before the next loop.
- If `expand_dataset` fails validation, re-run or hand-author five rows following the same JSON shape.
