# 0002 - Model choice: vendor-neutral behind LangChain

## Context
The project demonstrates LangChain/LangGraph, not a single model vendor. Phase 0 needs one
thin Diagnosis call that is cheap, reliable for structured output, and traceable in LangSmith.

## Decision
Use LangChain's provider-agnostic `init_chat_model`, driven by a `MODEL_ID` env var, default
**`google_genai:gemini-2.0-flash`**. The model is created behind a factory (`model.make_chat_model`)
and injected into the Diagnosis node, so it is swappable and testable.

## Rationale
- **Low credential friction**: Google AI Studio needs a single API key (no Vertex/ADC project setup).
- **Cost**: a flash-tier model is cheap for development.
- **Structured output**: `with_structured_output(DiagnosisOutput)` is supported across providers.
- **Tracing**: traces flow through LangSmith like any LangChain model.
- **Swappable**: change `MODEL_ID` to `openai:gpt-4o-mini` or `anthropic:claude-3-5-haiku-latest`
  and set the matching key (install that provider extra). No graph code changes.

## Testing
Offline tests inject a fake `DiagnoseFn` returning a canned `DiagnosisOutput`, so the graph
smoke test needs no key and no network.
