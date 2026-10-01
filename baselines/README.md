# Baselines

Reproducible baseline artifacts produced by the evaluation harness
(`python -m agent_reliability.evaluate`). Each artifact answers one question precisely:

> What exactly did this baseline do, on what code, model, and dataset?

## Generating `baseline-v1.json`

```bash
cp .env.example .env       # GOOGLE_API_KEY, LANGSMITH_API_KEY, LANGSMITH_TRACING=true
uv run python -m agent_reliability.evaluate baselines/baseline-v1.json
```

This runs the real graph over the **E2E** cases, scores each dimension separately, prints a summary,
and writes the artifact. Commit the artifact on the same commit the implementation was frozen at.

## Artifact contents

- `timestamp`, `git_commit`, `model_id`, `retrieval_k`
- `dataset`: path, tier (E2E), case count, case ids
- `aggregate`: per-dimension pass rates + failing case ids, distractor-resistance, latency stats
  (deliberately **no composite score**)
- `cases`: per-case expected vs observed, retrieved ids, grounding result, contract validity, latency,
  and the local `trace_id`

## Safety

The artifact stores only the local `trace_id` (a UUID). It does **not** contain API keys, LangSmith
tokens, or sensitive run URLs. The LangSmith project name is configured via `LANGSMITH_PROJECT`.

## Fault-injection cases

ARC-19 (missing answer at terminal) and ARC-20 (provenance present but unrelated) are **UNIT**-tier.
They are controlled contract/validator tests (see `tests/`), intentionally injected rather than hoped
out of a live model, and are excluded from the baseline's model-performance metrics.
