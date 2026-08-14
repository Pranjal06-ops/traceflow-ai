"""
SQLAlchemy ORM models.

Table set matches docs/architecture.md. Kept intentionally normalized and
small - this is a portfolio-scale system, not an attempt to model every edge
case a real data platform would need.
"""
from datetime import datetime

from sqlalchemy import (
    String, Integer, Float, DateTime, ForeignKey, Text, Boolean, JSON
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Pipeline(Base):
    __tablename__ = "pipelines"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    owner_team: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    source_system: Mapped[str] = mapped_column(String)
    target_table: Mapped[str] = mapped_column(String)

    runs: Mapped[list["PipelineRun"]] = relationship(back_populates="pipeline")


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    pipeline_id: Mapped[str] = mapped_column(ForeignKey("pipelines.id"))
    run_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)  # success | failed
    started_at: Mapped[datetime] = mapped_column(DateTime)
    ended_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    rows_processed: Mapped[int] = mapped_column(Integer, nullable=True)
    error_summary: Mapped[str] = mapped_column(Text, nullable=True)

    pipeline: Mapped["Pipeline"] = relationship(back_populates="runs")
    logs: Mapped[list["PipelineLog"]] = relationship(back_populates="run")


class PipelineLog(Base):
    __tablename__ = "pipeline_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime)
    level: Mapped[str] = mapped_column(String)  # INFO | WARN | ERROR
    message: Mapped[str] = mapped_column(Text)

    run: Mapped["PipelineRun"] = relationship(back_populates="logs")


class SchemaTable(Base):
    """Represents a logical table tracked for schema drift."""
    __tablename__ = "schemas"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    pipeline_id: Mapped[str] = mapped_column(ForeignKey("pipelines.id"))
    table_name: Mapped[str] = mapped_column(String)

    versions: Mapped[list["SchemaVersion"]] = relationship(back_populates="schema_table")


class SchemaVersion(Base):
    __tablename__ = "schema_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schema_id: Mapped[str] = mapped_column(ForeignKey("schemas.id"))
    effective_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"))
    columns: Mapped[dict] = mapped_column(JSON)  # {col_name: dtype}
    recorded_at: Mapped[datetime] = mapped_column(DateTime)

    schema_table: Mapped["SchemaTable"] = relationship(back_populates="versions")


class DataQualityResult(Base):
    __tablename__ = "data_quality_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"))
    check_name: Mapped[str] = mapped_column(String)
    column_name: Mapped[str] = mapped_column(String, nullable=True)
    metric_value: Mapped[float] = mapped_column(Float, nullable=True)
    baseline_value: Mapped[float] = mapped_column(Float, nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean)
    details: Mapped[str] = mapped_column(Text, nullable=True)


class GitChange(Base):
    __tablename__ = "git_changes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    pipeline_id: Mapped[str] = mapped_column(ForeignKey("pipelines.id"))
    commit_sha: Mapped[str] = mapped_column(String)
    author: Mapped[str] = mapped_column(String)
    committed_at: Mapped[datetime] = mapped_column(DateTime)
    message: Mapped[str] = mapped_column(Text)
    files_changed: Mapped[list] = mapped_column(JSON)
    diff_summary: Mapped[str] = mapped_column(Text)


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    pipeline_id: Mapped[str] = mapped_column(ForeignKey("pipelines.id"))
    triggering_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"))
    title: Mapped[str] = mapped_column(String)
    severity: Mapped[str] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    root_cause: Mapped[str] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=True)

    # Ground-truth label used ONLY by the evaluation harness, never shown to
    # the investigation engine. Null for real/unlabeled incidents.
    known_root_cause_label: Mapped[str] = mapped_column(String, nullable=True)

    evidence: Mapped[list["IncidentEvidence"]] = relationship(back_populates="incident")
    remediations: Mapped[list["RemediationProposal"]] = relationship(back_populates="incident")


class IncidentEvidence(Base):
    __tablename__ = "incident_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"))
    source_tool: Mapped[str] = mapped_column(String)
    summary: Mapped[str] = mapped_column(Text)
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)

    incident: Mapped["Incident"] = relationship(back_populates="evidence")


class RemediationProposal(Base):
    __tablename__ = "remediation_proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"))
    description: Mapped[str] = mapped_column(Text)
    patch_snippet: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, default="proposed")  # proposed|approved|rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    approved_by: Mapped[str] = mapped_column(String, nullable=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    incident: Mapped["Incident"] = relationship(back_populates="remediations")
    validation_results: Mapped[list["ValidationResult"]] = relationship(back_populates="remediation")


class ValidationResult(Base):
    __tablename__ = "validation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    remediation_id: Mapped[int] = mapped_column(ForeignKey("remediation_proposals.id"))
    check_name: Mapped[str] = mapped_column(String)
    passed: Mapped[bool] = mapped_column(Boolean)
    details: Mapped[str] = mapped_column(Text, nullable=True)

    remediation: Mapped["RemediationProposal"] = relationship(back_populates="validation_results")
