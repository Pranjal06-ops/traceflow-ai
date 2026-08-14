import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.graph import run_investigation
from app.db.session import get_db
from app.models.tables import (
    Pipeline, PipelineRun, Incident, IncidentEvidence,
    RemediationProposal, ValidationResult,
)
from app.schemas import api as schemas

router = APIRouter(prefix="/api")
logger = logging.getLogger("traceflow.api")


@router.get("/pipelines", response_model=list[schemas.PipelineOut])
def list_pipelines(db: Session = Depends(get_db)):
    return db.execute(select(Pipeline)).scalars().all()


@router.get("/pipelines/{pipeline_id}", response_model=schemas.PipelineOut)
def get_pipeline(pipeline_id: str, db: Session = Depends(get_db)):
    p = db.get(Pipeline, pipeline_id)
    if not p:
        raise HTTPException(404, "Pipeline not found")
    return p


@router.get("/runs", response_model=list[schemas.PipelineRunOut])
def list_runs(pipeline_id: str | None = None, db: Session = Depends(get_db)):
    q = select(PipelineRun)
    if pipeline_id:
        q = q.where(PipelineRun.pipeline_id == pipeline_id)
    return db.execute(q.order_by(PipelineRun.started_at.desc())).scalars().all()


@router.get("/incidents", response_model=list[schemas.IncidentOut])
def list_incidents(db: Session = Depends(get_db)):
    return db.execute(select(Incident).order_by(Incident.created_at.desc())).scalars().all()


@router.get("/incidents/{incident_id}", response_model=schemas.IncidentOut)
def get_incident(incident_id: str, db: Session = Depends(get_db)):
    inc = db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(404, "Incident not found")
    return inc


@router.post("/incidents/{incident_id}/investigate", response_model=schemas.InvestigationReportOut)
def investigate_incident(incident_id: str, db: Session = Depends(get_db)):
    inc = db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(404, "Incident not found")

    state = run_investigation(db, inc)
    report = state["final_report"]

    # Persist results
    inc.root_cause = report["root_cause"]
    inc.confidence = report["confidence"]
    inc.severity = report["severity"]

    db.execute(IncidentEvidence.__table__.delete().where(IncidentEvidence.incident_id == incident_id))
    for ev in report["evidence"]:
        db.add(IncidentEvidence(incident_id=incident_id, source_tool=ev["source_tool"], summary=ev["summary"]))

    remediation = RemediationProposal(
        incident_id=incident_id,
        description=report["remediation_description"],
        status="proposed",
    )
    db.add(remediation)
    db.flush()

    for vr in report["validation_results"]:
        db.add(ValidationResult(
            remediation_id=remediation.id,
            check_name=vr["check_name"], passed=vr["passed"], details=vr["details"],
        ))

    db.commit()
    logger.info("investigation complete incident_id=%s confidence=%s", incident_id, report["confidence"])
    return report


@router.get("/incidents/{incident_id}/evidence", response_model=list[schemas.EvidenceItemOut])
def get_evidence(incident_id: str, db: Session = Depends(get_db)):
    rows = db.execute(
        select(IncidentEvidence).where(IncidentEvidence.incident_id == incident_id)
    ).scalars().all()
    return [schemas.EvidenceItemOut(source_tool=r.source_tool, summary=r.summary, weight=r.weight) for r in rows]


@router.post("/incidents/{incident_id}/approve-remediation")
def approve_remediation(incident_id: str, body: schemas.ApprovalRequest, db: Session = Depends(get_db)):
    remediation = db.execute(
        select(RemediationProposal)
        .where(RemediationProposal.incident_id == incident_id)
        .order_by(RemediationProposal.created_at.desc())
    ).scalars().first()
    if not remediation:
        raise HTTPException(404, "No remediation proposal found for this incident")

    if body.decision not in ("approve", "reject"):
        raise HTTPException(400, "decision must be 'approve' or 'reject'")

    remediation.status = "approved" if body.decision == "approve" else "rejected"
    remediation.approved_by = body.approved_by
    from datetime import datetime
    remediation.approved_at = datetime.utcnow()

    incident = db.get(Incident, incident_id)
    if incident:
        incident.status = "resolved" if body.decision == "approve" else "open"

    db.commit()
    logger.info(
        "remediation %s incident_id=%s by=%s", remediation.status, incident_id, body.approved_by
    )
    return {"remediation_id": remediation.id, "status": remediation.status}


@router.get("/incidents/{incident_id}/remediations", response_model=list[schemas.RemediationOut])
def get_remediations(incident_id: str, db: Session = Depends(get_db)):
    rows = db.execute(
        select(RemediationProposal).where(RemediationProposal.incident_id == incident_id)
    ).scalars().all()
    return rows


@router.get("/evaluations")
def get_evaluations():
    """
    Returns the most recent evaluation report produced by
    scripts/run_evaluation.py, or an explicit "pending" status if that
    script has never been run. We never synthesize a placeholder report -
    see docs/evaluation.md.
    """
    path = Path(__file__).resolve().parents[3] / "docs" / "evaluation_results.json"
    if not path.exists():
        return {"status": "pending", "message": "Evaluation results pending. Run scripts/run_evaluation.py."}
    return {"status": "complete", **json.loads(path.read_text())}
