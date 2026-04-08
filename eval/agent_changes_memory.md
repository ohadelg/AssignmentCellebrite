# Agent changes memory (eval-driven)

High-level log tied to eval runs: metrics snapshot, where prompt proposals live, and **applied** prompt updates (after `eval/apply_prompts.py --apply` passes import + pytest).

---
### 2026-04-08 13:00 UTC — run `20260408T125101Z`

Metrics: P=0.306 R=0.704 F1=0.427 (TP=19 FP=43 FN=8).
Judge: 42/43 legitimate extras; 6/8 unfair misses.
Prompt proposal: `prompt_proposal.json` (change_prompts=True). Use `eval/apply_prompts.py` with `--apply` to validate and patch.

