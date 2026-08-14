"""
Evaluation harness.

Runs the investigation graph against every incident in the DB that has a
`known_root_cause_label` (i.e. was seeded with a ground-truth answer for
evaluation purposes only - that label is never read by the investigation
engine itself). Compares the top-ranked candidate's `key` against the
label and reports real, computed metrics.

This script does not fabricate numbers: if you have not run it, there is
no evaluation report, and README.md says so explicitly.

Run with: python scripts/run_evaluation.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db.session import SessionLocal
from app.models.tables import Incident
from app.agents.graph import run_investigation

db = SessionLocal()

labeled = db.query(Incident).filter(Incident.known_root_cause_label.isnot(None)).all()

if not labeled:
    print("No labeled incidents found. Run scripts/seed_data.py first.")
    sys.exit(1)

results = []
correct = 0
total_latency_ms = 0.0

for incident in labeled:
    start = time.time()
    state = run_investigation(db, incident)
    latency_ms = (time.time() - start) * 1000
    total_latency_ms += latency_ms

    report = state["final_report"]
    candidates = state.get("candidates", [])
    top_key = candidates[0]["key"] if candidates else None

    # A candidate "matches" the label if the label's keyword class appears
    # in the top candidate's key (e.g. "upstream_timeout" in
    # "upstream_timeout", or "type_change" candidates matching the
    # "upstream_representation_change_type_mismatch" label).
    label = incident.known_root_cause_label
    is_match = bool(top_key) and (
        label in top_key
        or (label == "upstream_representation_change_type_mismatch" and "schema_type_change" in top_key)
    )
    correct += int(is_match)

    results.append({
        "incident_id": incident.id,
        "pipeline_id": incident.pipeline_id,
        "known_label": label,
        "top_candidate_key": top_key,
        "confidence": report["confidence"],
        "evidence_count": len(report["evidence"]),
        "tools_used": sorted({tr["tool"] for tr in report["tool_trace"]}),
        "latency_ms": round(latency_ms, 1),
        "correct": is_match,
    })

n = len(labeled)
accuracy = round(correct / n, 3)
avg_latency = round(total_latency_ms / n, 1)
avg_evidence = round(sum(r["evidence_count"] for r in results) / n, 1)

summary = {
    "incidents_evaluated": n,
    "root_cause_accuracy": accuracy,
    "avg_latency_ms": avg_latency,
    "avg_evidence_items_per_incident": avg_evidence,
    "results": results,
}

out_path = Path(__file__).resolve().parents[1] / "docs" / "evaluation_results.json"
out_path.write_text(json.dumps(summary, indent=2))

print(f"Evaluated {n} labeled incidents.")
print(f"Root-cause accuracy: {correct}/{n} = {accuracy}")
print(f"Avg latency: {avg_latency} ms | Avg evidence items: {avg_evidence}")
print(f"Full report written to {out_path}")

db.close()
