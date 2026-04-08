import ast

from tree_sitter_language_pack import get_parser

from app.models import Language, SyntaxErrorItem, SyntaxResult


def _first_error_line(node) -> tuple[int, int] | None:
    if node.type == "ERROR" or getattr(node, "is_missing", False):
        row, col = node.start_point
        return row + 1, col + 1
    for child in node.children:
        found = _first_error_line(child)
        if found:
            return found
    return None


def _tree_sitter_check(code: str, lang_key: str) -> SyntaxResult:
    try:
        parser = get_parser(lang_key)
    except Exception as e:
        return SyntaxResult(
            valid=False,
            errors=[
                SyntaxErrorItem(
                    message=(
                        f"Syntax checker unavailable for this language (parser failed to load: {e})"
                    )
                )
            ],
        )
    tree = parser.parse(code.encode("utf-8"))
    if tree.root_node.has_error:
        pos = _first_error_line(tree.root_node)
        if pos:
            line, col = pos
            return SyntaxResult(
                valid=False,
                errors=[
                    SyntaxErrorItem(
                        line=line,
                        column=col,
                        message="Parse error: invalid syntax for this language",
                    )
                ],
            )
        return SyntaxResult(
            valid=False,
            errors=[
                SyntaxErrorItem(
                    message="Parse error: invalid syntax for this language"
                )
            ],
        )
    return SyntaxResult(valid=True, errors=[])


def check_syntax(language: Language, code: str) -> SyntaxResult:
    if language == Language.python:
        try:
            ast.parse(code)
        except SyntaxError as e:
            return SyntaxResult(
                valid=False,
                errors=[
                    SyntaxErrorItem(
                        line=e.lineno,
                        column=e.offset,
                        message=e.msg or "Syntax error",
                    )
                ],
            )
        return SyntaxResult(valid=True, errors=[])

    if language == Language.typescript:
        return _tree_sitter_check(code, "typescript")

    if language == Language.java:
        return _tree_sitter_check(code, "java")

    return SyntaxResult(valid=True, errors=[])
