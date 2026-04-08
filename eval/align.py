"""Deterministic match / miss / extra alignment between ground-truth tags and agent findings."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

CATEGORIES = frozenset({"security", "performance", "logic", "style"})


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def finding_text(f: dict[str, Any]) -> str:
    parts = [
        str(f.get("title", "")),
        str(f.get("detail", "")),
        str(f.get("suggestion", "")),
    ]
    return _normalize_ws(" ".join(parts))


def tag_matches_finding(tag: dict[str, Any], finding: dict[str, Any]) -> bool:
    if finding.get("category") != tag.get("category"):
        return False
    blob = finding_text(finding)
    signals = tag.get("signals") or []
    if not isinstance(signals, list):
        return False
    for s in signals:
        if not isinstance(s, str) or not s.strip():
            continue
        if _normalize_ws(s) in blob or s.lower() in blob:
            return True
    return False


@dataclass
class CaseAlignment:
    case_id: str
    matches: list[dict[str, Any]] = field(default_factory=list)
    misses: list[dict[str, Any]] = field(default_factory=list)
    extras: list[dict[str, Any]] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "match": len(self.matches),
            "miss": len(self.misses),
            "extra": len(self.extras),
        }


def align_case(
    case_id: str,
    ground_truth: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> CaseAlignment:
    """First-fit: each finding consumed by at most one GT tag (order of GT tags)."""
    used_finding_idx: set[int] = set()
    out = CaseAlignment(case_id=case_id)

    for tag in ground_truth:
        tid = tag.get("tag_id", "")
        cat = tag.get("category")
        if cat not in CATEGORIES:
            out.misses.append({**tag, "_reason": "invalid_gt_category"})
            continue
        matched_idx: int | None = None
        for i, f in enumerate(findings):
            if i in used_finding_idx:
                continue
            if tag_matches_finding(tag, f):
                matched_idx = i
                break
        if matched_idx is not None:
            used_finding_idx.add(matched_idx)
            out.matches.append(
                {
                    "tag_id": tid,
                    "category": cat,
                    "finding_index": matched_idx,
                    "finding": findings[matched_idx],
                }
            )
        else:
            out.misses.append(dict(tag))

    for i, f in enumerate(findings):
        if i not in used_finding_idx:
            out.extras.append({"finding_index": i, "finding": f})

    return out


def aggregate_tag_metrics(cases: list[CaseAlignment]) -> dict[str, float]:
    tp = sum(len(c.matches) for c in cases)
    fn = sum(len(c.misses) for c in cases)
    fp = sum(len(c.extras) for c in cases)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "tp": float(tp),
        "fp": float(fp),
        "fn": float(fn),
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def build_summary(
    run_id: str,
    model: str,
    cases_payload: list[dict[str, Any]],
    case_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """cases_payload: dataset rows; case_results: per-case agent output + optional error."""
    alignments: list[CaseAlignment] = []
    for row, res in zip(cases_payload, case_results, strict=True):
        cid = row["id"]
        gt = row.get("ground_truth") or []
        if res.get("error"):
            alignments.append(
                CaseAlignment(
                    case_id=cid,
                    misses=list(gt),
                    extras=[],
                )
            )
            continue
        review = res.get("review") or {}
        findings = review.get("findings") or []
        alignments.append(align_case(cid, gt, findings))

    per_case = []
    for a in alignments:
        per_case.append(
            {
                "id": a.case_id,
                "counts": a.counts(),
                "matches": a.matches,
                "misses": a.misses,
                "extras": a.extras,
            }
        )

    metrics = aggregate_tag_metrics(alignments)
    return {
        "run_id": run_id,
        "model": model,
        "aggregate": metrics,
        "per_case": per_case,
    }
