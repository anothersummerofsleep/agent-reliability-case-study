"""Model factory - vendor-neutral, behind LangChain's standard abstraction.

The thin Diagnosis call uses ``init_chat_model`` driven by the ``MODEL_ID`` env var
(default ``google_genai:gemini-3.8-flash``, the model Baseline v1 and the live experiments
were run against), so the provider is swappable without touching graph code. Imports are
lazy so the pure modules (contracts, policy, safety) can be imported and unit-tested
without the model providers installed or configured.
"""

from __future__ import annotations

import os
from typing import Any

DEFAULT_MODEL_ID = "google_genai:gemini-3.8-flash"


def make_chat_model(model_id: str | None = None, **kwargs: Any):
    """Return a LangChain chat model for ``MODEL_ID`` (or the given id).

    Raises at call time (not import time) if the provider/key is missing - live runs
    need credentials; offline tests inject a fake model instead.
    """
    from langchain.chat_models import init_chat_model

    mid = model_id or os.environ.get("MODEL_ID", DEFAULT_MODEL_ID)
    return init_chat_model(mid, **kwargs)
