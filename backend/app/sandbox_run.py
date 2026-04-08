from __future__ import annotations

import json
import logging
import os
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from app.config import Settings
from app.models import Language
from app.sanitize import truncate_output

logger = logging.getLogger(__name__)


def _subprocess_env_sanitized(*, extra: dict[str, str] | None = None) -> dict[str, str]:
    """Child env from os.environ; drop npm devdir keys so `npx` does not warn on stderr."""
    env = dict(os.environ)
    env.pop("npm_config_devdir", None)
    env.pop("NPM_CONFIG_DEVDIR", None)
    if extra:
        env.update(extra)
    return env


JAVA_HOST_SETUP_HINT = (
    "No working JDK found for the Java sandbox. Install a JDK (e.g. Eclipse Temurin 17 from "
    "https://adoptium.net), or set JAVA_HOME in your environment / `.env` to the JDK root "
    "(the folder that contains `bin/javac`). The API also searches common Homebrew and "
    "/Library/Java paths on macOS. Alternatively use Docker: `docker compose build sandbox` "
    "with Docker Desktop running."
)

# Cache docker daemon probe (seconds)
_DOCKER_READY_CACHE: tuple[float, bool] | None = None
_DOCKER_READY_TTL_SEC = 5.0


def _docker_cli_installed() -> bool:
    return shutil.which("docker") is not None


def _docker_daemon_ready() -> bool:
    """True only if the Docker daemon accepts commands (avoids failed docker run when Desktop is off)."""
    global _DOCKER_READY_CACHE
    now = time.monotonic()
    if _DOCKER_READY_CACHE is not None:
        ts, ok = _DOCKER_READY_CACHE
        if now - ts < _DOCKER_READY_TTL_SEC:
            return ok
    ok = False
    try:
        r = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5,
        )
        ok = r.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.debug("docker info probe failed: %s", e)
        ok = False
    _DOCKER_READY_CACHE = (now, ok)
    return ok


def _invalidate_docker_ready_cache() -> None:
    global _DOCKER_READY_CACHE
    _DOCKER_READY_CACHE = None


def run_in_docker(
    *,
    settings: Settings,
    language: Language,
    code: str,
    stdin: str,
) -> dict:
    payload = {
        "language": language.value,
        "code": code,
        "stdin": stdin,
    }
    mem = max(64, settings.sandbox_memory_mb)
    inner_timeout = max(1, settings.sandbox_timeout_sec - 1)
    cmd = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--network",
        "none",
        "-m",
        f"{mem}m",
        "--cpus",
        str(settings.sandbox_cpus),
        "--read-only",
        "--tmpfs",
        "/tmp:rw,nosuid,size=128m",
        "-e",
        f"SANDBOX_OUTPUT_LIMIT={settings.max_output_bytes}",
        "-e",
        f"SANDBOX_CMD_TIMEOUT_SEC={inner_timeout}",
        settings.sandbox_image,
    ]
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            input=json.dumps(payload).encode("utf-8"),
            capture_output=True,
            timeout=settings.sandbox_timeout_sec + 5,
        )
    except subprocess.TimeoutExpired:
        return {
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "timed_out": True,
            "duration_ms": int((time.perf_counter() - t0) * 1000),
            "error": "Sandbox execution timed out",
        }
    duration_ms = int((time.perf_counter() - t0) * 1000)
    raw_out = proc.stdout.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        err_txt = proc.stderr.decode("utf-8", errors="replace")
        if _docker_image_or_infra_error(err_txt):
            _invalidate_docker_ready_cache()
        logger.warning("docker run failed rc=%s stderr=%s", proc.returncode, err_txt[:500])
        return {
            "exit_code": None,
            "stdout": "",
            "stderr": err_txt[: settings.max_output_bytes],
            "timed_out": False,
            "duration_ms": duration_ms,
            "error": "Sandbox failed to start or returned an error",
        }
    try:
        data = json.loads(raw_out)
    except json.JSONDecodeError:
        return {
            "exit_code": None,
            "stdout": raw_out[: settings.max_output_bytes],
            "stderr": "",
            "timed_out": False,
            "duration_ms": duration_ms,
            "error": "Invalid sandbox output",
        }
    return {
        "exit_code": data.get("exit_code"),
        "stdout": data.get("stdout") or "",
        "stderr": data.get("stderr") or "",
        "timed_out": False,
        "duration_ms": data.get("duration_ms") or duration_ms,
        "error": data.get("error"),
    }


def _set_memory_limit(mb: int) -> None:
    if sys.platform == "win32":
        return
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        limit = mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, min(hard, limit) if hard > 0 else limit))
    except (ValueError, OSError):
        pass


def run_python_host_fallback(
    *,
    settings: Settings,
    code: str,
    stdin: str,
) -> dict:
    t0 = time.perf_counter()
    try:
        if sys.platform != "win32":
            _set_memory_limit(min(settings.sandbox_memory_mb, 256))
        proc = subprocess.run(
            [sys.executable, "-I", "-c", code],
            input=stdin.encode("utf-8"),
            capture_output=True,
            timeout=settings.sandbox_timeout_sec,
        )
        duration_ms = int((time.perf_counter() - t0) * 1000)
        out, _ = truncate_output(proc.stdout, settings.max_output_bytes)
        err, _ = truncate_output(proc.stderr, settings.max_output_bytes)
        return {
            "exit_code": proc.returncode,
            "stdout": out,
            "stderr": err,
            "timed_out": False,
            "duration_ms": duration_ms,
            "error": None,
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "timed_out": True,
            "duration_ms": int((time.perf_counter() - t0) * 1000),
            "error": "Execution timed out (host fallback)",
        }
    except Exception as e:
        logger.warning("host fallback failed: %s", e)
        return {
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "timed_out": False,
            "duration_ms": int((time.perf_counter() - t0) * 1000),
            "error": "Host execution failed",
        }


def run_typescript_host_fallback(
    *,
    settings: Settings,
    code: str,
    stdin: str,
) -> dict:
    t0 = time.perf_counter()
    path: str | None = None
    try:
        fd, path = tempfile.mkstemp(suffix=".ts", text=True)
        os.close(fd)
        Path(path).write_text(code, encoding="utf-8")
        tsx = shutil.which("tsx")
        if tsx:
            cmd = [tsx, path]
        else:
            cmd = ["npx", "--yes", "tsx@4", path]
        proc = subprocess.run(
            cmd,
            input=stdin.encode("utf-8") if stdin else None,
            capture_output=True,
            timeout=settings.sandbox_timeout_sec,
            env=_subprocess_env_sanitized(extra={"npm_config_yes": "true"}),
        )
        duration_ms = int((time.perf_counter() - t0) * 1000)
        out, _ = truncate_output(proc.stdout, settings.max_output_bytes)
        err, _ = truncate_output(proc.stderr, settings.max_output_bytes)
        return {
            "exit_code": proc.returncode,
            "stdout": out,
            "stderr": err,
            "timed_out": False,
            "duration_ms": duration_ms,
            "error": None,
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "timed_out": True,
            "duration_ms": int((time.perf_counter() - t0) * 1000),
            "error": "Execution timed out (TypeScript host fallback)",
        }
    except FileNotFoundError:
        return {
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "timed_out": False,
            "duration_ms": int((time.perf_counter() - t0) * 1000),
            "error": "TypeScript host fallback needs `tsx` on PATH or `npx` to run tsx",
        }
    except Exception as e:
        logger.warning("ts host fallback failed: %s", e)
        return {
            "exit_code": None,
            "stdout": "",
            "stderr": str(e)[: settings.max_output_bytes],
            "timed_out": False,
            "duration_ms": int((time.perf_counter() - t0) * 1000),
            "error": "TypeScript host execution failed",
        }
    finally:
        if path and os.path.isfile(path):
            try:
                os.unlink(path)
            except OSError:
                pass


def _macos_java_stub_output(text: str) -> bool:
    low = text.lower()
    return (
        "unable to locate a java runtime" in low
        or "java.com" in low
        or "no java runtime present" in low
    )


def _normalize_java_home(raw: str) -> str:
    s = (raw or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        s = s[1:-1].strip()
    return s


def _canonical_jdk_home(home: str) -> str:
    """Resolve ~ and symlinks so two paths to the same JDK compare equal."""
    if not (home or "").strip():
        return ""
    return os.path.realpath(os.path.expanduser(home.strip()))


def _jdk_home_layout_ok(home: str) -> bool:
    """True if `home` is a JDK layout: bin/javac and bin/java exist (symlinks OK).

    Do not use os.access(X_OK) here: on macOS it often returns False for real JDK binaries
    inside .jdk bundles even though subprocess can execute them.
    """
    canon = _canonical_jdk_home(home)
    if not canon or not os.path.isdir(canon):
        return False
    bin_dir = os.path.join(canon, "bin")
    if not os.path.isdir(bin_dir):
        return False
    for name in ("javac", "java"):
        p = os.path.join(bin_dir, name)
        if not os.path.exists(p) or os.path.isdir(p):
            return False
    return True


def _discover_macos_java_home() -> str | None:
    """Use Apple's helper so Temurin/Homebrew JDKs are found even when PATH is minimal."""
    if sys.platform != "darwin":
        return None
    helper = "/usr/libexec/java_home"
    if not os.path.isfile(helper):
        return None
    attempts: list[list[str]] = [
        [],
        ["-v", "21"],
        ["-v", "21+"],
        ["-v", "17"],
        ["-v", "17+"],
        ["-v", "11"],
        ["-v", "1.8+"],
    ]
    for extra in attempts:
        try:
            r = subprocess.run(
                [helper, *extra],
                capture_output=True,
                text=True,
                timeout=8,
            )
            if r.returncode != 0:
                continue
            line = (r.stdout or "").strip().split("\n")[0].strip()
            if line and _jdk_home_layout_ok(line):
                return _canonical_jdk_home(line)
        except (OSError, subprocess.TimeoutExpired):
            continue
    return None


def configure_java_environment(*, java_home_from_settings: str = "") -> None:
    """Apply JAVA_HOME from settings, macOS java_home, or drop invalid values so discovery can run."""
    setting = _normalize_java_home(java_home_from_settings)

    if setting and _jdk_home_layout_ok(setting):
        canon = _canonical_jdk_home(setting)
        os.environ["JAVA_HOME"] = canon
        logger.info("sandbox: JAVA_HOME=%s (from configuration)", canon)
        return

    if setting and not _jdk_home_layout_ok(setting):
        logger.warning(
            "sandbox: JAVA_HOME from .env/settings is not a JDK root (missing bin/javac or bin/java): %s",
            setting,
        )
        if _canonical_jdk_home(os.environ.get("JAVA_HOME", "")) == _canonical_jdk_home(setting):
            os.environ.pop("JAVA_HOME", None)

    existing = _normalize_java_home(os.environ.get("JAVA_HOME", ""))
    if existing and _jdk_home_layout_ok(existing):
        os.environ["JAVA_HOME"] = _canonical_jdk_home(existing)
        return

    if existing and not _jdk_home_layout_ok(existing):
        logger.warning("sandbox: removing invalid JAVA_HOME from environment: %s", existing)
        os.environ.pop("JAVA_HOME", None)

    jh = _discover_macos_java_home()
    if jh and _jdk_home_layout_ok(jh):
        os.environ["JAVA_HOME"] = _canonical_jdk_home(jh)
        logger.info("sandbox: JAVA_HOME set via /usr/libexec/java_home -> %s", os.environ["JAVA_HOME"])


def _find_executable_on_path(name: str, path_var: str) -> str | None:
    """Resolve `name` on PATH; on macOS skip /usr/bin so we avoid the Java install stub."""
    for part in path_var.split(os.pathsep):
        if not part:
            continue
        if sys.platform == "darwin" and os.path.normpath(part) == "/usr/bin":
            continue
        candidate = os.path.join(part, name)
        # Avoid os.access(X_OK): unreliable for JDK symlinks on macOS; subprocess probes below.
        if os.path.exists(candidate) and not os.path.isdir(candidate):
            return candidate
    return None


def _java_bin_dir_candidates() -> list[str]:
    """Extra bin dirs so host Java works when uvicorn inherits a minimal PATH (IDE, launchd)."""
    out: list[str] = []
    jh_env = _normalize_java_home(os.environ.get("JAVA_HOME", ""))
    if jh_env and _jdk_home_layout_ok(jh_env):
        out.append(os.path.join(_canonical_jdk_home(jh_env), "bin"))
    jh_mac = _discover_macos_java_home()
    if jh_mac:
        jb = os.path.join(jh_mac, "bin")
        if os.path.isdir(jb) and jb not in out:
            out.append(jb)
    if sys.platform == "darwin":
        jv = Path("/Library/Java/JavaVirtualMachines")
        if jv.is_dir():
            for home in sorted(jv.glob("*/Contents/Home/bin")):
                if home.is_dir():
                    out.append(str(home))
        for suffix in ("@21", "@17", "@11", ""):
            for root in (f"/opt/homebrew/opt/openjdk{suffix}", f"/usr/local/opt/openjdk{suffix}"):
                b = os.path.join(root, "bin")
                if os.path.isdir(b):
                    out.append(b)
    if sys.platform.startswith("linux"):
        jvm = Path("/usr/lib/jvm")
        if jvm.is_dir():
            for b in sorted(jvm.glob("*/bin")):
                if b.is_dir() and (b / "javac").is_file():
                    out.append(str(b))
    seen: set[str] = set()
    uniq: list[str] = []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def _java_exec_env() -> dict[str, str]:
    merged = {k: v for k, v in os.environ.items() if v is not None}
    prepend = _java_bin_dir_candidates()
    tail = merged.get("PATH", "")
    parts = prepend + ([tail] if tail else [])
    merged["PATH"] = os.pathsep.join(parts)
    return merged


def _jdk_host_usable() -> bool:
    """True if a real JDK is available (extends PATH like a login shell / IDE often does not)."""
    jh = _normalize_java_home(os.environ.get("JAVA_HOME", ""))
    if _jdk_home_layout_ok(jh):
        canon = _canonical_jdk_home(jh)
        javac = os.path.join(canon, "bin", "javac")
        java = os.path.join(canon, "bin", "java")
    else:
        env = _java_exec_env()
        path = env.get("PATH", "")
        javac = _find_executable_on_path("javac", path)
        java = _find_executable_on_path("java", path)
    if not javac or not java:
        return False
    env = _java_exec_env()
    try:
        rj = subprocess.run(
            [javac, "-version"],
            capture_output=True,
            timeout=8,
            text=True,
            env=env,
        )
        out_j = (rj.stderr or "") + (rj.stdout or "")
        if _macos_java_stub_output(out_j):
            return False
        if rj.returncode != 0:
            return False
        rjv = subprocess.run(
            [java, "-version"],
            capture_output=True,
            timeout=8,
            text=True,
            env=env,
        )
        out_v = (rjv.stderr or "") + (rjv.stdout or "")
        if _macos_java_stub_output(out_v):
            return False
        if rjv.returncode != 0 and "version" not in out_v.lower():
            return False
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


def run_java_host_fallback(
    *,
    settings: Settings,
    code: str,
    stdin: str,
) -> dict:
    if not _jdk_host_usable():
        hint = JAVA_HOST_SETUP_HINT
        sj = _normalize_java_home(settings.java_home)
        if sj and not _jdk_home_layout_ok(sj):
            hint = (
                f"JAVA_HOME in .env is set to {sj!r}, but that path has no JDK layout "
                "(need bin/javac and bin/java — install a **JDK**, not a JRE-only runtime). "
                "On macOS run `ls /Library/Java/JavaVirtualMachines` and "
                "`/usr/libexec/java_home -v 17`, set JAVA_HOME to that path, or remove JAVA_HOME for auto-discovery."
            )
        elif sj and _jdk_home_layout_ok(sj):
            hint = (
                f"JAVA_HOME is {sj!r}; bin/javac and bin/java exist but did not run successfully from the API "
                "(PATH stub, broken JDK, or sandbox restrictions). In Terminal, run: "
                f"export JAVA_HOME={sj!r} && \"$JAVA_HOME/bin/javac\" -version && \"$JAVA_HOME/bin/java\" -version"
            )
        return {
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "timed_out": False,
            "duration_ms": 0,
            "error": hint,
        }

    t0 = time.perf_counter()
    jenv = _java_exec_env()
    jh = _normalize_java_home(os.environ.get("JAVA_HOME", ""))
    javac_cmd = "javac"
    java_cmd = "java"
    if _jdk_home_layout_ok(jh):
        canon = _canonical_jdk_home(jh)
        javac_cmd = os.path.join(canon, "bin", "javac")
        java_cmd = os.path.join(canon, "bin", "java")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "Main.java"
            src.write_text(code, encoding="utf-8")
            jc = subprocess.run(
                [javac_cmd, str(src)],
                capture_output=True,
                timeout=settings.sandbox_timeout_sec,
                cwd=tmp,
                env=jenv,
            )
            cerr = (jc.stderr or b"").decode("utf-8", errors="replace")
            if jc.returncode != 0:
                duration_ms = int((time.perf_counter() - t0) * 1000)
                if _macos_java_stub_output(cerr):
                    return {
                        "exit_code": None,
                        "stdout": "",
                        "stderr": "",
                        "timed_out": False,
                        "duration_ms": duration_ms,
                        "error": JAVA_HOST_SETUP_HINT,
                    }
                return {
                    "exit_code": jc.returncode,
                    "stdout": (jc.stdout or b"").decode("utf-8", errors="replace")[
                        : settings.max_output_bytes
                    ],
                    "stderr": cerr[: settings.max_output_bytes],
                    "timed_out": False,
                    "duration_ms": duration_ms,
                    "error": None,
                }
            proc = subprocess.run(
                [java_cmd, "-cp", tmp, "Main"],
                input=stdin.encode("utf-8") if stdin else None,
                capture_output=True,
                timeout=settings.sandbox_timeout_sec,
                cwd=tmp,
                env=jenv,
            )
            duration_ms = int((time.perf_counter() - t0) * 1000)
            out, _ = truncate_output(proc.stdout, settings.max_output_bytes)
            err, _ = truncate_output(proc.stderr, settings.max_output_bytes)
            if _macos_java_stub_output(err):
                return {
                    "exit_code": None,
                    "stdout": "",
                    "stderr": "",
                    "timed_out": False,
                    "duration_ms": duration_ms,
                    "error": JAVA_HOST_SETUP_HINT,
                }
            return {
                "exit_code": proc.returncode,
                "stdout": out,
                "stderr": err,
                "timed_out": False,
                "duration_ms": duration_ms,
                "error": None,
            }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "timed_out": True,
            "duration_ms": int((time.perf_counter() - t0) * 1000),
            "error": "Execution timed out (Java host fallback)",
        }
    except FileNotFoundError:
        return {
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "timed_out": False,
            "duration_ms": int((time.perf_counter() - t0) * 1000),
            "error": JAVA_HOST_SETUP_HINT,
        }
    except Exception as e:
        logger.warning("java host fallback failed: %s", e)
        return {
            "exit_code": None,
            "stdout": "",
            "stderr": str(e)[: settings.max_output_bytes],
            "timed_out": False,
            "duration_ms": int((time.perf_counter() - t0) * 1000),
            "error": "Java host execution failed",
        }


def _docker_image_or_infra_error(stderr: str) -> bool:
    s = stderr.lower()
    return (
        "cannot connect to the docker daemon" in s
        or "docker daemon is not running" in s
        or "is the docker daemon running" in s
        or "docker.sock" in s
        or "connection refused" in s
        or "unable to find image" in s
        or "could not find image" in s
        or "no such image" in s
        or "pull access denied" in s
        or "denied: requested access" in s
        or "error response from daemon" in s
    )


def _should_use_host_after_docker_failure(result: dict) -> bool:
    """If docker run failed for infra reasons, retry on the host (all languages)."""
    if result.get("timed_out") or result.get("error") == "Sandbox execution timed out":
        return False
    stderr = result.get("stderr") or ""
    if _docker_image_or_infra_error(stderr):
        return True
    if result.get("error") == "Invalid sandbox output":
        return True
    return False


def _run_host_fallback(
    *,
    settings: Settings,
    language: Language,
    code: str,
    stdin: str,
) -> dict:
    if language == Language.python:
        return run_python_host_fallback(settings=settings, code=code, stdin=stdin)
    if language == Language.typescript:
        return run_typescript_host_fallback(settings=settings, code=code, stdin=stdin)
    if language == Language.java:
        return run_java_host_fallback(settings=settings, code=code, stdin=stdin)
    return {
        "exit_code": None,
        "stdout": "",
        "stderr": "",
        "timed_out": False,
        "duration_ms": 0,
        "error": "Unsupported language",
    }


def execute_sandboxed(
    *,
    settings: Settings,
    language: Language,
    code: str,
    stdin: str,
) -> dict:
    if not settings.sandbox_enabled:
        return {
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "timed_out": False,
            "duration_ms": 0,
            "error": "Sandbox is disabled",
        }

    use_docker = _docker_cli_installed() and _docker_daemon_ready()

    if use_docker:
        result = run_in_docker(
            settings=settings,
            language=language,
            code=code,
            stdin=stdin,
        )
        if _should_use_host_after_docker_failure(result):
            logger.info(
                "sandbox: host fallback after Docker failure (%s)",
                language.value,
            )
            return _run_host_fallback(
                settings=settings,
                language=language,
                code=code,
                stdin=stdin,
            )
        return result

    # No working Docker daemon (or CLI missing): run on host for all supported languages
    logger.info("sandbox: using host fallback (Docker not available or daemon not running)")
    return _run_host_fallback(settings=settings, language=language, code=code, stdin=stdin)
