import type {
  Pipeline, PipelineRun, Incident, EvidenceItem, InvestigationReport, EvaluationReport,
} from "../types";

const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json();
}

export const api = {
  listPipelines: () => request<Pipeline[]>("/api/pipelines"),
  listRuns: (pipelineId?: string) =>
    request<PipelineRun[]>(`/api/runs${pipelineId ? `?pipeline_id=${pipelineId}` : ""}`),
  listIncidents: () => request<Incident[]>("/api/incidents"),
  getIncident: (id: string) => request<Incident>(`/api/incidents/${id}`),
  investigate: (id: string) =>
    request<InvestigationReport>(`/api/incidents/${id}/investigate`, { method: "POST" }),
  getEvidence: (id: string) => request<EvidenceItem[]>(`/api/incidents/${id}/evidence`),
  approveRemediation: (id: string, approvedBy: string, decision: "approve" | "reject") =>
    request(`/api/incidents/${id}/approve-remediation`, {
      method: "POST",
      body: JSON.stringify({ approved_by: approvedBy, decision }),
    }),
  getEvaluations: () => request<EvaluationReport>("/api/evaluations"),
};
