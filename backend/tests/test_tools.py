from datetime import datetime

from app.models.tables import (
    Pipeline, PipelineRun, PipelineLog, SchemaTable, SchemaVersion,
    DataQualityResult, GitChange, Incident,
)
from app.tools import investigation_tools as t


def _make_pipeline_with_schema_change(db):
    p = Pipeline(id="p1", name="test_pipeline", owner_team="X", description="d",
                 source_system="s", target_table="t")
    db.add(p)
    run1 = PipelineRun(id="r1", pipeline_id="p1", run_number=1, status="success",
                        started_at=datetime(2026, 1, 1))
    run2 = PipelineRun(id="r2", pipeline_id="p1", run_number=2, status="failed",
                        started_at=datetime(2026, 1, 2), error_summary="boom")
    db.add_all([run1, run2])
    schema = SchemaTable(id="s1", pipeline_id="p1", table_name="tbl")
    db.add(schema)
    db.flush()
    db.add(SchemaVersion(schema_id="s1", effective_run_id="r1",
                          columns={"a": "INTEGER", "b": "VARCHAR"}, recorded_at=datetime(2026, 1, 1)))
    db.add(SchemaVersion(schema_id="s1", effective_run_id="r2",
                          columns={"a": "VARCHAR", "b": "VARCHAR", "c": "INTEGER"}, recorded_at=datetime(2026, 1, 2)))
    db.commit()
    return p, run1, run2


def test_schema_diff_detects_type_change_and_addition(db_session):
    _make_pipeline_with_schema_change(db_session)
    result = t.schema_diff_tool(db_session, t.SchemaDiffInput(pipeline_id="p1", around_run_id="r2"))
    assert result.ok
    changes_by_col = {c.column: c for c in result.changes}
    assert changes_by_col["a"].change_type == "type_changed"
    assert changes_by_col["a"].before == "INTEGER"
    assert changes_by_col["a"].after == "VARCHAR"
    assert changes_by_col["c"].change_type == "added"


def test_schema_diff_no_history_returns_empty(db_session):
    p = Pipeline(id="p2", name="n", owner_team="t", description="d", source_system="s", target_table="t")
    db_session.add(p)
    db_session.commit()
    result = t.schema_diff_tool(db_session, t.SchemaDiffInput(pipeline_id="p2", around_run_id="does-not-exist"))
    assert result.ok
    assert result.changes == []


def test_log_search_filters_by_level(db_session):
    _make_pipeline_with_schema_change(db_session)
    db_session.add_all([
        PipelineLog(run_id="r2", timestamp=datetime(2026, 1, 2, 0, 1), level="INFO", message="starting"),
        PipelineLog(run_id="r2", timestamp=datetime(2026, 1, 2, 0, 2), level="ERROR", message="it broke"),
    ])
    db_session.commit()
    result = t.log_search_tool(db_session, t.LogSearchInput(run_id="r2", levels=["ERROR"]))
    assert result.ok
    assert len(result.entries) == 1
    assert result.entries[0]["message"] == "it broke"


def test_data_quality_tool_returns_only_this_run(db_session):
    _make_pipeline_with_schema_change(db_session)
    db_session.add_all([
        DataQualityResult(run_id="r2", check_name="null_rate", column_name="a",
                           metric_value=0.5, baseline_value=0.01, passed=False),
        DataQualityResult(run_id="r1", check_name="null_rate", column_name="a",
                           metric_value=0.01, baseline_value=0.01, passed=True),
    ])
    db_session.commit()
    result = t.data_quality_tool(db_session, t.DataQualityInput(run_id="r2"))
    assert result.ok
    assert len(result.results) == 1
    assert result.results[0].passed is False


def test_sql_investigation_tool_rejects_non_allowlisted_query(db_session):
    _make_pipeline_with_schema_change(db_session)
    result = t.sql_investigation_tool(
        db_session, t.SQLInvestigationInput(pipeline_id="p1", query_name="DROP TABLE pipelines")
    )
    assert result.ok is False
    assert "not in the allow-list" in result.error


def test_sql_investigation_tool_computes_failure_rate(db_session):
    _make_pipeline_with_schema_change(db_session)
    result = t.sql_investigation_tool(
        db_session, t.SQLInvestigationInput(pipeline_id="p1", query_name="recent_failure_rate")
    )
    assert result.ok
    assert result.result["sample_size"] == 2
    assert result.result["failure_rate"] == 0.5


def test_historical_incident_tool_matches_on_keyword_overlap(db_session):
    p = Pipeline(id="p3", name="n", owner_team="t", description="d", source_system="s", target_table="t")
    db_session.add(p)
    db_session.add(Incident(
        id="INC-1", pipeline_id="p3", triggering_run_id="none", title="segment type mismatch",
        status="resolved", root_cause="upstream changed segment representation",
    ))
    db_session.add(Incident(
        id="INC-2", pipeline_id="p3", triggering_run_id="none", title="unrelated timeout issue",
        status="resolved", root_cause="network blip",
    ))
    db_session.commit()
    result = t.historical_incident_tool(
        db_session, t.HistoricalIncidentInput(pipeline_id="p3", keywords=["segment", "mismatch"])
    )
    assert result.ok
    assert len(result.incidents) == 1
    assert result.incidents[0]["id"] == "INC-1"


def test_validation_tool_flags_vague_remediation(db_session):
    result = t.validation_tool(db_session, t.ValidationInput(
        pipeline_id="p1", remediation_description="fix it", related_schema_changes=[],
    ))
    assert result.ok
    checks = {c.check_name: c.passed for c in result.checks}
    assert checks["schema_test"] is False
    assert checks["transformation_test"] is False
    assert checks["sample_data_validation"] is False
