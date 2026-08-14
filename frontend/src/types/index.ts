export interface Pipeline {
  id: string;
  name: string;
  owner_team: string;
  description: string;
  source_system: string;
  target_table: string;
}

export interface PipelineRun {
  id: string;
  pipeline_id: string;
  run_number: number;
  status: string;
  started_at: string;
  ended_at: string | null;
  rows_processed: number | null;
  error_summary: string | null;
}

export interface Incident {
  id: string;
  pipeline_id: string;
  triggering_run_id: string;
  title: string;
  severity: string | null;
  status: string;
  created_at: string;
  root_cause: string | null;
  confidence: number | null;
}

export interface EvidenceItem {
  source_tool: string;
  summary: string;
  weight: number;
}

export interface ValidationCheck {
  check_name: string;
  passed: boolean;
  details: string | null;
}

export interface ToolTrace {
  tool: string;
  duration_ms: number;
  ok: boolean;
  timestamp: string;
}

export interface InvestigationReport {
  incident_id: string;
  pipeline_id: string;
  severity: string | null;
  root_cause: string | null;
  confidence: number | null;
  evidence: EvidenceItem[];
  remediation_description: string | null;
  validation_results: ValidationCheck[];
  status: string;
  tool_trace: ToolTrace[];
  synthesis_method: string | null;
}

export interface EvaluationResult {
  incident_id: string;
  pipeline_id: string;
  known_label: string;
  top_candidate_key: string | null;
  confidence: number;
  evidence_count: number;
  tools_used: string[];
  latency_ms: number;
  correct: boolean;
}

export interface EvaluationReport {
  status: "pending" | "complete";
  message?: string;
  incidents_evaluated?: number;
  root_cause_accuracy?: number;
  avg_latency_ms?: number;
  avg_evidence_items_per_incident?: number;
  results?: EvaluationResult[];
}
