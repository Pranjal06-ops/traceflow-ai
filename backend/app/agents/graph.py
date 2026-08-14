"""
LangGraph orchestration for the investigation workflow.

Nodes are thin wrappers around the deterministic tools in
app/tools/investigation_tools.py and the scoring engine in
app/services/investigation_engine.py. The LLM is invoked exactly once, in
`synthesize_evidence`, and only on already-collected structured evidence
(see app/services/llm_synthesis.py for why).

State transitions are intentionally linear (no branching/looping) because
the investigation is a fixed pipeline of evidence-gathering steps -
LangGraph is used here for its explicit state typing and node tracing, not
because the control flow needs graph-like branching. See docs/decisions.md.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Optional, TypedDict

from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from app.models.tables import PipelineRun, Incident
from app.services import investigation_engine, llm_synthesis
from app.tools import investigation_tools as t

logger = logging.getLogger("traceflow.agent")


class IncidentState(TypedDict, total=False):
    incident_id: str
    pipeline_id: str
    triggering_run_id: str

    logs: list[dict]
    historical_runs: list[dict]
    schema_changes: list[dict]
    data_quality_findings: list[dict]
    git_changes: list[dict]
    sql_findings: dict
    historical_incidents: list[dict]

    evidence: list[dict]          # flattened, tool-tagged evidence for the incident report
    tool_trace: list[dict]        # observability: which tools ran, when, how long

    candidates: list[dict]
    root_cause: str
    confidence: float
    severity: str

    remediation_description: str
    remediation_patch: Optional[str]
    validation_results: list[dict]
    synthesis_method: str

    final_report: dict


def _trace(state: IncidentState, tool_name: str, started: float, ok: bool) -> None:
    state.setdefault("tool_trace", []).append({
        "tool": tool_name,
        "duration_ms": round((time.time() - started) * 1000, 1),
        "ok": ok,
        "timestamp": datetime.utcnow().isoformat(),
    })


def build_graph(db: Session):

    def detect_failure(state: IncidentState) -> IncidentState:
        run = db.get(PipelineRun, state["triggering_run_id"])
        state["evidence"] = []
        state["evidence"].append({
            "source_tool": "detect_failure",
            "summary": f"Run {run.run_number} failed with status='{run.status}': {run.error_summary}",
        })
        return state

    def collect_logs(state: IncidentState) -> IncidentState:
        start = time.time()
        res = t.log_search_tool(db, t.LogSearchInput(run_id=state["triggering_run_id"]))
        state["logs"] = res.entries
        for e in res.entries:
            state["evidence"].append({"source_tool": "log_search_tool", "summary": f"[{e['level']}] {e['message']}"})
        _trace(state, "log_search_tool", start, res.ok)
        return state

    def analyze_schema(state: IncidentState) -> IncidentState:
        start = time.time()
        res = t.schema_diff_tool(db, t.SchemaDiffInput(
            pipeline_id=state["pipeline_id"], around_run_id=state["triggering_run_id"]
        ))
        changes = [c.model_dump() for c in res.changes]
        state["schema_changes"] = changes
        for c in changes:
            state["evidence"].append({
                "source_tool": "schema_diff_tool",
                "summary": f"Column '{c['column']}' {c['change_type']} (before={c['before']}, after={c['after']})",
            })
        _trace(state, "schema_diff_tool", start, res.ok)
        return state

    def analyze_data_quality(state: IncidentState) -> IncidentState:
        start = time.time()
        res = t.data_quality_tool(db, t.DataQualityInput(run_id=state["triggering_run_id"]))
        results = [r.model_dump() for r in res.results]
        state["data_quality_findings"] = results
        for r in results:
            if not r["passed"]:
                state["evidence"].append({
                    "source_tool": "data_quality_tool",
                    "summary": f"Check '{r['check_name']}' failed on '{r['column_name']}' "
                               f"(value={r['metric_value']}, baseline={r['baseline_value']})",
                })
        _trace(state, "data_quality_tool", start, res.ok)
        return state

    def inspect_git_changes(state: IncidentState) -> IncidentState:
        start = time.time()
        res = t.git_change_tool(db, t.GitChangeInput(pipeline_id=state["pipeline_id"]))
        changes = res.changes[:5]
        state["git_changes"] = changes
        for c in changes:
            state["evidence"].append({
                "source_tool": "git_change_tool",
                "summary": f"Commit {c['commit_sha'][:7]} by {c['author']}: {c['message']}",
            })
        _trace(state, "git_change_tool", start, res.ok)
        return state

    def query_database(state: IncidentState) -> IncidentState:
        start = time.time()
        res = t.sql_investigation_tool(db, t.SQLInvestigationInput(
            pipeline_id=state["pipeline_id"], query_name="recent_failure_rate"
        ))
        state["sql_findings"] = res.result or {}
        if res.ok and res.result:
            state["evidence"].append({
                "source_tool": "sql_investigation_tool",
                "summary": f"Recent failure rate: {res.result.get('failure_rate')} "
                           f"over last {res.result.get('sample_size')} runs.",
            })
        _trace(state, "sql_investigation_tool", start, res.ok)
        return state

    def retrieve_historical_incidents(state: IncidentState) -> IncidentState:
        start = time.time()
        run = db.get(PipelineRun, state["triggering_run_id"])
        keywords = (run.error_summary or "").replace(",", " ").split()
        res = t.historical_incident_tool(db, t.HistoricalIncidentInput(
            pipeline_id=state["pipeline_id"], keywords=keywords,
        ))
        state["historical_incidents"] = res.incidents
        for h in res.incidents:
            state["evidence"].append({
                "source_tool": "historical_incident_tool",
                "summary": f"Similar past incident '{h['title']}' (root cause: {h['root_cause']})",
            })
        _trace(state, "historical_incident_tool", start, res.ok)
        return state

    def synthesize_evidence(state: IncidentState) -> IncidentState:
        candidates = investigation_engine.generate_candidates(
            schema_changes=state.get("schema_changes", []),
            git_changes=state.get("git_changes", []),
            dq_results=state.get("data_quality_findings", []),
            log_entries=state.get("logs", []),
            historical_incidents=state.get("historical_incidents", []),
        )
        state["candidates"] = [
            {
                "key": c.key, "description": c.description, "score": c.score,
                "supporting_tools": c.supporting_tools,
                "suggested_remediation": c.suggested_remediation,
            }
            for c in candidates
        ]
        return state

    def identify_root_cause(state: IncidentState) -> IncidentState:
        candidates = state.get("candidates", [])
        dq_failed = sum(1 for d in state.get("data_quality_findings", []) if not d["passed"])

        if not candidates:
            state["root_cause"] = "Insufficient evidence to determine a root cause."
            state["confidence"] = 0.0
            state["severity"] = "LOW"
            state["remediation_description"] = "Escalate for manual investigation; automated evidence was inconclusive."
            return state

        top = candidates[0]
        synthesis = llm_synthesis.synthesize_root_cause(state["evidence"], candidates)
        state["root_cause"] = synthesis["root_cause_explanation"]
        state["confidence"] = top["score"]
        state["severity"] = investigation_engine.severity_from_score(top["score"], dq_failed)
        state["remediation_description"] = synthesis["remediation_description"]
        state["synthesis_method"] = synthesis["synthesis_method"]
        return state

    def generate_remediation(state: IncidentState) -> IncidentState:
        # already produced alongside root cause; kept as a distinct node so
        # the graph/report structure matches the documented workflow and so
        # a future version can add a separate remediation-refinement pass
        # without touching identify_root_cause.
        state["remediation_patch"] = None
        return state

    def validate_remediation(state: IncidentState) -> IncidentState:
        start = time.time()
        res = t.validation_tool(db, t.ValidationInput(
            pipeline_id=state["pipeline_id"],
            remediation_description=state.get("remediation_description", ""),
            related_schema_changes=[t.SchemaChange(**c) for c in state.get("schema_changes", [])],
        ))
        state["validation_results"] = [c.model_dump() for c in res.checks]
        _trace(state, "validation_tool", start, res.ok)
        return state

    def generate_incident_report(state: IncidentState) -> IncidentState:
        state["final_report"] = {
            "incident_id": state["incident_id"],
            "pipeline_id": state["pipeline_id"],
            "severity": state.get("severity"),
            "root_cause": state.get("root_cause"),
            "confidence": state.get("confidence"),
            "evidence": state.get("evidence"),
            "remediation_description": state.get("remediation_description"),
            "validation_results": state.get("validation_results"),
            "status": "AWAITING_HUMAN_APPROVAL",
            "tool_trace": state.get("tool_trace"),
            "synthesis_method": state.get("synthesis_method"),
        }
        return state

    graph = StateGraph(IncidentState)
    graph.add_node("detect_failure", detect_failure)
    graph.add_node("collect_logs", collect_logs)
    graph.add_node("analyze_schema", analyze_schema)
    graph.add_node("analyze_data_quality", analyze_data_quality)
    graph.add_node("inspect_git_changes", inspect_git_changes)
    graph.add_node("query_database", query_database)
    graph.add_node("retrieve_historical_incidents", retrieve_historical_incidents)
    graph.add_node("synthesize_evidence", synthesize_evidence)
    graph.add_node("identify_root_cause", identify_root_cause)
    graph.add_node("generate_remediation", generate_remediation)
    graph.add_node("validate_remediation", validate_remediation)
    graph.add_node("generate_incident_report", generate_incident_report)

    graph.set_entry_point("detect_failure")
    graph.add_edge("detect_failure", "collect_logs")
    graph.add_edge("collect_logs", "analyze_schema")
    graph.add_edge("analyze_schema", "analyze_data_quality")
    graph.add_edge("analyze_data_quality", "inspect_git_changes")
    graph.add_edge("inspect_git_changes", "query_database")
    graph.add_edge("query_database", "retrieve_historical_incidents")
    graph.add_edge("retrieve_historical_incidents", "synthesize_evidence")
    graph.add_edge("synthesize_evidence", "identify_root_cause")
    graph.add_edge("identify_root_cause", "generate_remediation")
    graph.add_edge("generate_remediation", "validate_remediation")
    graph.add_edge("validate_remediation", "generate_incident_report")
    graph.add_edge("generate_incident_report", END)

    return graph.compile()


def run_investigation(db: Session, incident: Incident) -> IncidentState:
    app_graph = build_graph(db)
    initial_state: IncidentState = {
        "incident_id": incident.id,
        "pipeline_id": incident.pipeline_id,
        "triggering_run_id": incident.triggering_run_id,
    }
    result = app_graph.invoke(initial_state)
    return result
