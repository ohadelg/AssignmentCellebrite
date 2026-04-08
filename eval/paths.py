from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = REPO_ROOT / "eval"
BACKEND_DIR = REPO_ROOT / "backend"
DATASET_PATH = EVAL_DIR / "dataset.jsonl"
RUNS_DIR = EVAL_DIR / "runs"
