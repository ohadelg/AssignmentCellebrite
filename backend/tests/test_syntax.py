from app.models import Language
from app.syntax_check import check_syntax


def test_python_syntax_valid():
    r = check_syntax(Language.python, "x = 1\n")
    assert r.valid is True
    assert r.errors == []


def test_python_syntax_invalid():
    r = check_syntax(Language.python, "def bad(\n")
    assert r.valid is False
    assert r.errors
    assert r.errors[0].line is not None
