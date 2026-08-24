"""LLM backends. openrouter for everything, plus a direct anthropic path
(model slug prefix "direct/") for fable-5 via an org account with a cyber exception.

Token caps: ALWAYS the model's provider maximum. max_tokens=None resolves to
the per-model max from openrouter's /models listing (or 128k for the direct
anthropic path).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx

URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS_URL = "https://openrouter.ai/api/v1/models"
ATTEMPTS = 3
FABLE_MAX_OUTPUT = 128_000  # per claude-api docs: fable-5 max output tokens

_model_max_cache: dict[str, int | None] = {}


@dataclass(frozen=True)
class Reply:
    content: str
    usage: dict[str, object]
    refusal: str | None
    finish: str | None
    reasoning: str | None
    gen_id: str | None = None  # provider-side generation id (third-party receipt)


def model_max_tokens(model: str) -> int | None:
    """The real output ceiling for a model, from openrouter (cached).

    Some providers report max_completion_tokens equal to the full context
    window (e.g. 1,048,576) — that is a context bound, not an output bound,
    and sending it as max_tokens 400s because input + output must fit in
    context. So the cap is clamped to context_length minus 16k of input
    headroom (our prompts are ~3k tokens)."""
    if not _model_max_cache:
        key = os.environ["OPENROUTER_API_KEY"]
        resp = httpx.get(MODELS_URL, headers={"Authorization": f"Bearer {key}"}, timeout=60)
        resp.raise_for_status()
        for m in resp.json()["data"]:
            mc = (m.get("top_provider") or {}).get("max_completion_tokens")
            ctx = m.get("context_length")
            cap = mc
            if ctx is not None:
                bound = ctx - 16_384
                cap = bound if cap is None else min(cap, bound)
            _model_max_cache[m["id"]] = cap
    return _model_max_cache.get(model)


def _chat_direct_anthropic(model: str, prompt: str, timeout: float) -> Reply:
    """Direct anthropic api (fable-5 via the cyber-exception org). thinking is
    always on for fable; display=summarized so we can store the summary as
    reasoning. NO fallbacks parameter — a fallback model answering in fable's
    place would corrupt the eval; a refusal must be recorded as a refusal."""
    import anthropic

    client = anthropic.Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY_FOR_FABLE_WITH_CYBER_EXCEPTION"],
        timeout=timeout,
        max_retries=2,
    )
    with client.messages.stream(
        model=model,
        max_tokens=FABLE_MAX_OUTPUT,
        thinking={"type": "adaptive", "display": "summarized"},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        msg = stream.get_final_message()
    content = "".join(b.text for b in msg.content if b.type == "text")
    reasoning = "\n".join(
        b.thinking for b in msg.content if b.type == "thinking" and b.thinking
    ) or None
    refusal = None
    if msg.stop_reason == "refusal":
        details = getattr(msg, "stop_details", None)
        refusal = (
            f"category={getattr(details, 'category', None)}: "
            f"{getattr(details, 'explanation', '')}"
            if details
            else "refusal (no stop_details)"
        )
    finish = {"max_tokens": "length", "end_turn": "stop"}.get(
        msg.stop_reason or "", msg.stop_reason
    )
    usage: dict[str, object] = {
        "prompt_tokens": msg.usage.input_tokens,
        "completion_tokens": msg.usage.output_tokens,
        "backend": "anthropic-direct",
    }
    return Reply(content=content, usage=usage, refusal=refusal, finish=finish,
                 reasoning=reasoning, gen_id=msg.id)


def chat(
    model: str, prompt: str, max_tokens: int | None = None, timeout: float = 3600.0
) -> Reply:
    last_err: Exception | None = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            if model.startswith("direct/"):
                return _chat_direct_anthropic(model.removeprefix("direct/"), prompt, timeout)
            key = os.environ["OPENROUTER_API_KEY"]
            payload: dict[str, object] = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
            }
            cap = max_tokens if max_tokens is not None else model_max_tokens(model)
            if cap is not None:
                payload["max_tokens"] = cap
            resp = httpx.post(
                URL, headers={"Authorization": f"Bearer {key}"}, json=payload, timeout=timeout
            )
            data = resp.json()
            if resp.status_code != 200 or "error" in data:
                raise RuntimeError(f"{model}: http {resp.status_code}: {data.get('error', data)}")
            choice = data["choices"][0]
            return Reply(
                content=choice["message"]["content"] or "",
                usage=data.get("usage", {}),
                refusal=choice["message"].get("refusal"),
                finish=choice.get("finish_reason"),
                reasoning=choice["message"].get("reasoning"),
                gen_id=data.get("id"),
            )
        except Exception as err:  # noqa: BLE001 - retry everything, surface last
            last_err = err
            if attempt < ATTEMPTS:
                time.sleep(10 * attempt)
    raise RuntimeError(f"{model}: failed after {ATTEMPTS} attempts: {last_err}")
