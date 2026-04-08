#!/usr/bin/env python3
"""Runs inside the sandbox container. Reads JSON from stdin, writes JSON result to stdout."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

_TIMEOUT_EXIT = 124


def _cmd_timeout_sec() -> int:
    raw = os.environ.get("SANDBOX_CMD_TIMEOUT_SEC", "").strip()
    if not raw:
        return 14
    try:
        return max(1, int(raw))
    except ValueError:
        return 14


def _run_cmd(
    cmd: list[str],
    stdin_bytes: bytes,
    cwd: str | None = None,
    timeout_sec: int | None = None,
) -> tuple[int, bytes, bytes]:
    t = timeout_sec if timeout_sec is not None else _cmd_timeout_sec()
    try:
        p = subprocess.run(
            cmd,
            input=stdin_bytes if stdin_bytes else None,
            capture_output=True,
            cwd=cwd,
            timeout=t,
        )
        return p.returncode, p.stdout or b"", p.stderr or b""
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or b""
        err = (exc.stderr or b"") + b"\n[sandbox] command timed out\n"
        return _TIMEOUT_EXIT, out, err


def _truncate(data: bytes, limit: int) -> bytes:
    if len(data) <= limit:
        return data
    return data[:limit] + b"\n[truncated]"


def run_python(code: str, stdin_text: str, out_limit: int) -> dict:
    path = Path("/tmp/sandbox_main.py")
    path.write_text(code, encoding="utf-8")
    code_ret, out, err = _run_cmd(
        ["python3", "-I", str(path)],
        stdin_text.encode("utf-8"),
    )
    return {
        "exit_code": int(code_ret),
        "stdout": _truncate(out, out_limit).decode("utf-8", errors="replace"),
        "stderr": _truncate(err, out_limit).decode("utf-8", errors="replace"),
    }


def run_typescript(code: str, stdin_text: str, out_limit: int) -> dict:
    path = Path("/tmp/sandbox_main.ts")
    path.write_text(code, encoding="utf-8")
    code_ret, out, err = _run_cmd(
        ["tsx", str(path)],
        stdin_text.encode("utf-8"),
    )
    return {
        "exit_code": int(code_ret),
        "stdout": _truncate(out, out_limit).decode("utf-8", errors="replace"),
        "stderr": _truncate(err, out_limit).decode("utf-8", errors="replace"),
    }


def run_java(code: str, stdin_text: str, out_limit: int) -> dict:
    src = Path("/tmp/Main.java")
    src.write_text(code, encoding="utf-8")
    cr, cout, cerr = _run_cmd(["javac", str(src)], b"", cwd="/tmp")
    if cr != 0:
        return {
            "exit_code": cr,
            "stdout": _truncate(cout, out_limit).decode("utf-8", errors="replace"),
            "stderr": _truncate(cerr, out_limit).decode("utf-8", errors="replace"),
        }
    code_ret, out, err = _run_cmd(
        ["java", "-cp", "/tmp", "Main"],
        stdin_text.encode("utf-8"),
        cwd="/tmp",
    )
    return {
        "exit_code": int(code_ret),
        "stdout": _truncate(out, out_limit).decode("utf-8", errors="replace"),
        "stderr": _truncate(err, out_limit).decode("utf-8", errors="replace"),
    }


def main() -> None:
    out_limit = int(os.environ.get("SANDBOX_OUTPUT_LIMIT", "65536"))
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        print(
            json.dumps({"error": f"invalid stdin json: {e}", "exit_code": None}),
            flush=True,
        )
        sys.exit(0)

    lang = payload.get("language")
    code = payload.get("code") or ""
    stdin_text = payload.get("stdin") or ""

    try:
        t0 = time.perf_counter()
        if lang == "python":
            result = run_python(code, stdin_text, out_limit)
        elif lang == "typescript":
            result = run_typescript(code, stdin_text, out_limit)
        elif lang == "java":
            result = run_java(code, stdin_text, out_limit)
        else:
            result = {
                "error": f"unsupported language: {lang}",
                "exit_code": None,
                "stdout": "",
                "stderr": "",
            }
        result["duration_ms"] = int((time.perf_counter() - t0) * 1000)
        result.setdefault("error", None)
        print(json.dumps(result), flush=True)
    except Exception as e:
        print(
            json.dumps(
                {
                    "error": str(e),
                    "exit_code": None,
                    "stdout": "",
                    "stderr": "",
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
