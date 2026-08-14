"""
Seeds the database with a realistic fictional company's pipeline history.

Company: Northstar Data Systems

Run with: python scripts/seed_data.py
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db.session import Base, engine, SessionLocal
from app.models.tables import (
    Pipeline, PipelineRun, PipelineLog, SchemaTable, SchemaVersion,
    DataQualityResult, GitChange, Incident,
)

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

db = SessionLocal()

NOW = datetime(2026, 8, 1, 6, 0, 0)


def add_pipeline(id_, name, owner, desc, source, target):
    p = Pipeline(id=id_, name=name, owner_team=owner, description=desc,
                 source_system=source, target_table=target)
    db.add(p)
    return p


pipelines = [
    add_pipeline("pl-customer-ingest", "customer_daily_ingestion", "Data Platform",
                 "Ingests daily customer records from the CRM export into the warehouse.",
                 "CRM Export API", "warehouse.dim_customer"),
    add_pipeline("pl-sales-load", "sales_warehouse_load", "Analytics Engineering",
                 "Loads daily sales transactions into the sales fact table.",
                 "Sales DB (Postgres)", "warehouse.fact_sales"),
    add_pipeline("pl-support-metrics", "support_metrics_pipeline", "Support Analytics",
                 "Aggregates support ticket metrics for the daily ops dashboard.",
                 "Zendesk-like Ticketing API", "warehouse.support_metrics"),
    add_pipeline("pl-product-usage", "product_usage_etl", "Product Analytics",
                 "Extracts product usage events and loads them into the usage fact table.",
                 "Event Stream (Kafka)", "warehouse.fact_usage"),
    add_pipeline("pl-finance-reporting", "finance_reporting_pipeline", "Finance Engineering",
                 "Builds the daily finance reporting rollups.",
                 "Finance ERP export", "warehouse.finance_rollup"),
]
db.flush()


def add_run(pipeline, run_number, status, offset_days, rows=50000, error=None):
    started = NOW - timedelta(days=offset_days)
    run = PipelineRun(
        id=f"{pipeline.id}-run-{run_number}", pipeline_id=pipeline.id, run_number=run_number,
        status=status, started_at=started, ended_at=started + timedelta(minutes=12),
        rows_processed=rows if status == "success" else None,
        error_summary=error,
    )
    db.add(run)
    return run


def add_log(run, level, message, minute_offset=0):
    db.add(PipelineLog(
        run_id=run.id, timestamp=run.started_at + timedelta(minutes=minute_offset),
        level=level, message=message,
    ))


# ---------------------------------------------------------------------
# FLAGSHIP SCENARIO: customer_daily_ingestion, run 1832 fails due to a
# schema change on customer_segment (INTEGER -> VARCHAR).
# ---------------------------------------------------------------------
cust = pipelines[0]

for i, run_num in enumerate(range(1820, 1832)):
    r = add_run(cust, run_num, "success", offset_days=(1832 - run_num) + 1)
    add_log(r, "INFO", f"Run {run_num} completed successfully. Rows processed: 50000.")

failed_run = add_run(
    cust, 1832, "failed", offset_days=0, rows=None,
    error="TypeError: invalid literal for int() with base 10: 'ENTERPRISE'",
)
add_log(failed_run, "INFO", "Starting ingestion for customer_daily_ingestion run 1832.")
add_log(failed_run, "INFO", "Fetched 50210 records from CRM Export API.")
add_log(failed_run, "ERROR",
        "TypeError: invalid literal for int() with base 10: 'ENTERPRISE' while casting customer_segment to INTEGER.",
        minute_offset=4)
add_log(failed_run, "ERROR", "Transformation step 'normalize_customer_segment' aborted. Run marked FAILED.",
        minute_offset=4)

# Schema history
schema_table = SchemaTable(id="schema-dim-customer", pipeline_id=cust.id, table_name="dim_customer")
db.add(schema_table)
db.flush()

base_columns = {
    "customer_id": "INTEGER", "customer_name": "VARCHAR", "customer_segment": "INTEGER",
    "signup_date": "DATE", "region": "VARCHAR",
}
changed_columns = dict(base_columns)
changed_columns["customer_segment"] = "VARCHAR"

db.add(SchemaVersion(
    schema_id=schema_table.id, effective_run_id="pl-customer-ingest-run-1820",
    columns=base_columns, recorded_at=NOW - timedelta(days=13),
))
db.add(SchemaVersion(
    schema_id=schema_table.id, effective_run_id=failed_run.id,
    columns=changed_columns, recorded_at=NOW,
))

# Data quality: null/type-error spike on customer_segment for the failed run
db.add(DataQualityResult(
    run_id=failed_run.id, check_name="type_conformance", column_name="customer_segment",
    metric_value=0.62, baseline_value=0.0, passed=False,
    details="62% of customer_segment values failed INTEGER cast (e.g. 'ENTERPRISE', 'SMB').",
))
db.add(DataQualityResult(
    run_id=failed_run.id, check_name="null_rate", column_name="customer_segment",
    metric_value=0.0, baseline_value=0.01, passed=True,
    details="Null rate unaffected; values are present but of the wrong type.",
))

# Git history: a commit on the CRM export mapping shortly before the failure
db.add(GitChange(
    id="gc-1", pipeline_id=cust.id, commit_sha="a1b2c3d4e5f60718293aabbccddeeff00112233",
    author="j.alvarez", committed_at=NOW - timedelta(hours=20),
    message="Update CRM export mapping: customer_segment now uses named tiers instead of codes",
    files_changed=["ingestion/crm_export_mapping.py", "config/customer_segment_map.yaml"],
    diff_summary=(
        "- SEGMENT_MAP = {1: 1, 2: 2, 3: 3}\n"
        "+ SEGMENT_MAP = {1: 'SMB', 2: 'MIDMARKET', 3: 'ENTERPRISE'}"
    ),
))
db.add(GitChange(
    id="gc-2", pipeline_id=cust.id, commit_sha="9f8e7d6c5b4a30201928374655463728190abcd",
    author="j.alvarez", committed_at=NOW - timedelta(days=6),
    message="Add retry logic for CRM export API pagination",
    files_changed=["ingestion/crm_client.py"],
    diff_summary="+ retry(max_attempts=3, backoff=2.0) added around paginated fetch calls",
))

# A resolved historical incident with the same underlying pattern
# (a different pipeline, different column, same class of failure:
# upstream representation change breaking a typed downstream transform)
db.add(Incident(
    id="INC-2025-0042", pipeline_id="pl-sales-load", triggering_run_id="pl-sales-load-run-1",
    title="sales_warehouse_load failure: region_code changed from INTEGER to VARCHAR",
    severity="HIGH", status="resolved", created_at=NOW - timedelta(days=140),
    root_cause=(
        "Upstream Sales DB changed region_code representation from numeric IDs to string codes; "
        "downstream transformation expected INTEGER."
    ),
    confidence=0.91,
    # Note: no known_root_cause_label here - this incident exists purely as
    # background retrieval context (it references a run that predates this
    # seed and isn't itself re-investigated). Only incidents with a real,
    # queryable triggering run are included in the evaluation set below.
))

# ---------------------------------------------------------------------
# Additional pipelines: other realistic failure types, with enough
# variety that the evaluation harness has more than one scenario.
# ---------------------------------------------------------------------
sales = pipelines[1]
for run_num in range(90, 100):
    r = add_run(sales, run_num, "success", offset_days=(100 - run_num) + 1)
    add_log(r, "INFO", f"Run {run_num} completed. Rows processed: 120000.")
sales_failed = add_run(sales, 100, "failed", offset_days=0, rows=None,
                        error="requests.exceptions.Timeout: upstream API timeout after 30s")
add_log(sales_failed, "ERROR", "requests.exceptions.Timeout: upstream API request timed out after 30s.",
        minute_offset=2)
db.add(Incident(
    id="INC-2026-0018", pipeline_id=sales.id, triggering_run_id=sales_failed.id,
    title="sales_warehouse_load run 100 failed: upstream API timeout",
    status="open", created_at=NOW,
    known_root_cause_label="upstream_timeout",
))

support = pipelines[2]
for run_num in range(40, 49):
    r = add_run(support, run_num, "success", offset_days=(49 - run_num) + 1)
    add_log(r, "INFO", f"Run {run_num} completed. Rows processed: 8000.")
support_failed = add_run(support, 49, "failed", offset_days=0, rows=None,
                          error="IntegrityError: duplicate key value violates unique constraint")
add_log(support_failed, "ERROR",
        "IntegrityError: duplicate key value violates unique constraint 'uq_ticket_id'.", minute_offset=3)
db.add(Incident(
    id="INC-2026-0019", pipeline_id=support.id, triggering_run_id=support_failed.id,
    title="support_metrics_pipeline run 49 failed: duplicate ticket records",
    status="open", created_at=NOW,
    known_root_cause_label="duplicate_records",
))

usage = pipelines[3]
for run_num in range(200, 210):
    r = add_run(usage, run_num, "success", offset_days=(210 - run_num) + 1)
    add_log(r, "INFO", f"Run {run_num} completed. Rows processed: 900000.")
usage_failed = add_run(usage, 210, "failed", offset_days=0, rows=None,
                        error="FileNotFoundError: expected partition dt=2026-08-01 not found")
add_log(usage_failed, "ERROR",
        "FileNotFoundError: expected partition dt=2026-08-01 not found in event stream sink.",
        minute_offset=1)
db.add(Incident(
    id="INC-2026-0020", pipeline_id=usage.id, triggering_run_id=usage_failed.id,
    title="product_usage_etl run 210 failed: missing partition",
    status="open", created_at=NOW,
    known_root_cause_label="missing_partition",
))

finance = pipelines[4]
for run_num in range(60, 69):
    r = add_run(finance, run_num, "success", offset_days=(69 - run_num) + 1)
    add_log(r, "INFO", f"Run {run_num} completed. Rows processed: 15000.")
finance_failed = add_run(finance, 69, "failed", offset_days=0, rows=None,
                          error="ValueError: malformed row: missing required field 'amount_cents'")
add_log(finance_failed, "ERROR",
        "ValueError: malformed row detected: missing required field 'amount_cents'.", minute_offset=2)
db.add(Incident(
    id="INC-2026-0021", pipeline_id=finance.id, triggering_run_id=finance_failed.id,
    title="finance_reporting_pipeline run 69 failed: malformed source rows",
    status="open", created_at=NOW,
    known_root_cause_label="malformed_source_data",
))

# The flagship incident itself (open, awaiting investigation)
db.add(Incident(
    id="INC-2026-0017", pipeline_id=cust.id, triggering_run_id=failed_run.id,
    title="customer_daily_ingestion run 1832 failed: customer_segment type mismatch",
    status="open", created_at=NOW,
    known_root_cause_label="upstream_representation_change_type_mismatch",
))

db.commit()
db.close()

print("Seed data loaded.")
print("Pipelines:", len(pipelines))
print("Flagship incident: INC-2026-0017 (pipeline: customer_daily_ingestion)")
print("Additional labeled incidents for evaluation: INC-2026-0018 .. INC-2026-0021")
