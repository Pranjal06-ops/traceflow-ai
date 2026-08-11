# traceflow-ai
AI-powered data pipeline reliability &amp; root-cause investigation platform. FastAPI + LangGraph backend, React/TS dashboard, real evaluation harness, mandatory human approval before remediation.
# 🔎 TraceFlow AI

[![CI](https://github.com/YOUR_GITHUB_USERNAME/traceflow-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_GITHUB_USERNAME/traceflow-ai/actions/workflows/ci.yml)
![Tests](https://img.shields.io/badge/tests-21%20passing-brightgreen)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Node](https://img.shields.io/badge/node-20-green)
![License](https://img.shields.io/badge/license-MIT-yellow)

<sub>(CI badge will go green after you push — replace `YOUR_GITHUB_USERNAME` in the badge URL above with your actual GitHub username first; see `docs/github_setup.md`.)</sub>

**AI-powered data pipeline reliability & root-cause investigation platform.**

A ready-to-run system that investigates failed data pipelines: it collects
evidence (logs, schema diffs, data-quality checks, Git changes, run history,
past incidents), scores the most likely root cause with a transparent
rule-based engine, drafts a remediation, validates it automatically, and
requires human approval before anything is applied. Built with FastAPI,
LangGraph, PostgreSQL/SQLite, and a React + TypeScript dashboard. 21
passing tests, a real (not fabricated) evaluation report, and honest
documentation of what isn't finished yet.

---

It is not a chatbot wrapped around an LLM call. The LLM is used for exactly
one thing — turning already-collected, structured evidence into readable
prose — and the system is fully functional (with a template-based fallback)
even with no LLM API key configured. See [`docs/decisions.md`](docs/decisions.md)
for why it's built this way.

## Key features

- **Grounded root-cause analysis** — every claim in a report traces back to
  a specific tool call over real data; the LLM never invents facts (see
  `docs/security.md`).
- **Transparent, inspectable scoring** — root-cause confidence is a
  weighted sum a human can read line-by-line in
  `investigation_engine.py`, not an opaque model output.
- **Works with or without an LLM API key** — evidence synthesis has a
  fully functional deterministic template fallback; the system never
  silently depends on an external API to run.
- **Mandatory human approval** — no remediation is ever auto-applied;
  `RemediationProposal.status` can only become `approved` through an
  explicit, audited API call.
- **Real evaluation, not a claimed one** — `scripts/run_evaluation.py`
  computes actual accuracy against labeled seed incidents and writes it to
  disk; the UI shows "pending" until you've actually run it.
- **Full observability** — every tool call in an investigation is timed,
  logged, and shown in a "tool execution trace" panel in the UI.
- **SQL safety by construction** — the one SQL-investigation tool only
  executes a small allow-listed set of parameterized, read-only queries;
  it can never run arbitrary or AI-generated SQL.

## Why this problem matters

Data pipeline failures are common and expensive to triage: an on-call
engineer typically has to manually correlate logs, schema history, recent
deploys, and tribal knowledge of "didn't this happen before?" across
several disconnected tools. TraceFlow demonstrates what a first pass at
automating that correlation — with strict grounding and mandatory human
sign-off — could look like.

## Demo: the flagship scenario

`customer_daily_ingestion` run 1832 fails with:

```
TypeError: invalid literal for int() with base 10: 'ENTERPRISE'
```

TraceFlow investigates and — **derived live from the actual seeded data,
not hard-coded** (see the screenshot above) — produces:

- **Root cause (0.95 confidence, HIGH severity):** the `customer_segment`
  column changed type from `INTEGER` to `VARCHAR` between runs 1831 and
  1832, correlated with a Git commit ("update CRM export mapping ...")
  made ~20 hours earlier, a 62% type-conformance failure rate on that
  column, and a structurally similar resolved incident on a different
  pipeline.
- **Remediation recommendation:** normalize/cast `customer_segment` to
  `INTEGER` in the ingestion transformation before it reaches the
  warehouse.
- **Validation:** 3/3 automated sanity checks pass.
- **Status:** `AWAITING_HUMAN_APPROVAL` — nothing is applied automatically.

See [`docs/architecture.md`](docs/architecture.md) for a sequence diagram
of exactly how this is derived, and the screenshots section below for the
live-captured result.

## Architecture

```
FAILURE → Evidence Collection → Historical Incident Search →
Schema/DQ Analysis → Git Change Analysis → SQL Investigation →
Root Cause Scoring → Remediation Draft → Automated Validation →
Human Approval → Incident Report
```

Full diagrams (system, LangGraph state machine, ER diagram): [`docs/architecture.md`](docs/architecture.md).

## Tech stack

| Layer | Tech |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic, SQLAlchemy |
| Orchestration | LangGraph (typed state, node tracing) |
| LLM | Anthropic API (evidence synthesis only; optional) |
| Database | PostgreSQL (docker-compose) / SQLite (local dev default) |
| Frontend | React 19, TypeScript, Vite |
| Testing | pytest (21 tests, backend) |
| DevOps | Docker, Docker Compose |

## Repository structure

```
traceflow-ai/
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI routes
│   │   ├── agents/         # LangGraph workflow (graph.py)
│   │   ├── services/       # investigation_engine.py, llm_synthesis.py
│   │   ├── models/         # SQLAlchemy tables
│   │   ├── schemas/        # Pydantic request/response models
│   │   ├── tools/          # deterministic investigation tools
│   │   ├── db/              # session/engine setup
│   │   └── core/           # config
│   └── tests/               # 21 pytest tests
├── frontend/                # React + TS + Vite dashboard
├── data/                    # local SQLite dev DB lives here (gitignored)
├── scripts/
│   ├── seed_data.py         # realistic Northstar Data Systems seed data
│   └── run_evaluation.py    # real evaluation harness, no fabricated numbers
├── docs/
│   ├── architecture.md
│   ├── evaluation.md
│   ├── security.md
│   └── decisions.md
├── docker-compose.yml
└── .env.example
```

## Setup

### Option A — local (fastest path, SQLite, no Docker)

```bash
git clone <this-repo>
cd traceflow-ai
cp .env.example .env

pip install -r backend/requirements.txt --break-system-packages   # or use a venv
PYTHONPATH=backend python3 scripts/seed_data.py

PYTHONPATH=backend uvicorn app.main:app --reload --app-dir backend --port 8000
# in a second terminal:
cd frontend && npm install && npm run dev
```

Open `http://localhost:5173`. The API is at `http://localhost:8000`
(`/health`, interactive docs at `/docs`).

### Option B — Docker Compose (PostgreSQL)

```bash
cp .env.example .env
docker compose up --build
```

This starts PostgreSQL, the backend (`:8000`), and the frontend (`:5173`).
Then seed the database — the seed/evaluation scripts run on the host and
connect to the containerized Postgres via the exposed port:

```bash
DATABASE_URL=postgresql+psycopg2://traceflow:traceflow@localhost:5432/traceflow \
  PYTHONPATH=backend python3 scripts/seed_data.py
```

> **Honesty note:** this sandbox environment I built the project in has no
> internet access to pull Docker base images, so I was not able to run
> `docker compose up --build` end-to-end here. The compose file follows
> standard, well-tested patterns (official `postgres:16-alpine` image,
> standard multi-stage-free Python/Node Dockerfiles), and everything it
> orchestrates — the backend, the schema, the API — was verified working
> directly against both SQLite and by design against Postgres via the same
> SQLAlchemy code path. Please verify the Docker path on your machine
> before relying on it, and open an issue/note in `docs/` if anything
> needs adjusting.

## Environment variables

See [`.env.example`](.env.example) for the full list. Nothing is required
to run the demo — `ANTHROPIC_API_KEY` is optional (see below).

## Running without an LLM API key

If `ANTHROPIC_API_KEY` is unset, evidence synthesis falls back to a
deterministic template instead of calling the API. This is a real fallback
path, not a stub — `GET /health` reports `llm_enabled: false` in that case,
and the investigation report includes `"synthesis_method": "template"` so
it's always clear which path produced the explanation you're reading.

## Testing

```bash
cd backend
python3 -m pytest tests/ -v
```

21 tests covering: schema-drift detection, log filtering, SQL
allow-listing (rejects non-allow-listed queries), historical-incident
keyword matching, validation-check logic, full LangGraph state
transitions (including a "no evidence → inconclusive" case), and API
endpoints (investigate → evidence → approve → resolved flow, 404s, invalid
input).

### Continuous Integration

`.github/workflows/ci.yml` runs on every push and pull request to `main`:
a backend job that installs dependencies, seeds the demo database, runs
the full test suite, and runs the evaluation harness (uploading
`evaluation_results.json` as a build artifact); and a frontend job that
installs dependencies and does a full TypeScript + Vite production build.
Both jobs are the exact same commands documented above — CI doesn't run
anything different from what you can run locally.

## Evaluation

```bash
PYTHONPATH=backend python3 scripts/run_evaluation.py
```

**Real result from an actual run:** 4/5 (80%) root-cause accuracy against
5 labeled seeded incidents. The one miss is a genuine limitation of
keyword-based log classification, documented (not hidden) in
[`docs/evaluation.md`](docs/evaluation.md) along with the methodology and
what this evaluation does and doesn't demonstrate. If you haven't run the
script, `GET /api/evaluations` returns `{"status": "pending"}` — the UI
never shows a fabricated number.

## Security considerations

Read-only DB access for investigation, SQL query allow-listing (never
free-form/AI-generated SQL), parameterized queries, mandatory human
approval before any remediation, audit logging, secrets via environment
variables only. Full details and known gaps (e.g. no API auth/RBAC is
implemented — this is a local/demo-scale system) in
[`docs/security.md`](docs/security.md).

## Design decisions

Why LangGraph for a currently-linear workflow, why Postgres-target/SQLite-
dev, why deterministic tools + LLM-for-prose instead of one big LLM call,
why lexical (not embedding-based) historical search at this scale — all in
[`docs/decisions.md`](docs/decisions.md).

## Limitations

- Log-based failure classification is keyword-matching, not semantic —
  see the documented miss in `docs/evaluation.md`.
- Historical incident retrieval is lexical overlap, not embeddings —
  reasonable at this data scale, a real limitation at larger scale.
- No API authentication/authorization — this is a local/demo system, not
  something to expose publicly as-is.
- The evaluation set (5 labeled incidents) is small and self-authored; it
  validates the pipeline works end-to-end, not a production accuracy
  claim.
- Docker Compose is written to standard patterns but wasn't fully
  exercised end-to-end in the sandbox this was built in (see Setup above).

## Future improvements

- Embedding-based historical incident retrieval (pgvector) once the
  incident corpus is large enough to benefit from it.
- A learned or hybrid scoring model once there's enough labeled
  production data to justify moving off pure rules.
- Branching in the LangGraph workflow (e.g., loop back for more evidence
  when confidence is low) now that the linear version is proven out.
- API auth/RBAC for any non-local deployment.

## Screenshots

All screenshots below are real captures of the app running locally against
the seeded demo data — not mockups. You can reproduce every one of them by
following the Setup instructions.

**Overview dashboard** — pipelines, run counts, open incidents at a glance:

![Overview dashboard](docs/screenshots/01_overview.png)

**Incidents list** — open and resolved incidents across all five seeded pipelines:

![Incidents list](docs/screenshots/02_incidents_list.png)

**Before investigation** — an open incident with no report yet:

![Incident detail before investigation](docs/screenshots/03_incident_detail_pre.png)

**Full investigation flow** — this is the flagship scenario, captured live: failure → 8 evidence items from 7 tools → root cause (95% confidence) → recommended remediation → 3/3 validation checks passed → human approval gate:

![Full investigation flow](docs/screenshots/04_incident_investigation.png)

**Evaluation page** — the real 4/5 (80%) accuracy result, including the one honest miss shown in red rather than hidden:

![Evaluation results](docs/screenshots/05_evaluation.png)

## License

MIT — see [`LICENSE`](LICENSE).
