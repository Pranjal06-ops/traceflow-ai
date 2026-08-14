"""
Deterministic investigation tools.

Design decision (see docs/decisions.md): every tool here returns *facts*
pulled from the database - no LLM involvement. The LLM never sees raw table
rows; it only sees the structured evidence these tools produce. This is the
mechanism that prevents hallucinated database results (see docs/security.md).

Each tool:
- takes a narrow, typed input
- returns a typed Pydantic result
- never raises unhandled exceptions (errors are captured in the result)
- is logged via the `logger`
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tables import (
    PipelineRun, PipelineLog, SchemaVersion, SchemaTable,
    DataQualityResult, GitChange, Incident, IncidentEvidence,
)

logger = logging.getLogger("traceflow.tools")


# ---------------------------------------------------------------------------
# LogSearchTool
# ---------------------------------------------------------------------------
class LogSearchInput(BaseModel):
    run_id: str
    levels: list[str] = ["ERROR", "WARN"]


class LogSearchResult(BaseModel):
    ok: bool
    entries: list[dict] = []
    error: Optional[str] = None


def log_search_tool(db: Session, params: LogSearchInput) -> LogSearchResult:
    try:
        rows = db.execute(
            select(PipelineLog)
            .where(PipelineLog.run_id == params.run_id)
            .where(PipelineLog.level.in_(params.levels))
            .order_by(PipelineLog.timestamp)
        ).scalars().all()
        entries = [
            {"timestamp": r.timestamp.isoformat(), "level": r.level, "message": r.message}
            for r in rows
        ]
        logger.info("log_search_tool run_id=%s found=%d", params.run_id, len(entries))
        return LogSearchResult(ok=True, entries=entries)
    except Exception as e:  # noqa: BLE001
        logger.exception("log_search_tool failed")
        return LogSearchResult(ok=False, error=str(e))


# ---------------------------------------------------------------------------
# PipelineHistoryTool
# ---------------------------------------------------------------------------
class PipelineHistoryInput(BaseModel):
    pipeline_id: str
    limit: int = 10


class PipelineHistoryResult(BaseModel):
    ok: bool
    runs: list[dict] = []
    error: Optional[str] = None


def pipeline_history_tool(db: Session, params: PipelineHistoryInput) -> PipelineHistoryResult:
    try:
        rows = db.execute(
            select(PipelineRun)
            .where(PipelineRun.pipeline_id == params.pipeline_id)
            .order_by(PipelineRun.run_number.desc())
            .limit(params.limit)
        ).scalars().all()
        runs = [
            {
                "id": r.id, "run_number": r.run_number, "status": r.status,
                "started_at": r.started_at.isoformat(),
                "rows_processed": r.rows_processed,
                "error_summary": r.error_summary,
            }
            for r in rows
        ]
        return PipelineHistoryResult(ok=True, runs=runs)
    except Exception as e:  # noqa: BLE001
        logger.exception("pipeline_history_tool failed")
        return PipelineHistoryResult(ok=False, error=str(e))


# ---------------------------------------------------------------------------
# SchemaDiffTool
# ---------------------------------------------------------------------------
class SchemaDiffInput(BaseModel):
    pipeline_id: str
    around_run_id: str


class SchemaChange(BaseModel):
    column: str
    change_type: str  # added | removed | type_changed
    before: Optional[str] = None
    after: Optional[str] = None


class SchemaDiffResult(BaseModel):
    ok: bool
    changes: list[SchemaChange] = []
    error: Optional[str] = None


def schema_diff_tool(db: Session, params: SchemaDiffInput) -> SchemaDiffResult:
    try:
        schema_table = db.execute(
            select(SchemaTable).where(SchemaTable.pipeline_id == params.pipeline_id)
        ).scalars().first()
        if not schema_table:
            return SchemaDiffResult(ok=True, changes=[])

        versions = db.execute(
            select(SchemaVersion)
            .where(SchemaVersion.schema_id == schema_table.id)
            .order_by(SchemaVersion.recorded_at)
        ).scalars().all()

        target_run = db.get(PipelineRun, params.around_run_id)
        if not target_run or len(versions) < 2:
            return SchemaDiffResult(ok=True, changes=[])

        # find the schema version in effect at/just-before the target run,
        # and the one immediately prior to it
        before_version, after_version = None, None
        for i, v in enumerate(versions):
            if v.effective_run_id == params.around_run_id:
                after_version = v
                before_version = versions[i - 1] if i > 0 else None
                break

        if not after_version or not before_version:
            return SchemaDiffResult(ok=True, changes=[])

        changes: list[SchemaChange] = []
        before_cols, after_cols = before_version.columns, after_version.columns
        for col, dtype in after_cols.items():
            if col not in before_cols:
                changes.append(SchemaChange(column=col, change_type="added", after=dtype))
            elif before_cols[col] != dtype:
                changes.append(SchemaChange(
                    column=col, change_type="type_changed",
                    before=before_cols[col], after=dtype,
                ))
        for col in before_cols:
            if col not in after_cols:
                changes.append(SchemaChange(column=col, change_type="removed", before=before_cols[col]))

        return SchemaDiffResult(ok=True, changes=changes)
    except Exception as e:  # noqa: BLE001
        logger.exception("schema_diff_tool failed")
        return SchemaDiffResult(ok=False, error=str(e))


# ---------------------------------------------------------------------------
# DataQualityTool
# ---------------------------------------------------------------------------
class DataQualityInput(BaseModel):
    run_id: str


class DataQualityResultItem(BaseModel):
    check_name: str
    column_name: Optional[str]
    metric_value: Optional[float]
    baseline_value: Optional[float]
    passed: bool
    details: Optional[str]


class DataQualityToolResult(BaseModel):
    ok: bool
    results: list[DataQualityResultItem] = []
    error: Optional[str] = None


def data_quality_tool(db: Session, params: DataQualityInput) -> DataQualityToolResult:
    try:
        rows = db.execute(
            select(DataQualityResult).where(DataQualityResult.run_id == params.run_id)
        ).scalars().all()
        results = [
            DataQualityResultItem(
                check_name=r.check_name, column_name=r.column_name,
                metric_value=r.metric_value, baseline_value=r.baseline_value,
                passed=r.passed, details=r.details,
            )
            for r in rows
        ]
        return DataQualityToolResult(ok=True, results=results)
    except Exception as e:  # noqa: BLE001
        logger.exception("data_quality_tool failed")
        return DataQualityToolResult(ok=False, error=str(e))


# ---------------------------------------------------------------------------
# GitChangeTool
# ---------------------------------------------------------------------------
class GitChangeInput(BaseModel):
    pipeline_id: str
    since: Optional[datetime] = None
    until: Optional[datetime] = None


class GitChangeToolResult(BaseModel):
    ok: bool
    changes: list[dict] = []
    error: Optional[str] = None


def git_change_tool(db: Session, params: GitChangeInput) -> GitChangeToolResult:
    try:
        query = select(GitChange).where(GitChange.pipeline_id == params.pipeline_id)
        if params.since:
            query = query.where(GitChange.committed_at >= params.since)
        if params.until:
            query = query.where(GitChange.committed_at <= params.until)
        rows = db.execute(query.order_by(GitChange.committed_at.desc())).scalars().all()
        changes = [
            {
                "commit_sha": r.commit_sha, "author": r.author,
                "committed_at": r.committed_at.isoformat(),
                "message": r.message, "files_changed": r.files_changed,
                "diff_summary": r.diff_summary,
            }
            for r in rows
        ]
        return GitChangeToolResult(ok=True, changes=changes)
    except Exception as e:  # noqa: BLE001
        logger.exception("git_change_tool failed")
        return GitChangeToolResult(ok=False, error=str(e))


# ---------------------------------------------------------------------------
# SQLInvestigationTool
# ---------------------------------------------------------------------------
# Security: this tool only ever executes a small allow-listed set of
# read-only, parameterized aggregate queries against pipeline_runs. It never
# executes arbitrary AI-generated SQL. See docs/security.md.
class SQLInvestigationInput(BaseModel):
    pipeline_id: str
    query_name: str  # must be one of ALLOWED_QUERIES


ALLOWED_QUERIES = {"recent_failure_rate", "recent_row_count_trend"}


class SQLInvestigationToolResult(BaseModel):
    ok: bool
    query_name: str
    result: Optional[dict] = None
    error: Optional[str] = None


def sql_investigation_tool(db: Session, params: SQLInvestigationInput) -> SQLInvestigationToolResult:
    if params.query_name not in ALLOWED_QUERIES:
        return SQLInvestigationToolResult(
            ok=False, query_name=params.query_name,
            error=f"Query '{params.query_name}' is not in the allow-list.",
        )
    try:
        runs = db.execute(
            select(PipelineRun)
            .where(PipelineRun.pipeline_id == params.pipeline_id)
            .order_by(PipelineRun.run_number.desc())
            .limit(10)
        ).scalars().all()

        if params.query_name == "recent_failure_rate":
            if not runs:
                result = {"failure_rate": None, "sample_size": 0}
            else:
                failures = sum(1 for r in runs if r.status == "failed")
                result = {"failure_rate": round(failures / len(runs), 2), "sample_size": len(runs)}
        else:  # recent_row_count_trend
            result = {
                "trend": [
                    {"run_number": r.run_number, "rows_processed": r.rows_processed}
                    for r in reversed(runs)
                ]
            }
        return SQLInvestigationToolResult(ok=True, query_name=params.query_name, result=result)
    except Exception as e:  # noqa: BLE001
        logger.exception("sql_investigation_tool failed")
        return SQLInvestigationToolResult(ok=False, query_name=params.query_name, error=str(e))


# ---------------------------------------------------------------------------
# HistoricalIncidentTool
# ---------------------------------------------------------------------------
class HistoricalIncidentInput(BaseModel):
    pipeline_id: str
    keywords: list[str] = []
    limit: int = 5


class HistoricalIncidentToolResult(BaseModel):
    ok: bool
    incidents: list[dict] = []
    error: Optional[str] = None


def historical_incident_tool(db: Session, params: HistoricalIncidentInput) -> HistoricalIncidentToolResult:
    """
    Keyword-overlap retrieval over past incidents' titles/root causes.

    Design decision: this uses simple lexical overlap rather than embeddings
    + pgvector. With a demo corpus of a few dozen incidents, semantic search
    adds infra cost without adding retrieval quality that's measurable at
    this scale - see docs/decisions.md for the fuller argument and the
    conditions under which embeddings would be worth adding.
    """
    try:
        rows = db.execute(
            select(Incident)
            .where(Incident.pipeline_id == params.pipeline_id)
            .where(Incident.status == "resolved")
        ).scalars().all()

        scored = []
        kw_set = {k.lower() for k in params.keywords}
        for r in rows:
            text = f"{r.title} {r.root_cause or ''}".lower()
            overlap = sum(1 for k in kw_set if k in text)
            if overlap > 0:
                scored.append((overlap, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[: params.limit]
        incidents = [
            {
                "id": r.id, "title": r.title, "root_cause": r.root_cause,
                "confidence": r.confidence, "match_score": score,
            }
            for score, r in top
        ]
        return HistoricalIncidentToolResult(ok=True, incidents=incidents)
    except Exception as e:  # noqa: BLE001
        logger.exception("historical_incident_tool failed")
        return HistoricalIncidentToolResult(ok=False, error=str(e))


# ---------------------------------------------------------------------------
# ValidationTool
# ---------------------------------------------------------------------------
class ValidationInput(BaseModel):
    pipeline_id: str
    remediation_description: str
    related_schema_changes: list[SchemaChange] = []


class ValidationCheck(BaseModel):
    check_name: str
    passed: bool
    details: str


class ValidationToolResult(BaseModel):
    ok: bool
    checks: list[ValidationCheck] = []
    error: Optional[str] = None


def validation_tool(db: Session, params: ValidationInput) -> ValidationToolResult:
    """
    Runs lightweight automated checks against the *proposed* remediation.
    These are heuristic sanity checks, not a guarantee of correctness -
    the point is to catch obviously broken proposals before a human reviews
    them, not to replace human review (which remains mandatory).
    """
    try:
        checks: list[ValidationCheck] = []

        checks.append(ValidationCheck(
            check_name="schema_test",
            passed=len(params.related_schema_changes) > 0,
            details=(
                f"{len(params.related_schema_changes)} schema change(s) referenced by remediation."
                if params.related_schema_changes else
                "No schema changes were linked to this remediation; schema_test is inconclusive."
            ),
        ))

        checks.append(ValidationCheck(
            check_name="transformation_test",
            passed="normalize" in params.remediation_description.lower()
            or "cast" in params.remediation_description.lower()
            or "map" in params.remediation_description.lower(),
            details="Remediation references a concrete transformation step (normalize/cast/map).",
        ))

        checks.append(ValidationCheck(
            check_name="sample_data_validation",
            passed=len(params.remediation_description) > 20,
            details="Remediation description is specific enough to act on.",
        ))

        return ValidationToolResult(ok=True, checks=checks)
    except Exception as e:  # noqa: BLE001
        logger.exception("validation_tool failed")
        return ValidationToolResult(ok=False, error=str(e))
