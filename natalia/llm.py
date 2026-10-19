"""The one thin wrapper for every LLM call (task 1.7).

This is the only module allowed to import an LLM SDK (`anthropic`, `google-genai`; a test
enforces it). Everything else calls `generate()` here, so the provider can be swapped, tests can
use a fake, and every call's token use is logged in one place: one JSON line per request in
logs/llm-usage.jsonl (git-ignored) and the `natalia.llm` logger.

Two providers, picked by LLM_PROVIDER (environment or `.env`):
- `anthropic` (default): Claude Haiku 5.5, paid per token from prepaid credits, key
  ANTHROPIC_API_KEY.
- `gemini`: Gemini Flash on the free tier, key GEMINI_API_KEY. Blocked for this account
  (403 "project denied access", 2026-10-16); kept as an option.
Keys are never printed or logged. Never pass private data here (CLAUDE.md rule 10); news content
is fine. Chat (task 1.9b) sends the owner's own questions, which is the feature the owner asked
for; nothing else private (keys, `.env`, other people's data).

Limits: rate-limit errors (429) are retried after a short wait, a few times. `max_calls` caps the
requests one process may make, retries included, so a bug can't burn the day's quota.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
USAGE_LOG = ROOT / "logs" / "llm-usage.jsonl"
DEFAULT_PROVIDER = "anthropic"
# Pinned per provider, so a model change is a code change that shows up in review.
# gemini-2.5-flash answered "no longer available to new users" (404) on 2026-10-16;
# gemini-3.8-flash is the newest numbered Flash model the Gemini key lists.
MODELS = {"anthropic": "claude-haiku-5-5", "gemini": "gemini-3.8-flash"}
DEFAULT_MODEL = MODELS[DEFAULT_PROVIDER]
RETRIES = 3
RETRY_WAIT_S = 20.0  # when the error doesn't say how long to wait
MAX_RETRY_WAIT_S = 65.0

log = logging.getLogger("natalia.llm")


class LLMError(RuntimeError):
    """The request failed (after retries), or the call cap was reached."""


@dataclass
class Result:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    requests: int = 1  # requests sent, including retries
    stop_reason: str = ""  # why the model stopped (Claude: end_turn, max_tokens, …), if known


class Usage:
    """Requests and tokens of this process, with an optional cap on requests."""

    def __init__(self, max_calls: int | None = None):
        self.max_calls = max_calls
        self.requests = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.thinking_tokens = 0

    def check(self) -> None:
        if self.max_calls is not None and self.requests >= self.max_calls:
            raise LLMError(f"LLM call cap reached ({self.max_calls} requests)")

    def add(self, r: Result) -> None:
        self.input_tokens += r.input_tokens
        self.output_tokens += r.output_tokens
        self.thinking_tokens += r.thinking_tokens


usage = Usage()


def set_max_calls(n: int | None) -> None:
    """Cap the requests this process may still make (None: no cap)."""
    usage.max_calls = None if n is None else usage.requests + n


def provider() -> str:
    """The provider named by LLM_PROVIDER (environment or `.env`), default anthropic."""
    load_dotenv(ROOT / ".env", override=False)
    name = os.environ.get("LLM_PROVIDER", "").strip().lower() or DEFAULT_PROVIDER
    if name not in MODELS:
        raise LLMError(f"LLM_PROVIDER must be one of {', '.join(MODELS)}, not {name!r}")
    return name


def default_model() -> str:
    return MODELS[provider()]


class AnthropicClient:
    """Claude through the official `anthropic` SDK. Created lazily, so tests and imports never
    need the key. The SDK's own retries are off: `generate()` retries, and counts every request
    against the call cap."""

    def __init__(self):
        import anthropic

        load_dotenv(ROOT / ".env", override=False)
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not key:
            raise LLMError("ANTHROPIC_API_KEY is not set (environment or .env)")
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=key, max_retries=0, timeout=120.0)

    def generate(
        self, prompt, *, model, system, json_schema, temperature, max_output_tokens, thinking=True
    ):
        # `temperature` is not sent: Haiku 5.5 rejects any non-default sampling value (400).
        # Effort "low" keeps the adaptive thinking short: summaries don't need much.
        output_config: dict = {"effort": "low"}
        if json_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": strict_schema(json_schema)}
        kwargs = {}
        if system:
            kwargs["system"] = system
        if not thinking:
            # Haiku 5.5 has no thinking budget (budget_tokens answers 400); "disabled" is the only
            # hard limit, accepted at effort low to high. Chat uses it (task 1.9d): at "low",
            # one Khmer answer still thought 1,132 tokens and ran out of room for the reply.
            kwargs["thinking"] = {"type": "disabled"}
        a = self._anthropic
        try:
            resp = self._client.messages.create(
                model=model,
                max_tokens=max_output_tokens,
                messages=[{"role": "user", "content": prompt}],
                output_config=output_config,
                **kwargs,
            )
        except a.APIStatusError as e:
            wait = e.response.headers.get("retry-after")
            hint = f" (retry after {wait}s)" if wait else ""
            raise ProviderError(e.status_code, f"{e.message}{hint}") from None
        except a.APIConnectionError as e:
            raise ProviderError(None, f"connection error: {e}") from None
        if resp.stop_reason == "refusal":
            raise ProviderError(None, f"refused ({getattr(resp.stop_details, 'category', None)})")
        u = resp.usage
        details = getattr(u, "output_tokens_details", None)
        thinking = (getattr(details, "thinking_tokens", None) or 0) if details else 0
        return Result(
            text="".join(b.text for b in resp.content if b.type == "text"),
            model=resp.model or model,
            input_tokens=u.input_tokens or 0,
            output_tokens=max((u.output_tokens or 0) - thinking, 0),  # Claude counts thinking in
            thinking_tokens=thinking,  # output_tokens; split it out like Gemini does
            stop_reason=resp.stop_reason or "",
        )


def strict_schema(schema):
    """A copy of `schema` with `additionalProperties: false` on every object: Claude's
    structured outputs require it."""
    if isinstance(schema, dict):
        out = {k: strict_schema(v) for k, v in schema.items()}
        if out.get("type") == "object":
            out.setdefault("additionalProperties", False)
        return out
    if isinstance(schema, list):
        return [strict_schema(v) for v in schema]
    return schema


class GeminiClient:
    """The real provider. Created lazily, so tests and imports never need the key."""

    def __init__(self):
        from google import genai

        load_dotenv(ROOT / ".env", override=False)
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            raise LLMError("GEMINI_API_KEY is not set (environment or .env)")
        self._client = genai.Client(api_key=key)

    def generate(
        self, prompt, *, model, system, json_schema, temperature, max_output_tokens, thinking=True
    ):
        from google.genai import errors, types  # `thinking`: Gemini already thinks minimally

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            thinking_config=thinking_config(model, types),
        )
        if json_schema is not None:
            config.response_mime_type = "application/json"
            config.response_json_schema = json_schema
        try:
            resp = self._client.models.generate_content(model=model, contents=prompt, config=config)
        except errors.APIError as e:
            raise ProviderError(e.code, str(e)) from None
        meta = resp.usage_metadata
        return Result(
            text=resp.text or "",
            model=model,
            input_tokens=(meta.prompt_token_count or 0) if meta else 0,
            output_tokens=(meta.candidates_token_count or 0) if meta else 0,
            thinking_tokens=(meta.thoughts_token_count or 0) if meta else 0,
        )


def thinking_config(model: str, types):
    """As little "thinking" as the model allows: summaries don't need it, and it costs output
    tokens and time. Gemini 2.x takes a token budget (0 = off); Gemini 3+ takes a level."""
    if model.startswith("gemini-2"):
        return types.ThinkingConfig(thinking_budget=0)
    return types.ThinkingConfig(thinking_level="low")


class ProviderError(Exception):
    def __init__(self, code: int | None, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


_client = None


def _get_client():
    global _client
    if _client is None:
        _client = AnthropicClient() if provider() == "anthropic" else GeminiClient()
    return _client


def use_client(client) -> None:
    """Swap the provider (tests use a fake with the same `generate` signature)."""
    global _client
    _client = client


def _retry_wait(message: str) -> float:
    """The wait the error asks for ("retry in 23.5s" / "retryDelay": "23s"), capped."""
    m = re.search(r"retry(?:Delay)?\D{0,12}?(\d+(?:\.\d+)?)\s*s", message, re.I)
    wait = float(m.group(1)) + 1 if m else RETRY_WAIT_S
    return min(wait, MAX_RETRY_WAIT_S)


def _log_usage(purpose: str, r: Result | None, error: str = "") -> None:
    entry = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "purpose": purpose,
        "model": r.model if r else None,
        "input_tokens": r.input_tokens if r else 0,
        "output_tokens": r.output_tokens if r else 0,
        "thinking_tokens": r.thinking_tokens if r else 0,
        "error": error[:200],
    }
    log.info("llm %s", entry)
    try:
        USAGE_LOG.parent.mkdir(exist_ok=True)
        with USAGE_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass  # logging must never break a digest


def generate(
    prompt: str,
    *,
    system: str | None = None,
    json_schema: dict | None = None,
    model: str | None = None,
    temperature: float = 0.3,
    max_output_tokens: int = 4096,
    thinking: bool = True,
    purpose: str = "",
    sleep=time.sleep,
) -> Result:
    """Send `prompt` to the LLM and return its reply with token counts.

    `json_schema`: ask for JSON matching it (parse `Result.text` with json.loads). `purpose`
    names the call in the usage log. `model`: default, the provider's pinned model.
    `thinking=False` turns the model's thinking off, so all of `max_output_tokens` is left for
    the reply (Claude; Gemini ignores it). Retries
    rate-limit (429) and server (5xx, including Claude's 529 "overloaded") errors.
    """
    client = _get_client()
    model = model or default_model()
    total = Result(text="", model=model, requests=0)
    for attempt in range(RETRIES + 1):
        usage.check()
        usage.requests += 1
        total.requests += 1
        try:
            r = client.generate(
                prompt,
                model=model,
                system=system,
                json_schema=json_schema,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                thinking=thinking,
            )
        except ProviderError as e:
            _log_usage(purpose, None, f"{e.code}: {e.message}")
            retryable = e.code == 429 or (e.code or 0) >= 500
            if not retryable or attempt == RETRIES:
                raise LLMError(f"LLM request failed ({e.code}): {e.message[:300]}") from None
            sleep(_retry_wait(e.message))
            continue
        r.requests = total.requests
        usage.add(r)
        _log_usage(purpose, r)
        return r
    raise LLMError("unreachable")  # pragma: no cover


def main(argv: list[str] | None = None) -> int:
    """`python -m natalia.llm ping [--model M]`: one tiny request (a few dozen tokens) to check
    the key, the account's access and the model. Prints the reply and token counts, never the
    key. The provider comes from LLM_PROVIDER."""
    import argparse

    parser = argparse.ArgumentParser(description="Check the LLM: one tiny request.")
    parser.add_argument("command", choices=["ping"])
    parser.add_argument("--model", help="default: the provider's pinned model")
    args = parser.parse_args(argv)
    set_max_calls(1)
    try:
        model = args.model or default_model()
        # 64, not 20: a thinking model's thinking counts toward the cap, before the answer.
        r = generate(
            "Reply with the single word OK.", model=model, max_output_tokens=64, purpose="ping"
        )
    except LLMError as e:
        print(f"{args.model or 'ping'}: FAILED: {e}")
        return 1
    print(
        f"{model}: {r.text.strip()!r} ({r.input_tokens} in / {r.output_tokens} out / "
        f"{r.thinking_tokens} thinking tokens)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
