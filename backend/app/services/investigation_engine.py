"""
Rule-based root-cause candidate generation and scoring.

This is the core "intelligence" that is NOT delegated to an LLM. Given the
structured evidence collected by the deterministic tools, it produces a
ranked list of root-cause hypotheses with a confidence score in [0, 1].

Design decision (docs/decisions.md): scoring is a simple weighted-evidence
sum, not a learned model. With a demo-scale incident corpus there isn't
enough labeled data to train anything meaningful, and a transparent rule
set is easier to justify to a human reviewer than an opaque score - which
matters because remediation always requires human approval.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Candidate:
    key: str
    description: str
    score: float = 0.0
    supporting_tools: list[str] = field(default_factory=list)
    suggested_remediation: str = ""


ERROR_KEYWORDS = {
    "timeout": ("upstream_timeout", "Upstream API call timed out during ingestion.",
                "Add retry with backoff and circuit breaker around the upstream API call."),
    "duplicate": ("duplicate_records", "Duplicate records were written to the target table.",
                  "Add a deduplication step keyed on the natural/primary key before load."),
    "missing partition": ("missing_partition", "An expected partition was missing at read time.",
                           "Add a partition-existence check with alerting before the pipeline reads."),
    "malformed": ("malformed_source_data", "Source data was malformed for at least one record.",
                  "Add schema/format validation at ingestion with a quarantine path for bad records."),
    "dependency": ("dependency_failure", "An upstream pipeline dependency failed or was delayed.",
                   "Add an explicit dependency-sensor/wait step with alerting on SLA breach."),
}


def _score_schema_changes(candidates: dict[str, Candidate], schema_changes: list[dict]) -> None:
    for ch in schema_changes:
        if ch["change_type"] == "type_changed":
            key = f"schema_type_change::{ch['column']}"
            candidates[key] = Candidate(
                key=key,
                description=(
                    f"Column '{ch['column']}' changed type from {ch['before']} to {ch['after']}, "
                    f"likely breaking a downstream transformation that expects {ch['before']}."
                ),
                score=0.45,
                supporting_tools=["schema_diff_tool"],
                suggested_remediation=(
                    f"Normalize/cast '{ch['column']}' to the expected type ({ch['before']}) "
                    f"in the ingestion transformation before it reaches the warehouse."
                ),
            )
        elif ch["change_type"] in ("added", "removed"):
            key = f"schema_{ch['change_type']}::{ch['column']}"
            candidates[key] = Candidate(
                key=key,
                description=f"Column '{ch['column']}' was {ch['change_type']} in the schema.",
                score=0.25,
                supporting_tools=["schema_diff_tool"],
                suggested_remediation=(
                    f"Update the pipeline's expected schema/contract to account for the "
                    f"{ch['change_type']} column '{ch['column']}'."
                ),
            )


def _score_git_changes(candidates: dict[str, Candidate], git_changes: list[dict]) -> None:
    for gc in git_changes:
        matched_key = None
        for key, cand in candidates.items():
            col = key.split("::")[-1] if "::" in key else None
            haystack = f"{gc['message']} {gc['diff_summary']} {' '.join(gc.get('files_changed', []))}".lower()
            if col and col.lower() in haystack:
                matched_key = key
                break
        if matched_key:
            candidates[matched_key].score += 0.35
            candidates[matched_key].supporting_tools.append("git_change_tool")
            candidates[matched_key].description += (
                f" A related code/config change (commit {gc['commit_sha'][:7]} by {gc['author']}: "
                f"\"{gc['message']}\") was made shortly before the failure."
            )


def _score_data_quality(candidates: dict[str, Candidate], dq_results: list[dict]) -> None:
    for dq in dq_results:
        if dq["passed"]:
            continue
        col = dq.get("column_name")
        matched_key = None
        if col:
            for key in candidates:
                if key.endswith(f"::{col}"):
                    matched_key = key
                    break
        if matched_key:
            candidates[matched_key].score += 0.15
            candidates[matched_key].supporting_tools.append("data_quality_tool")
            candidates[matched_key].description += (
                f" Data-quality check '{dq['check_name']}' on '{col}' failed "
                f"(value={dq.get('metric_value')}, baseline={dq.get('baseline_value')})."
            )
        else:
            key = f"data_quality::{dq['check_name']}::{col or 'unknown'}"
            candidates.setdefault(key, Candidate(
                key=key,
                description=(
                    f"Data-quality check '{dq['check_name']}' failed on "
                    f"'{col or 'an unspecified column'}' (value={dq.get('metric_value')}, "
                    f"baseline={dq.get('baseline_value')})."
                ),
                score=0.3,
                supporting_tools=["data_quality_tool"],
                suggested_remediation=(
                    f"Investigate and fix the source of the '{dq['check_name']}' anomaly on "
                    f"'{col or 'the affected column'}', then re-run affected downstream steps."
                ),
            ))


def _score_logs(candidates: dict[str, Candidate], log_entries: list[dict]) -> None:
    combined = " ".join(e["message"].lower() for e in log_entries)
    for phrase, (key, desc, remediation) in ERROR_KEYWORDS.items():
        if phrase in combined:
            candidates.setdefault(key, Candidate(
                key=key, description=desc, score=0.3,
                supporting_tools=["log_search_tool"], suggested_remediation=remediation,
            ))
            candidates[key].score += 0.1
            if "log_search_tool" not in candidates[key].supporting_tools:
                candidates[key].supporting_tools.append("log_search_tool")


def _score_historical_incidents(candidates: dict[str, Candidate], historical: list[dict]) -> None:
    if not historical:
        return
    # Boost whichever current candidate's description shares the most
    # keyword overlap with the top historical incident's root cause text.
    top_hist = historical[0]
    hist_text = f"{top_hist.get('title', '')} {top_hist.get('root_cause', '')}".lower()
    best_key, best_overlap = None, 0
    for key, cand in candidates.items():
        overlap = sum(1 for w in set(cand.description.lower().split()) if w in hist_text and len(w) > 4)
        if overlap > best_overlap:
            best_key, best_overlap = key, overlap
    if best_key and best_overlap > 0:
        candidates[best_key].score += 0.15
        candidates[best_key].supporting_tools.append("historical_incident_tool")
        candidates[best_key].description += (
            f" A similar prior incident ('{top_hist['title']}') had the same underlying pattern."
        )


def generate_candidates(
    schema_changes: list[dict],
    git_changes: list[dict],
    dq_results: list[dict],
    log_entries: list[dict],
    historical_incidents: list[dict],
) -> list[Candidate]:
    candidates: dict[str, Candidate] = {}

    _score_schema_changes(candidates, schema_changes)
    _score_git_changes(candidates, git_changes)
    _score_data_quality(candidates, dq_results)
    _score_logs(candidates, log_entries)
    _score_historical_incidents(candidates, historical_incidents)

    ranked = sorted(candidates.values(), key=lambda c: c.score, reverse=True)
    for c in ranked:
        c.score = min(round(c.score, 2), 0.97)  # never claim absolute certainty
        c.supporting_tools = sorted(set(c.supporting_tools))
    return ranked


def severity_from_score(score: float, dq_failed_count: int) -> str:
    if score >= 0.7 or dq_failed_count >= 3:
        return "HIGH"
    if score >= 0.4:
        return "MEDIUM"
    return "LOW"
