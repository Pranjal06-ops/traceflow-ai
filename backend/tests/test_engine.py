from app.services.investigation_engine import generate_candidates, severity_from_score


def test_schema_and_git_and_dq_evidence_reinforce_same_candidate():
    schema_changes = [{"column": "customer_segment", "change_type": "type_changed",
                        "before": "INTEGER", "after": "VARCHAR"}]
    git_changes = [{"commit_sha": "abc123", "author": "j", "message": "update customer_segment mapping",
                     "diff_summary": "changed mapping", "files_changed": ["x.py"]}]
    dq = [{"check_name": "type_conformance", "column_name": "customer_segment",
           "metric_value": 0.6, "baseline_value": 0.0, "passed": False}]

    candidates = generate_candidates(schema_changes, git_changes, dq, [], [])
    assert candidates, "expected at least one candidate"
    top = candidates[0]
    assert "customer_segment" in top.description
    assert set(top.supporting_tools) == {"schema_diff_tool", "git_change_tool", "data_quality_tool"}
    # combined evidence should score higher than schema change alone
    schema_only = generate_candidates(schema_changes, [], [], [], [])
    assert top.score > schema_only[0].score


def test_log_keyword_detects_timeout_pattern():
    logs = [{"level": "ERROR", "message": "requests.exceptions.Timeout: upstream request timeout"}]
    candidates = generate_candidates([], [], [], logs, [])
    assert any(c.key == "upstream_timeout" for c in candidates)


def test_no_evidence_returns_no_candidates():
    assert generate_candidates([], [], [], [], []) == []


def test_confidence_is_capped_below_one():
    schema_changes = [{"column": "x", "change_type": "type_changed", "before": "A", "after": "B"}]
    git_changes = [{"commit_sha": "1", "author": "a", "message": "x change", "diff_summary": "x",
                     "files_changed": ["x"]}]
    dq = [{"check_name": "c", "column_name": "x", "metric_value": 1, "baseline_value": 0, "passed": False}]
    historical = [{"title": "x issue", "root_cause": "x change broke things"}]
    candidates = generate_candidates(schema_changes, git_changes, dq, [], historical)
    assert all(c.score <= 0.97 for c in candidates)


def test_severity_thresholds():
    assert severity_from_score(0.8, 0) == "HIGH"
    assert severity_from_score(0.5, 0) == "MEDIUM"
    assert severity_from_score(0.1, 0) == "LOW"
    assert severity_from_score(0.1, 3) == "HIGH"
