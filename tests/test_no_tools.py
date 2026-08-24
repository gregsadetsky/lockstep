"""The no-tools guarantee, mechanically enforced: every request the harness
sends is a bare chat completion. Not 'tools: false' — the tools field must
not EXIST, and neither may any other capability-granting field. The payload
key set is asserted EXACTLY, so a future edit that adds any new field breaks
this test and forces a conscious decision."""

from typing import Any

import httpx
import pytest

from lockstep import llm


class FakeResponse:
    status_code = 200

    def json(self) -> dict[str, Any]:
        return {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {},
        }


def test_openrouter_payload_is_bare_text_in_text_out(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url: str, headers: Any = None, json: Any = None, timeout: Any = None) -> Any:
        captured.update(json)
        return FakeResponse()

    def fail_get(*a: Any, **k: Any) -> Any:
        raise AssertionError("no network GETs during a chat call with a set cap")

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fail_get)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    llm.chat("some/model", "prompt", max_tokens=100)

    # exact key set: nothing that could grant tools, code execution, plugins,
    # functions, or any other capability may ever appear
    assert set(captured.keys()) == {"model", "messages", "max_tokens"}, captured.keys()
    for forbidden in ("tools", "tool_choice", "functions", "function_call", "plugins"):
        assert forbidden not in captured


def test_openrouter_payload_without_cap_is_still_bare(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url: str, headers: Any = None, json: Any = None, timeout: Any = None) -> Any:
        if url == llm.MODELS_URL:
            raise AssertionError("unexpected models fetch")
        captured.update(json)
        return FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    llm._model_max_cache["some/model"] = None  # cap unknown -> field omitted
    llm.chat("some/model", "prompt", max_tokens=None)
    assert set(captured.keys()) == {"model", "messages"}, captured.keys()
