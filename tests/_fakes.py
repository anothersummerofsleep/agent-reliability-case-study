"""Tiny fake chat model for offline tests of the structured LLM steps.

Mimics the LangChain surface the nodes use: ``model.with_structured_output(Schema)``
returns something with ``.invoke(messages)``. The fake returns a preset result, or
raises a preset exception to exercise the fail-closed paths.
"""

from __future__ import annotations


class _FakeStructured:
    def __init__(self, result):
        self._result = result

    def invoke(self, messages):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class FakeModel:
    """A fake chat model whose structured output is fixed ahead of time."""

    def __init__(self, result):
        self._result = result

    def with_structured_output(self, schema):
        return _FakeStructured(self._result)
