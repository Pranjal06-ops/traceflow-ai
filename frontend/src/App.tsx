import { useEffect, useState } from "react";
import { api } from "./services/api";
import type { Pipeline, PipelineRun, Incident, InvestigationReport, EvaluationReport } from "./types";
import "./App.css";

type View = "overview" | "incidents" | "evaluation";

function StatusPill({ status }: { status: string }) {
  const cls = status === "failed" || status === "open" ? "pill pill-red"
    : status === "success" || status === "resolved" ? "pill pill-green"
    : "pill pill-gray";
  return <span className={cls}>{status}</span>;
}

function SeverityPill({ severity }: { severity: string | null }) {
  if (!severity) return <span className="pill pill-gray">-</span>;
  const cls = severity === "HIGH" ? "pill pill-red" : severity === "MEDIUM" ? "pill pill-amber" : "pill pill-gray";
  return <span className={cls}>{severity}</span>;
}

function App() {
  const [view, setView] = useState<View>("overview");
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [selectedIncident, setSelectedIncident] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadAll = async () => {
    try {
      const [p, r, i] = await Promise.all([api.listPipelines(), api.listRuns(), api.listIncidents()]);
      setPipelines(p);
      setRuns(r);
      setIncidents(i);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => { loadAll(); }, []);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">TF</div>
          <div>
            <div className="brand-name">TraceFlow AI</div>
            <div className="brand-sub">Northstar Data Systems</div>
          </div>
        </div>
        <nav>
          <button className={view === "overview" ? "nav-item active" : "nav-item"} onClick={() => setView("overview")}>Overview</button>
          <button className={view === "incidents" ? "nav-item active" : "nav-item"} onClick={() => { setView("incidents"); setSelectedIncident(null); }}>Incidents</button>
          <button className={view === "evaluation" ? "nav-item active" : "nav-item"} onClick={() => setView("evaluation")}>Evaluation</button>
        </nav>
      </aside>

      <main className="main">
        {error && <div className="banner banner-error">Could not reach backend API at {import.meta.env.VITE_API_URL || "http://localhost:8000"} — {error}</div>}

        {view === "overview" && <Overview pipelines={pipelines} runs={runs} incidents={incidents} />}
        {view === "incidents" && !selectedIncident && (
          <IncidentsList incidents={incidents} pipelines={pipelines} onSelect={setSelectedIncident} />
        )}
        {view === "incidents" && selectedIncident && (
          <IncidentDetail incidentId={selectedIncident} onBack={() => setSelectedIncident(null)} onChanged={loadAll} />
        )}
        {view === "evaluation" && <Evaluation />}
      </main>
    </div>
  );
}

function Overview({ pipelines, runs, incidents }: { pipelines: Pipeline[]; runs: PipelineRun[]; incidents: Incident[] }) {
  const openIncidents = incidents.filter((i) => i.status === "open").length;
  const failedRuns = runs.filter((r) => r.status === "failed").length;
  return (
    <div>
      <h1>Overview</h1>
      <div className="stat-grid">
        <div className="card stat"><div className="stat-value">{pipelines.length}</div><div className="stat-label">Pipelines</div></div>
        <div className="card stat"><div className="stat-value">{runs.length}</div><div className="stat-label">Tracked runs</div></div>
        <div className="card stat"><div className="stat-value">{failedRuns}</div><div className="stat-label">Failed runs</div></div>
        <div className="card stat"><div className="stat-value">{openIncidents}</div><div className="stat-label">Open incidents</div></div>
      </div>

      <h2>Pipelines</h2>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Name</th><th>Owner</th><th>Source</th><th>Target table</th></tr></thead>
          <tbody>
            {pipelines.map((p) => (
              <tr key={p.id}>
                <td className="mono">{p.name}</td>
                <td>{p.owner_team}</td>
                <td>{p.source_system}</td>
                <td className="mono">{p.target_table}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function IncidentsList({ incidents, pipelines, onSelect }: { incidents: Incident[]; pipelines: Pipeline[]; onSelect: (id: string) => void }) {
  const pipelineName = (id: string) => pipelines.find((p) => p.id === id)?.name ?? id;
  return (
    <div>
      <h1>Incidents</h1>
      <div className="table-wrap">
        <table>
          <thead><tr><th>ID</th><th>Title</th><th>Pipeline</th><th>Status</th><th>Severity</th><th>Confidence</th></tr></thead>
          <tbody>
            {incidents.map((inc) => (
              <tr key={inc.id} className="clickable" onClick={() => onSelect(inc.id)}>
                <td className="mono">{inc.id}</td>
                <td>{inc.title}</td>
                <td className="mono">{pipelineName(inc.pipeline_id)}</td>
                <td><StatusPill status={inc.status} /></td>
                <td><SeverityPill severity={inc.severity} /></td>
                <td>{inc.confidence !== null ? `${Math.round(inc.confidence * 100)}%` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function IncidentDetail({ incidentId, onBack, onChanged }: { incidentId: string; onBack: () => void; onChanged: () => void }) {
  const [incident, setIncident] = useState<Incident | null>(null);
  const [report, setReport] = useState<InvestigationReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [approving, setApproving] = useState(false);
  const [reviewer, setReviewer] = useState("");

  const load = async () => {
    const inc = await api.getIncident(incidentId);
    setIncident(inc);
  };

  useEffect(() => { load(); }, [incidentId]);

  const runInvestigation = async () => {
    setLoading(true);
    try {
      const r = await api.investigate(incidentId);
      setReport(r);
      await load();
    } finally {
      setLoading(false);
    }
  };

  const decide = async (decision: "approve" | "reject") => {
    if (!reviewer) return;
    setApproving(true);
    try {
      await api.approveRemediation(incidentId, reviewer, decision);
      await load();
      onChanged();
    } finally {
      setApproving(false);
    }
  };

  if (!incident) return <div>Loading…</div>;

  return (
    <div>
      <button className="link-back" onClick={onBack}>&larr; Back to incidents</button>
      <h1>{incident.title}</h1>
      <div className="meta-row">
        <span className="mono">{incident.id}</span>
        <StatusPill status={incident.status} />
        <SeverityPill severity={incident.severity} />
      </div>

      {!report && (
        <div className="card">
          <p>No investigation has been run for this incident yet.</p>
          <button className="btn-primary" onClick={runInvestigation} disabled={loading}>
            {loading ? "Investigating…" : "Run investigation"}
          </button>
        </div>
      )}

      {report && (
        <div className="investigation-flow">
          <FlowStep title="Failure">
            <p className="mono small">{incident.id} — triggering run: {incident.triggering_run_id}</p>
          </FlowStep>

          <FlowStep title={`Evidence (${report.evidence.length} items, ${report.tool_trace.length} tools)`}>
            <ul className="evidence-list">
              {report.evidence.map((e, idx) => (
                <li key={idx}><span className="tag">{e.source_tool}</span>{e.summary}</li>
              ))}
            </ul>
            <details>
              <summary>Tool execution trace</summary>
              <ul className="trace-list">
                {report.tool_trace.map((t, idx) => (
                  <li key={idx} className="mono small">{t.tool} — {t.duration_ms}ms — {t.ok ? "ok" : "error"}</li>
                ))}
              </ul>
            </details>
          </FlowStep>

          <FlowStep title="Root cause">
            <p>{report.root_cause}</p>
            {report.synthesis_method && <p className="small dim">synthesis: {report.synthesis_method}</p>}
          </FlowStep>

          <FlowStep title="Confidence">
            <div className="confidence-bar">
              <div className="confidence-fill" style={{ width: `${(report.confidence ?? 0) * 100}%` }} />
            </div>
            <p className="small">{Math.round((report.confidence ?? 0) * 100)}%</p>
          </FlowStep>

          <FlowStep title="Recommended remediation">
            <p>{report.remediation_description}</p>
          </FlowStep>

          <FlowStep title="Validation">
            <ul className="checklist">
              {report.validation_results.map((v, idx) => (
                <li key={idx} className={v.passed ? "check-pass" : "check-fail"}>
                  {v.passed ? "✓" : "✗"} {v.check_name} — <span className="dim">{v.details}</span>
                </li>
              ))}
            </ul>
          </FlowStep>

          <FlowStep title="Human approval">
            {incident.status === "resolved" ? (
              <p className="check-pass">✓ Remediation approved. Incident resolved.</p>
            ) : (
              <div className="approval-box">
                <input
                  placeholder="Your email (approver)"
                  value={reviewer}
                  onChange={(e) => setReviewer(e.target.value)}
                />
                <div className="approval-actions">
                  <button className="btn-primary" disabled={!reviewer || approving} onClick={() => decide("approve")}>Approve</button>
                  <button className="btn-secondary" disabled={!reviewer || approving} onClick={() => decide("reject")}>Reject</button>
                </div>
              </div>
            )}
          </FlowStep>
        </div>
      )}
    </div>
  );
}

function FlowStep({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flow-step">
      <div className="flow-step-title">{title}</div>
      <div className="flow-step-body">{children}</div>
    </div>
  );
}

function Evaluation() {
  const [report, setReport] = useState<EvaluationReport | null>(null);

  useEffect(() => { api.getEvaluations().then(setReport); }, []);

  if (!report) return <div>Loading…</div>;

  if (report.status === "pending") {
    return (
      <div>
        <h1>Evaluation</h1>
        <div className="card"><p>{report.message}</p></div>
      </div>
    );
  }

  return (
    <div>
      <h1>Evaluation</h1>
      <div className="stat-grid">
        <div className="card stat"><div className="stat-value">{report.incidents_evaluated}</div><div className="stat-label">Incidents evaluated</div></div>
        <div className="card stat"><div className="stat-value">{Math.round((report.root_cause_accuracy ?? 0) * 100)}%</div><div className="stat-label">Root-cause accuracy</div></div>
        <div className="card stat"><div className="stat-value">{report.avg_latency_ms}ms</div><div className="stat-label">Avg latency</div></div>
        <div className="card stat"><div className="stat-value">{report.avg_evidence_items_per_incident}</div><div className="stat-label">Avg evidence/incident</div></div>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Incident</th><th>Known label</th><th>Predicted</th><th>Confidence</th><th>Result</th></tr></thead>
          <tbody>
            {(report.results ?? []).map((r) => (
              <tr key={r.incident_id}>
                <td className="mono">{r.incident_id}</td>
                <td className="mono small">{r.known_label}</td>
                <td className="mono small">{r.top_candidate_key ?? "—"}</td>
                <td>{Math.round(r.confidence * 100)}%</td>
                <td className={r.correct ? "check-pass" : "check-fail"}>{r.correct ? "✓ correct" : "✗ miss"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="small dim">Generated by scripts/run_evaluation.py against seeded, labeled incidents. Not a claim about real-world production accuracy — see docs/evaluation.md.</p>
    </div>
  );
}

export default App;
