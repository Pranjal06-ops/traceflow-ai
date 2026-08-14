# 🔎 TraceFlow AI

## AI-Powered Data Pipeline Reliability & Root-Cause Investigation Platform

> **A data pipeline failed before the morning reporting deadline. TraceFlow helps an engineer figure out what actually broke, why it broke, what evidence supports that conclusion, and whether the proposed fix is safe to apply.**

[![CI](https://github.com/Pranjal06-ops/traceflow-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/Pranjal06-ops/traceflow-ai/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](#tech-stack)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)](#tech-stack)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agent_Orchestration-1C3C3C)](#tech-stack)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=111827)](#tech-stack)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](#tech-stack)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](#tech-stack)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](#tech-stack)
[![Tests](https://img.shields.io/badge/Tests-21_passing-success)](#testing)
[![License](https://img.shields.io/badge/license-MIT-yellow)](#license)

---

## 🚨 The Real-World Problem

Imagine a data engineering team responsible for a company's daily customer and sales reporting.

At 2:14 AM, the overnight ingestion pipeline fails.

The dashboard that finance expects at 7:00 AM will now contain stale data.

The error itself is not especially useful:

```text
TypeError:
invalid literal for int() with base 10: 'ENTERPRISE'
```

The engineer still has to answer:

- Did the source system change?
- When did the change begin?
- Was the schema different from yesterday?
- Did a recent deployment cause it?
- How much data is affected?
- Has this happened before?
- Is the downstream warehouse also impacted?
- What is the safest remediation?
- Can the proposed fix be validated before anyone touches production?

In a real environment, the evidence is fragmented across **logs, schemas, data-quality checks, databases, Git history, pipeline runs, and previous incidents**.

### That's the problem TraceFlow is designed to solve.

Instead of giving an engineer another chatbot, TraceFlow acts as an **AI-assisted incident investigator**.

---

## 🎯 The Product in One Sentence

**TraceFlow turns a vague pipeline failure into an evidence-backed incident investigation with a proposed, validated remediation — while keeping the final decision with a human.**

---

## 🔥 What Happens During an Investigation?

```mermaid
sequenceDiagram
    autonumber
    participant P as Pipeline
    participant T as TraceFlow
    participant E as Engineer

    P->>T: 02:14 — run fails (TypeError)
    T->>T: 02:15 — open incident, search relevant logs
    T->>T: 02:16 — compare current vs previous schema
    T->>T: 02:16 — check data-quality anomalies
    T->>T: 02:17 — inspect recent Git changes
    T->>T: 02:17 — search similar historical incidents
    T->>T: 02:18 — query warehouse run-history metadata
    T->>T: 02:18 — correlate evidence into candidate root causes
    T-->>E: 02:19 — root cause + confidence
    T-->>E: 02:19 — remediation proposal
    T->>T: 02:20 — run automated validation checks
    E->>T: 02:20 — review evidence
    E-->>T: APPROVE / REJECT
```

The goal isn't to replace the engineer.

**The goal is to reduce the time spent hunting through disconnected evidence.**

---

## 🧩 A Concrete Incident

### Incident: `customer_daily_ingestion`

At 02:14 AM:

```text
Pipeline status: FAILED

Error:
invalid literal for int() with base 10: 'ENTERPRISE'
```

A normal log viewer tells you **what failed**.

TraceFlow attempts to answer **why** — by correlating four independent evidence sources:

```mermaid
flowchart LR
    subgraph Schema
        S1["previous: customer_segment → INTEGER"]
        S2["current: customer_segment → VARCHAR"]
    end
    subgraph DQ["Data Quality"]
        D1["62% type-conformance failure"]
    end
    subgraph Git
        G1["commit: CRM export mapping modified, ~20h prior"]
    end
    subgraph History["Historical Incidents"]
        H1["similar schema transition previously broke\na downstream transformation"]
    end

    S1 --> R((Root-cause\nscoring engine))
    S2 --> R
    D1 --> R
    G1 --> R
    H1 --> R
    R --> C["schema_type_change::customer_segment\nconfidence 0.95"]
```

TraceFlow then produces an evidence-backed hypothesis:

```text
LIKELY ROOT CAUSE
Upstream CRM export changed the representation
of customer_segment from numeric codes to string labels.

CONFIDENCE
0.95

IMPACT
customer_daily_ingestion
↓
warehouse transformation
↓
customer reporting freshness
```

Then it proposes:

```text
REMEDIATION
Normalize customer_segment during ingestion
before warehouse insertion.
```

But TraceFlow does **not** execute that change automatically.

```mermaid
flowchart LR
    A[Recommendation] --> B[Automated validation]
    B --> C[Human review]
    C --> D{Decision}
    D -->|Approve| E[Incident resolved]
    D -->|Reject| F[Incident stays open]
```

That distinction is central to the project — see the live screenshot of exactly this flow in [Screenshots](#-screenshots-real-not-mockups) below.

---

## 🧠 Why This Is More Than an AI Demo

The interesting engineering challenge is not "can an LLM explain an error?"

It is:

> **Can an AI system combine imperfect operational evidence from multiple systems without inventing facts?**

TraceFlow therefore separates **evidence collection** from **AI reasoning**.

```mermaid
flowchart TD
    subgraph Deterministic["Deterministic systems establish the facts"]
        L[Logs]
        S[Schemas]
        Q[Data Quality]
        GT[Git]
        SQL[SQL]
        H[Pipeline History]
        HI[Historical Incidents]
    end

    L & S & Q & GT & SQL & H & HI --> EV["Structured Evidence\n(typed, tool-tagged)"]

    subgraph AIReasoning["AI handles the reasoning-heavy layer"]
        EV --> COR[Correlation / scoring]
        COR --> RC[Root-cause explanation]
        RC --> REM[Remediation recommendation]
        REM --> SUM[Incident summary]
    end
```

This architecture makes the project closer to a **reliability engineering tool** than a generic RAG application. The LLM never sees a raw database row — only the structured evidence the deterministic tools already collected — and it's never given tool-calling or write access. See [`docs/security.md`](docs/security.md) and [`docs/decisions.md`](docs/decisions.md) for the full reasoning.

---

## 🎯 Project at a Glance

| Capability | What TraceFlow does |
|---|---|
| Failure investigation | Finds relevant evidence around a failed run |
| Schema analysis | Detects changes between pipeline versions |
| Data-quality analysis | Surfaces abnormal values and type/conformance issues |
| Git investigation | Connects recent code/config changes to incidents |
| Historical context | Finds similar previous incidents |
| AI reasoning | Correlates evidence into a root-cause hypothesis |
| Remediation | Generates a proposed corrective action |
| Validation | Checks whether the proposed remediation passes available tests |
| Human control | Requires explicit approval before remediation |
| Auditability | Preserves investigation evidence and outcomes |

---

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
not hard-coded** (see the screenshot in the Screenshots section) — produces:

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

See [`docs/architecture.md`](docs/architecture.md) for the full diagram set.

## Architecture

```mermaid
flowchart LR
    subgraph Client
        FE[React + TS Dashboard]
    end

    subgraph API["FastAPI backend"]
        R[REST routes]
        G[LangGraph investigation workflow]
        E[Rule-based scoring engine]
        L[LLM synthesis - optional]
    end

    subgraph Data
        DB[(PostgreSQL / SQLite)]
    end

    FE -->|HTTP JSON| R
    R --> G
    G -->|reads| DB
    G --> E
    E --> L
    L -->|grounded evidence only| G
    G -->|writes report + remediation| DB
    R -->|GET evidence / evaluations| DB
```

**Investigation workflow (LangGraph state machine)** — a linear pipeline, not a branching agent (see "Why a linear graph?" in `docs/decisions.md`):

```mermaid
flowchart TD
    A[detect_failure] --> B[collect_logs]
    B --> C[analyze_schema]
    C --> D[analyze_data_quality]
    D --> E[inspect_git_changes]
    E --> F[query_database]
    F --> G[retrieve_historical_incidents]
    G --> H[synthesize_evidence]
    H --> I[identify_root_cause]
    I --> J[generate_remediation]
    J --> K[validate_remediation]
    K --> L[generate_incident_report]
    L --> M{Human approval}
    M -->|approve| N[Incident resolved]
    M -->|reject| O[Incident stays open]
```

Full diagram set (system, LangGraph state machine, ER diagram, sequence diagram of the flagship scenario): [`docs/architecture.md`](docs/architecture.md).

## Tech stack

| Layer | Tech |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic, SQLAlchemy |
| Orchestration | LangGraph (typed state, node tracing) |
| LLM | Anthropic API (evidence synthesis only; optional) |
| Database | PostgreSQL (docker-compose) / SQLite (local dev default) |
| Frontend | React 19, TypeScript, Vite |
| Testing | pytest (21 tests, backend) |
| DevOps | Docker, Docker Compose, GitHub Actions CI |

## Repository structure

```
traceflow-ai/
├── .github/workflows/       # CI: backend tests + frontend build on every push
├── backend/
│   ├── app/
│   │   ├── api/             # FastAPI routes
│   │   ├── agents/          # LangGraph workflow (graph.py)
│   │   ├── services/        # investigation_engine.py, llm_synthesis.py
│   │   ├── models/          # SQLAlchemy tables
│   │   ├── schemas/         # Pydantic request/response models
│   │   ├── tools/           # deterministic investigation tools
│   │   ├── db/              # session/engine setup
│   │   └── core/            # config
│   └── tests/               # 21 pytest tests
├── frontend/                 # React + TS + Vite dashboard
├── data/                     # local SQLite dev DB lives here (gitignored)
├── scripts/
│   ├── seed_data.py          # realistic Northstar Data Systems seed data
│   └── run_evaluation.py     # real evaluation harness, no fabricated numbers
├── docs/
│   ├── architecture.md
│   ├── evaluation.md
│   ├── security.md
│   ├── decisions.md
│   ├── github_setup.md
│   └── screenshots/           # real screenshots of the running app
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

> **Honesty note:** this project was built in a sandbox with no internet
> access to pull Docker base images, so `docker compose up --build` was
> not run end-to-end in that environment. The compose file follows
> standard, well-tested patterns (official `postgres:16-alpine` image,
> standard Python/Node Dockerfiles), and everything it orchestrates — the
> backend, the schema, the API — was verified working directly against
> both SQLite and, by design, against Postgres via the same SQLAlchemy
> code path. Please verify the Docker path on your machine before relying
> on it in a real deployment.

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
Both jobs run the exact same commands documented above — CI doesn't run
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
never shows a fabricated number. See the real evaluation screenshot below,
including the miss shown in red.

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
- A dedicated, standalone remediation-validation endpoint (today,
  validation runs automatically as part of `/investigate` rather than as
  a separately triggerable step).
- API auth/RBAC for any non-local deployment.

## 📸 Screenshots (real, not mockups)

All five images below are real captures of the app running locally
against the seeded demo data — not mockups or fabricated UI. Reproduce
every one of them by following [Setup](#setup) above.

**Overview dashboard** — pipelines, run counts, open incidents at a glance:

![Overview dashboard](docs/screenshots/01_overview.png)

**Incidents list** — open and resolved incidents across all five seeded pipelines:

![Incidents list](docs/screenshots/02_incidents_list.png)

**Before investigation** — an open incident with no report yet:

![Incident detail before investigation](docs/screenshots/03_incident_detail_pre.png)

**Full investigation flow** — the flagship scenario, captured live: failure → 8 evidence items from 7 tools → root cause (95% confidence) → recommended remediation → 3/3 validation checks passed → human approval gate:

![Full investigation flow](docs/screenshots/04_incident_investigation.png)

**Evaluation page** — the real 4/5 (80%) accuracy result, including the one honest miss shown in red rather than hidden:

![Evaluation results](docs/screenshots/05_evaluation.png)

## 🔌 API & System Surface

The backend exposes these investigation-oriented endpoints
(`backend/app/api/routes.py` — this list matches the code exactly):

```text
GET  /api/pipelines
GET  /api/pipelines/{id}
GET  /api/runs
GET  /api/incidents
GET  /api/incidents/{id}
POST /api/incidents/{id}/investigate         # runs the full LangGraph workflow,
                                              # including automated validation
GET  /api/incidents/{id}/evidence
GET  /api/incidents/{id}/remediations
POST /api/incidents/{id}/approve-remediation
GET  /api/evaluations
```

Note: automated remediation validation currently runs as part of
`/investigate` rather than as a separately callable step — see "Future
improvements" above for the standalone-endpoint idea.

Interactive API documentation is available through FastAPI/Swagger at:

```text
http://localhost:8000/docs
```

---

## 🧩 Skills Demonstrated

### AI / LLM Engineering
`LangGraph` · `LLM orchestration` · `evidence grounding` · `structured outputs` · `tool-based AI` · `human-in-the-loop AI` · `AI evaluation`

### Data Engineering
`SQL` · `ETL reliability` · `schema drift` · `data quality` · `pipeline history` · `incident analysis` · `relational data modeling`

### Backend Engineering
`Python` · `FastAPI` · `Pydantic` · `SQLAlchemy` · `REST APIs` · `service-oriented architecture`

### Frontend Engineering
`React` · `TypeScript` · `Vite` · `data-driven dashboards`

### DevOps / Infrastructure
`Docker` · `Docker Compose` · `PostgreSQL` · `GitHub Actions CI` · `environment configuration`

### Software Engineering
`pytest` · `stateful workflows` · `validation` · `security boundaries` · `technical documentation`

---

## 📌 Resume-Ready Project Entry

> **TraceFlow AI — AI-Powered Data Pipeline Reliability Platform**
>
> • Built a Python/FastAPI reliability platform using **LangGraph, PostgreSQL/SQLite, React, and TypeScript** to investigate failed data pipelines by correlating logs, schema changes, data-quality signals, Git changes, run history, and historical incidents.
>
> • Designed an **evidence-grounded AI workflow** separating deterministic investigation tools from optional LLM synthesis, with automated remediation validation and a mandatory human approval gate.
>
> • Developed **21 automated tests** and a **GitHub Actions CI pipeline**, covering schema drift, SQL safety, incident retrieval, validation logic, LangGraph state transitions, and investigation API workflows.
>
> • Evaluated the system against **5 labeled seeded incidents**, achieving **4/5 (80%) root-cause accuracy**, while documenting the current keyword-based classification limitation.

---

## 🎥 Recruiter Demo Flow

A strong 60–90 second demo should show the complete engineering loop rather than every screen:

```mermaid
flowchart LR
    A[1. Open failed\nincident] --> B[2. Trigger\ninvestigation]
    B --> C[3. Show collected\nevidence]
    C --> D[4. Show schema/Git/DQ\ncorrelation]
    D --> E[5. Show root cause\n+ confidence]
    E --> F[6. Show remediation\nrecommendation]
    F --> G[7. Show automated\nvalidation]
    G --> H[8. Show human\napproval gate]
```

The key story is:

> **Failure → Evidence → Diagnosis → Remediation → Validation → Human Control**

---

## 🧭 Engineering Principles

TraceFlow follows five principles:

**1. Evidence before explanation**
Collect operational facts before asking the model to explain them.

**2. Deterministic where possible**
Logs, schema checks, SQL validation, permissions, and remediation validation should not depend on an LLM when conventional software can perform them more reliably.

**3. AI where reasoning adds value**
Use the model for evidence synthesis and readable investigation output rather than treating it as an authoritative data source.

**4. Human control over consequential actions**
Recommendations can be generated automatically; remediation requires explicit approval.

**5. Honest engineering**
Document limitations, failed evaluation cases, unverified deployment paths, and missing production controls rather than hiding them.

---

## License

MIT — see [`LICENSE`](LICENSE).

---

## ⚠️ Portfolio Scope

TraceFlow AI is a portfolio/research project designed to demonstrate practical patterns for AI-assisted data reliability. It is **not a production incident-management system**. Before connecting it to real infrastructure, additional authentication, authorization, observability, validation, deployment hardening, and operational controls would be required.
