# Evaluation

## Methodology

`scripts/run_evaluation.py` runs the real investigation graph
(`run_investigation`, the same code path used by the API) against every
seeded incident that carries a `known_root_cause_label`. That label is
**only** read by the evaluation script itself - the investigation engine
never sees it. The script compares the top-ranked candidate's internal
`key` against the label and writes the results to
`docs/evaluation_results.json`.

If this script has never been run, `GET /api/evaluations` returns
`{"status": "pending", ...}` and the UI shows that message verbatim. No
placeholder numbers are ever fabricated or hard-coded.

## Results (from an actual run against the seeded demo data)

```
Evaluated 5 labeled incidents.
Root-cause accuracy: 4/5 = 0.8
Avg latency: ~18-28 ms per investigation (rule-based scoring; LLM disabled in this run)
Avg evidence items per incident: 4.2
```

Full machine-readable results: `docs/evaluation_results.json` (regenerate
with `python scripts/run_evaluation.py`).

### The one miss, explained

`INC-2026-0020` (`product_usage_etl`, expected label `missing_partition`)
was **not** correctly classified — the engine produced no confident
candidate at all. The underlying log message is:

> `FileNotFoundError: expected partition dt=2026-08-01 not found in event stream sink.`

The rule-based log-keyword matcher in `investigation_engine.py` looks for
the literal phrase `"missing partition"`, which doesn't appear in this
message (it says "not found," not "missing"). This is a real, honest
limitation of keyword-based log classification, not a bug that was fixed
by tuning the test — see "Known limitations" below.

## What this evaluation does and does not show

**Does show:** on this seeded, 5-incident, single-company demo dataset,
covering 5 distinct known failure classes, the deterministic scoring
engine correctly identifies the root-cause category in 4 of 5 cases, and
the flagship scenario (schema type change) is identified with high
confidence (0.95) using every evidence source described in the README.

**Does not show:** anything about accuracy on real production data, at
scale, or across failure types not represented in this seed set. Five
labeled examples is enough to sanity-check the scoring logic and to be
transparent about a real weakness — it is not a benchmark, and this
document does not claim otherwise.

## Known limitations of the current scoring approach

1. **Log classification is keyword-based**, not semantic. It will miss
   paraphrases of known failure patterns (as shown above). A more robust
   version would use a small classifier or embedding similarity over log
   messages instead of literal substring matching.
2. **Candidate generation is rule-based and hand-written per evidence
   type.** Adding a genuinely new failure category (beyond the ~9 types
   seeded here) requires adding a new rule, not just more data.
3. **Historical incident retrieval is lexical overlap**, not semantic
   search (see `docs/decisions.md` for why pgvector wasn't used at this
   scale). This means it will miss historically similar incidents that
   are described with different words.
4. **The evaluation set is small and self-authored.** It was built to
   exercise the pipeline end-to-end and catch obvious regressions, not to
   serve as a statistically meaningful accuracy benchmark.

## Re-running the evaluation

```bash
cd traceflow-ai
python scripts/seed_data.py        # fresh seed data
python scripts/run_evaluation.py   # writes docs/evaluation_results.json
```
