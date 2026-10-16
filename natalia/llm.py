"""The one thin wrapper for every LLM call (task 1.7).

This is the only module allowed to import the `google-genai` SDK (a test enforces it). Everything
else calls `generate()` here, so the provider can be swapped later, tests can use a fake, and
every call's token use is logged in one place: one JSON line per request in logs/llm-usage.jsonl
(git-ignored) and the `natalia.llm` logger.

Gemini Flash on the free tier, key GEMINI_API_KEY from the environment or `.env` (never printed
or logged). The free tier may use prompts and responses to improve Google's models: never pass
private data here (CLAUDE.md rule 10). News content is fine.

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
# gemini-2.5-flash answered "no longer available to new users" (404) on 2026-10-16; this is the
# newest numbered Flash model the key lists. Pinned (not the moving "gemini-flash-latest" alias),
# so a model change is a code change that shows up in review.
DEFAULT_MODEL = "gemini-3.8-flash"
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


class GeminiClient:
    """The real provider. Created lazily, so tests and imports never need the key."""

    def __init__(self):
        from google import genai

        load_dotenv(ROOT / ".env", override=False)
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            raise LLMError("GEMINI_API_KEY is not set (environment or .env)")
        self._client = genai.Client(api_key=key)

    def generate(self, prompt, *, model, system, json_schema, temperature, max_output_tokens):
        from google.genai import errors, types

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
        _client = GeminiClient()
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
    model: str = DEFAULT_MODEL,
    temperature: float = 0.3,
    max_output_tokens: int = 4096,
    purpose: str = "",
    sleep=time.sleep,
) -> Result:
    """Send `prompt` to the LLM and return its reply with token counts.

    `json_schema`: ask for JSON matching it (parse `Result.text` with json.loads). `purpose`
    names the call in the usage log. Retries rate-limit (429) and server (5xx) errors.
    """
    client = _get_client()
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
    """`python -m natalia.llm ping [--model M]`: one tiny request (~10 tokens) to check the key,
    the project's access and the model. Prints the reply and token counts, never the key."""
    import argparse

    parser = argparse.ArgumentParser(description="Check the LLM: one tiny request.")
    parser.add_argument("command", choices=["ping"])
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args(argv)
    set_max_calls(1)
    try:
        r = generate(
            "Reply with the single word OK.", model=args.model, max_output_tokens=20, purpose="ping"
        )
    except LLMError as e:
        print(f"{args.model}: FAILED: {e}")
        return 1
    print(f"{args.model}: {r.text.strip()!r} ({r.input_tokens} in / {r.output_tokens} out tokens)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
