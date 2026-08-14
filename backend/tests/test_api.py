from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_db
from app.models.tables import Pipeline, PipelineRun, Incident


@pytest.fixture()
def client(db_session):
    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_list_pipelines_empty(client):
    r = client.get("/api/pipelines")
    assert r.status_code == 200
    assert r.json() == []


def test_pipeline_not_found(client):
    r = client.get("/api/pipelines/does-not-exist")
    assert r.status_code == 404


def test_investigate_and_approve_flow(client, db_session):
    p = Pipeline(id="p1", name="n", owner_team="t", description="d", source_system="s", target_table="t")
    db_session.add(p)
    run = PipelineRun(id="r1", pipeline_id="p1", run_number=1, status="failed",
                       started_at=datetime(2026, 1, 1), error_summary="boom")
    db_session.add(run)
    incident = Incident(id="INC-1", pipeline_id="p1", triggering_run_id="r1",
                         title="t", status="open", created_at=datetime(2026, 1, 1))
    db_session.add(incident)
    db_session.commit()

    r = client.post("/api/incidents/INC-1/investigate")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "AWAITING_HUMAN_APPROVAL"

    r2 = client.get("/api/incidents/INC-1/evidence")
    assert r2.status_code == 200
    assert len(r2.json()) >= 1

    r3 = client.post("/api/incidents/INC-1/approve-remediation",
                      json={"approved_by": "alice@example.com", "decision": "approve"})
    assert r3.status_code == 200
    assert r3.json()["status"] == "approved"

    r4 = client.get("/api/incidents/INC-1")
    assert r4.json()["status"] == "resolved"


def test_investigate_missing_incident_returns_404(client):
    r = client.post("/api/incidents/does-not-exist/investigate")
    assert r.status_code == 404


def test_approve_rejects_invalid_decision(client, db_session):
    p = Pipeline(id="p2", name="n", owner_team="t", description="d", source_system="s", target_table="t")
    db_session.add(p)
    run = PipelineRun(id="r2", pipeline_id="p2", run_number=1, status="failed",
                       started_at=datetime(2026, 1, 1), error_summary="boom")
    db_session.add(run)
    incident = Incident(id="INC-2", pipeline_id="p2", triggering_run_id="r2",
                         title="t", status="open", created_at=datetime(2026, 1, 1))
    db_session.add(incident)
    db_session.commit()
    client.post("/api/incidents/INC-2/investigate")

    r = client.post("/api/incidents/INC-2/approve-remediation",
                     json={"approved_by": "alice", "decision": "maybe"})
    assert r.status_code == 400
