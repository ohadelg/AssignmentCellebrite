from eval.align import align_case, aggregate_tag_metrics, tag_matches_finding


def test_tag_matches_finding_substring():
    tag = {
        "category": "security",
        "tag_id": "sqli",
        "signals": ["sql injection", "parameterized"],
    }
    finding = {
        "category": "security",
        "title": "SQL injection risk",
        "detail": "Use parameterized queries instead of string concatenation.",
        "suggestion": "Use placeholders with bound parameters.",
    }
    assert tag_matches_finding(tag, finding)


def test_tag_wrong_category():
    tag = {"category": "security", "tag_id": "x", "signals": ["sql"]}
    finding = {
        "category": "style",
        "title": "SQL style",
        "detail": "sql",
        "suggestion": "sql",
    }
    assert not tag_matches_finding(tag, finding)


def test_align_first_fit_one_finding_two_tags():
    gt = [
        {"category": "security", "tag_id": "a", "signals": ["injection"]},
        {"category": "security", "tag_id": "b", "signals": ["injection"]},
    ]
    findings = [
        {
            "category": "security",
            "title": "Injection",
            "detail": "injection issue",
            "suggestion": "fix injection",
        }
    ]
    a = align_case("c1", gt, findings)
    assert len(a.matches) == 1
    assert len(a.misses) == 1
    assert len(a.extras) == 0


def test_align_extra_finding():
    gt = [{"category": "security", "tag_id": "sqli", "signals": ["parameterized"]}]
    findings = [
        {
            "category": "style",
            "title": "Types",
            "detail": "Add type hints",
            "suggestion": "Annotate parameters",
        }
    ]
    a = align_case("c2", gt, findings)
    assert len(a.matches) == 0
    assert len(a.misses) == 1
    assert len(a.extras) == 1


def test_aggregate_metrics():
    from eval.align import CaseAlignment

    c1 = CaseAlignment(
        case_id="1",
        matches=[{"x": 1}],
        misses=[{"y": 1}],
        extras=[{"z": 1}],
    )
    c2 = CaseAlignment(
        case_id="2",
        matches=[{"x": 1}, {"x": 2}],
        misses=[],
        extras=[],
    )
    m = aggregate_tag_metrics([c1, c2])
    assert m["tp"] == 3.0
    assert m["fn"] == 1.0
    assert m["fp"] == 1.0
