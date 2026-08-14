from datetime import datetime

from app.agents.graph import run_investigation
from app.models.tables import (
    Pipeline, PipelineRun, PipelineLog, SchemaTable, SchemaVersion,
    DataQualityResult, GitChange, Incident,
)


def _seed_flagship_scenario(db):
    p = Pipeline(id="pl-1", name="customer_daily_ingestion", owner_team="Data Platform",
                 description="d", source_system="CRM", target_table="dim_customer")
    db.add(p)

    good = PipelineRun(id="run-1", pipeline_id="pl-1", run_number=1, status="success",
                        started_at=datetime(2026, 1, 1))
    bad = PipelineRun(id="run-2", pipeline_id="pl-1", run_number=2, status="failed",
                       started_at=datetime(2026, 1, 2),
                       error_summary="TypeError: invalid literal for int()")
    db.add_all([good, bad])

    db.add_all([
        PipelineLog(run_id="run-2", timestamp=datetime(2026, 1, 2, 0, 1), level="ERROR",
                    message="TypeError while casting customer_segment to INTEGER."),
    ])

    schema = SchemaTable(id="schema-1", pipeline_id="pl-1", table_name="dim_customer")
    db.add(schema)
    db.flush()
    db.add(SchemaVersion(schema_id="schema-1", effective_run_id="run-1",
                          columns={"customer_segment": "INTEGER"}, recorded_at=datetime(2026, 1, 1)))
    db.add(SchemaVersion(schema_id="schema-1", effective_run_id="run-2",
                          columns={"customer_segment": "VARCHAR"}, recorded_at=datetime(2026, 1, 2)))

    db.add(DataQualityResult(run_id="run-2", check_name="type_conformance", column_name="customer_segment",
                              metric_value=0.6, baseline_value=0.0, passed=False))

    db.add(GitChange(id="gc-1", pipeline_id="pl-1", commit_sha="deadbeef", author="dev",
                      committed_at=datetime(2026, 1, 1, 23), message="update customer_segment mapping",
                      files_changed=["x.py"], diff_summary="d"))

    incident = Incident(id="INC-1", pipeline_id="pl-1", triggering_run_id="run-2",
                         title="customer_segment mismatch", status="open", created_at=datetime(2026, 1, 2))
    db.add(incident)
    db.commit()
    return incident


def test_full_investigation_produces_grounded_root_cause(db_session):
    incident = _seed_flagship_scenario(db_session)
    state = run_investigation(db_session, incident)

    report = state["final_report"]
    assert report["status"] == "AWAITING_HUMAN_APPROVAL"
    assert "customer_segment" in report["root_cause"]
    assert report["confidence"] > 0.5
    assert report["severity"] in ("HIGH", "MEDIUM")

    # Every tool in the pipeline should have run and been traced.
    tool_names = {t["tool"] for t in report["tool_trace"]}
    assert {
        "log_search_tool", "schema_diff_tool", "data_quality_tool",
        "git_change_tool", "sql_investigation_tool", "historical_incident_tool",
        "validation_tool",
    }.issubset(tool_names)

    # Root cause explanation must only reference evidence that was actually
    # collected - a coarse grounding check: every evidence summary's key
    # noun phrase or the root cause text overlaps with actual evidence.
    evidence_text = " ".join(e["summary"] for e in report["evidence"])
    assert "customer_segment" in evidence_text


def test_investigation_with_no_evidence_is_inconclusive(db_session):
    p = Pipeline(id="pl-empty", name="empty_pipeline", owner_team="t", description="d",
                 source_system="s", target_table="t")
    db_session.add(p)
    run = PipelineRun(id="run-empty", pipeline_id="pl-empty", run_number=1, status="failed",
                       started_at=datetime(2026, 1, 1), error_summary="unknown")
    db_session.add(run)
    incident = Incident(id="INC-empty", pipeline_id="pl-empty", triggering_run_id="run-empty",
                         status="open", title="mystery failure", created_at=datetime(2026, 1, 1))
    db_session.add(incident)
    db_session.commit()

    state = run_investigation(db_session, incident)
    report = state["final_report"]
    assert report["confidence"] == 0.0
    assert "Insufficient evidence" in report["root_cause"]
