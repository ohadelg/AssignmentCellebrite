import pytest

from app.config import Settings
from app.sanitize import normalize_newlines, sanitize_code, strip_control_chars, truncate_output


def test_strip_control_chars_keeps_newline_tab():
    assert strip_control_chars("a\n\tb") == "a\n\tb"


def test_strip_control_chars_removes_nul():
    assert strip_control_chars("a\x00b") == "ab"


def test_normalize_newlines():
    assert normalize_newlines("a\r\nb\rc") == "a\nb\nc"


def test_sanitize_code_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        sanitize_code("   \n", Settings())


def test_sanitize_code_ok():
    s = Settings()
    assert sanitize_code("print(1)", s) == "print(1)"


def test_truncate_output():
    text, trunc = truncate_output(b"x" * 100, 50)
    assert trunc is True
    assert len(text.encode("utf-8")) <= 50 + len("\n[output truncated]")
