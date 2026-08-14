# Architecture

## System overview

TraceFlow AI investigates failed data pipeline runs. Given a triggering
`PipelineRun` in `failed` status, it collects structured evidence from
several deterministic sources, scores candidate root causes with a
transparent rule-based engine, uses an LLM only to turn that evidence into
readable prose, and produces an incident report that requires human
approval before any remediation is considered "done."

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

## Investigation workflow (LangGraph state machine)

This is a linear pipeline, not a branching agent — see "Why a linear
graph?" in `decisions.md`. Every node is implemented in
`backend/app/agents/graph.py`.

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

Each node reads/writes a single `IncidentState` TypedDict. Nodes that call
tools also append to `tool_trace` (tool name, duration, success) for
observability — this is what powers the "Tool execution trace" panel in
the UI and the `tool_trace` field in every investigation report.

## Flagship demo scenario

```mermaid
sequenceDiagram
    participant U as CRM Export API
    participant P as customer_daily_ingestion (run 1832)
    participant T as TraceFlow

    U->>P: customer_segment now sent as 'ENTERPRISE'/'SMB' strings
    P->>P: cast to INTEGER fails
    P-->>T: run marked FAILED (TypeError)
    T->>T: schema_diff_tool: customer_segment INTEGER -> VARCHAR
    T->>T: git_change_tool: commit updating CRM export mapping, 20h prior
    T->>T: data_quality_tool: 62% type_conformance failures on customer_segment
    T->>T: historical_incident_tool: similar past incident on a different pipeline
    T->>T: score candidates, top = schema_type_change::customer_segment (0.95)
    T-->>U: incident report, AWAITING_HUMAN_APPROVAL
```

## Data model

11 tables, implemented in `backend/app/models/tables.py`:

```mermaid
erDiagram
    PIPELINES ||--o{ PIPELINE_RUNS : has
    PIPELINE_RUNS ||--o{ PIPELINE_LOGS : has
    PIPELINES ||--o{ SCHEMAS : tracks
    SCHEMAS ||--o{ SCHEMA_VERSIONS : versions
    PIPELINE_RUNS ||--o{ DATA_QUALITY_RESULTS : produces
    PIPELINES ||--o{ GIT_CHANGES : has
    PIPELINES ||--o{ INCIDENTS : triggers
    INCIDENTS ||--o{ INCIDENT_EVIDENCE : has
    INCIDENTS ||--o{ REMEDIATION_PROPOSALS : has
    REMEDIATION_PROPOSALS ||--o{ VALIDATION_RESULTS : has
```

## Why LangGraph?

The workflow is a fixed sequence of evidence-gathering steps followed by
one synthesis step - there's no branching or looping in the current
scope. LangGraph is used here specifically for its typed state object and
built-in node tracing/visualization, which map directly onto the
"evidence -> root cause -> remediation -> validation" story the UI needs
to tell. A hand-rolled sequence of function calls would work equally well
functionally; LangGraph buys clearer structure for a reviewer and a
natural extension point if branching (e.g. re-running a node on low
confidence) is added later.

## Why deterministic tools + a rule-based scorer, not "ask the LLM"?

Handing raw DB rows to an LLM and asking "what's the root cause?" is fast
to build and easy to get wrong: the model can invent plausible-sounding
facts that aren't in the data, and there is no way to audit *why* it
reached a conclusion. Here, every fact the LLM sees was computed by a
tested, deterministic function first, and the root-cause ranking itself is
a transparent weighted score a human reviewer can read at a glance.
The LLM's only job is prose.

See `security.md` and `decisions.md` for more on this boundary.
