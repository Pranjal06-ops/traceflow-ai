from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PipelineOut(BaseModel):
    id: str
    name: str
    owner_team: str
    description: str
    source_system: str
    target_table: str

    class Config:
        from_attributes = True


class PipelineRunOut(BaseModel):
    id: str
    pipeline_id: str
    run_number: int
    status: str
    started_at: datetime
    ended_at: Optional[datetime]
    rows_processed: Optional[int]
    error_summary: Optional[str]

    class Config:
        from_attributes = True


class IncidentOut(BaseModel):
    id: str
    pipeline_id: str
    triggering_run_id: str
    title: str
    severity: Optional[str]
    status: str
    created_at: datetime
    root_cause: Optional[str]
    confidence: Optional[float]

    class Config:
        from_attributes = True


class EvidenceItemOut(BaseModel):
    source_tool: str
    summary: str
    weight: float = 1.0


class ValidationCheckOut(BaseModel):
    check_name: str
    passed: bool
    details: Optional[str]


class RemediationOut(BaseModel):
    id: int
    description: str
    status: str
    created_at: datetime
    validation_results: list[ValidationCheckOut] = []

    class Config:
        from_attributes = True


class InvestigationReportOut(BaseModel):
    incident_id: str
    pipeline_id: str
    severity: Optional[str]
    root_cause: Optional[str]
    confidence: Optional[float]
    evidence: list[dict]
    remediation_description: Optional[str]
    validation_results: list[dict]
    status: str
    tool_trace: list[dict]
    synthesis_method: Optional[str]


class ApprovalRequest(BaseModel):
    approved_by: str
    decision: str  # "approve" | "reject"
