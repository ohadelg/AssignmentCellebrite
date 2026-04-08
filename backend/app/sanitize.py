from app.config import Settings


def strip_control_chars(text: str) -> str:
    # Allow tab, newline, carriage return; strip other C0 controls and DEL
    return "".join(
        ch for ch in text if ch in "\t\n\r" or (ord(ch) >= 32 and ord(ch) != 127)
    )


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def sanitize_code(code: str, settings: Settings) -> str:
    code = normalize_newlines(code)
    code = strip_control_chars(code)
    if len(code.encode("utf-8")) > settings.max_code_bytes:
        raise ValueError("Code exceeds maximum allowed size")
    if not code.strip():
        raise ValueError("Code cannot be empty")
    return code


def sanitize_stdin(stdin: str, settings: Settings) -> str:
    stdin = normalize_newlines(stdin)
    stdin = strip_control_chars(stdin)
    if len(stdin.encode("utf-8")) > settings.max_stdin_bytes:
        raise ValueError("Stdin exceeds maximum allowed size")
    return stdin


def truncate_output(data: bytes, max_bytes: int) -> tuple[str, bool]:
    truncated = len(data) > max_bytes
    raw = data[:max_bytes] if truncated else data
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        text = raw.decode("utf-8", errors="replace")
    if truncated:
        text += "\n[output truncated]"
    return text, truncated
