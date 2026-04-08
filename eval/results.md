# Eval results (append-only)

Each `eval/orchestrate.py --loop` or `eval/summarize.py` run appends a section below with metrics, per-case match/miss/extra counts, and judge highlights. Dataset expansions (+5 rows) are noted when `--loop` completes.

---
## Run `20260408T125101Z`

- **When**: 2026-04-08 13:00 UTC
- **Model**: `gemini-2.5-flash`
- **Git**: `8c20fb3`
- **Dataset rows**: 20 (evaluated cases this run: 20)

### Aggregate (tag-level)

- TP (matches): 19, FP (extras): 43, FN (misses): 8
- Precision: 0.306, Recall: 0.704, F1: 0.427

### Judge rollup

- Extras judged legitimate: 42 / 43
- Misses judged unfair (should have caught): 6 / 8

### Per case

| case | match | miss | extra |
| --- | ---: | ---: | ---: |
| py_sqli_concat | 1 | 2 | 2 |
| py_cmd_injection | 2 | 0 | 2 |
| py_path_traversal | 0 | 1 | 4 |
| py_hardcoded_secret | 1 | 1 | 1 |
| py_weak_random | 1 | 0 | 1 |
| py_pickle | 1 | 0 | 1 |
| py_eval | 1 | 0 | 2 |
| py_ssrf | 0 | 1 | 5 |
| py_logic_off_by_one | 0 | 1 | 1 |
| py_div_zero | 1 | 0 | 2 |
| py_style_no_hints | 1 | 0 | 1 |
| py_perf_string_concat | 1 | 0 | 3 |
| py_open_no_ctx | 1 | 1 | 2 |
| py_none_deref | 1 | 0 | 0 |
| ts_xss_innerhtml | 1 | 0 | 1 |
| ts_fetch_no_validate | 1 | 1 | 2 |
| java_sqli | 1 | 0 | 3 |
| java_runtime_exec | 1 | 0 | 4 |
| java_weak_hash | 1 | 0 | 4 |
| py_race_temp_file | 2 | 0 | 2 |

### Highlights (from judge deltas)

- Consider adding a finding for undeclared variables or implicit global dependencies, especially for critical resources like database cursors, as it impacts modularity and testability.
- Ensure findings include common error handling omissions for I/O or external resource operations, such as database calls, as unhandled exceptions can lead to crashes.
- Include findings for unnecessary `shell=True` usage in `subprocess` calls, as it can introduce overhead and is often a sign of a potential security risk (even if not directly exploited in the current context).
- Ensure findings cover missing docstrings and complete type hinting (including return types) for functions, as these are crucial for code readability, maintainability, and static analysis.
- Confirm that findings for path traversal vulnerabilities correctly identify the need for explicit checks (e.g., `resolve()` and `is_relative_to()`) even when using `pathlib`, as simple concatenation does not guarantee safety.
- Include findings for missing error handling around file I/O operations, as unhandled exceptions can lead to crashes or poor user experience.
- Ensure findings consistently identify missing docstrings for functions, as they are a fundamental aspect of good code documentation.
- Add findings for missing explicit encoding specifications in file I/O operations (e.g., `read_text()`), as relying on system defaults can cause portability and correctness issues.
- Consider including findings for stylistic improvements like preferring f-strings over `+` for string concatenation, especially in modern Python code, as it enhances readability.
- Ensure findings for weak random number generation or insecure token generation clearly highlight the inadequacy of the generated token's length and character space, emphasizing the security implications.
- The finding discusses a scenario involving `json` and `UnicodeDecodeError` when decoding bytes to a string. However, the provided code only uses `pickle.loads` which operates directly on bytes and does not involve `json` or explicit string decoding. Please ensure findings are directly relevant to the provided code.
- Add type hints to function parameters and return values.
- Add a docstring to explain the function's purpose, arguments, and return value.
- Consider if `cursor.fetchone()` or `cursor.fetchmany()` would be more appropriate if only a single row or a limited number of rows are expected, to optimize memory and performance.
- Sanitize the `name` input to prevent path traversal attacks, for example, by resolving the final path to its canonical form and ensuring it remains within the intended base directory, or by strictly validating the `name` to only allow safe characters and no path separators.
- Move sensitive constants like API keys to environment variables or a secure configuration management system instead of hardcoding them directly in the source code.
- Implement strict URL validation and an allowlist to prevent Server-Side Request Forgery (SSRF) attacks. Only allow requests to trusted domains or specific internal resources, and ensure no sensitive internal IP addresses or services can be accessed.
- Consider using the more Pythonic and concise slice `items[:-1]` to achieve the same result of slicing all but the last element, which is less prone to off-by-one errors than explicit length calculations.
- Use a `with` statement when opening files to ensure they are automatically closed, even if exceptions occur, preventing resource leaks. For example: `with open(path) as f:`
- Implement strict URL validation and an allowlist for the `url` parameter to prevent Server-Side Request Forgery (SSRF) or Open Redirect vulnerabilities. Only allow requests to trusted domains or specific internal resources.

