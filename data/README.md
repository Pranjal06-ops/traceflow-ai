# data/

The demo dataset for TraceFlow AI ("Northstar Data Systems") is generated
programmatically by `scripts/seed_data.py` rather than checked in as static
fixture files — this keeps the seed data and the schema it depends on
(`backend/app/models/tables.py`) from drifting apart.

- `traceflow.db` (gitignored) — the local SQLite dev database, created here
  when you run `python scripts/seed_data.py` with the default `DATABASE_URL`.
- `sample_logs/`, `sample_pipeline_runs/`, `sample_schemas/`,
  `sample_incidents/`, `seed_data/` — placeholders kept for anyone who wants
  to extend the seeding approach to read from static fixture files (e.g. to
  add a new pipeline/incident without touching Python). Currently empty;
  `scripts/seed_data.py` is the source of truth for demo data.

To regenerate the dataset (this drops and recreates all tables):

```bash
PYTHONPATH=backend python3 scripts/seed_data.py
```
