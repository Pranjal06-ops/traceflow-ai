# Design decisions

Short rationale for the choices most likely to come up in an interview.

## Why LangGraph for a linear workflow?

See `architecture.md`. Short version: the control flow doesn't currently
branch, so LangGraph isn't buying dynamic routing here - it's buying a
typed, inspectable state object and a natural place to add branching later
(e.g., "if confidence < 0.3, loop back and gather more evidence" or "if two
candidates are close, ask a clarifying tool"). Building a bespoke sequence
of function calls would work today; it wouldn't extend as cleanly.

## Why PostgreSQL as the target, SQLite as the dev default?

`DATABASE_URL` defaults to a local SQLite file so `git clone` -> `pip
install` -> run works with zero external services, which matters for
anyone (including a recruiter or interviewer) evaluating this quickly.
The schema and all queries are written against SQLAlchemy Core/ORM with no
SQLite-specific features, so switching to Postgres is a connection-string
change (see `docker-compose.yml`). Postgres is still the documented
production target because a real version of this system would need
concurrent writers and would likely add `pgvector` for semantic search
(see below) - both are a poor fit for SQLite.

## Why deterministic tools + LLM-for-prose, instead of one big LLM call?

Covered in `architecture.md` and `security.md`. The short version: an
LLM given raw logs/schemas/git history and asked "what's wrong?" can
produce a plausible-sounding but ungrounded answer, and a human reviewer
has no way to check its reasoning against the data. Here, the ranking is a
transparent weighted sum a reviewer can inspect line by line
(`investigation_engine.py`), and the LLM is only asked to phrase an
already-determined conclusion in readable language - with a fully
functional non-LLM fallback (`_template_fallback`) proving the system
doesn't secretly depend on the LLM to work.

## Why keyword/lexical historical-incident retrieval instead of pgvector?

With a demo corpus of a handful of resolved incidents, semantic embedding
search doesn't have enough data to meaningfully outperform lexical
overlap, but it does add real infrastructure cost (an embedding model
call, a vector index, versioning embeddings alongside schema changes).
The honest threshold for switching: once the historical incident corpus is
large enough that near-duplicate phrasing ("null spike" vs. "unexpected
NULL increase") starts causing real retrieval misses, embeddings earn
their cost. `historical_incident_tool` is intentionally isolated behind a
single function so that swap is a contained change.

## Why human approval is mandatory, not optional

The system is explicitly described everywhere (README, UI copy, this doc)
as requiring human sign-off before a remediation is considered actioned -
`RemediationProposal.status` cannot become `"approved"` except via the
approval endpoint, and no code path applies a remediation automatically.
This isn't a placeholder for a future "autonomous mode" - it's a
deliberate constraint appropriate for a system that touches production
data pipelines, and it's the reason the evaluation script measures
*root-cause accuracy*, not "remediations successfully auto-applied."

## Why a rule-based confidence score, capped below 1.0

`Candidate.score` is capped at 0.97 in `investigation_engine.py` -
the system is never allowed to claim absolute certainty, which matters
because confidence is shown directly to the human approver and should
never read as "don't bother checking this."

## What's explicitly out of scope for this MVP

- Multi-tenant auth/RBAC on the API (see `security.md`).
- Automatic re-running of failed remediations.
- Semantic/embedding-based log and incident search (see above).
- A learned (rather than rule-based) scoring model - there isn't enough
  labeled data at this scale to justify one, and a transparent rule set is
  easier for a human approver to trust.
