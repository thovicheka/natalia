"""Tests for the LLM wrapper (task 1.7), with a fake provider: no network, no key, no quota."""

import json
from types import SimpleNamespace as NS

import anthropic
import httpx2
import pytest

from natalia import llm


class FakeProvider:
    """Replies from a script: each entry is a Result to return or a ProviderError to raise."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def generate(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


@pytest.fixture(autouse=True)
def fresh(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "usage", llm.Usage())
    monkeypatch.setattr(llm, "USAGE_LOG", tmp_path / "usage.jsonl")
    yield
    llm.use_client(None)


def ok(text="hi", i=10, o=5):
    return llm.Result(text=text, model="fake", input_tokens=i, output_tokens=o)


def test_generate_returns_text_counts_tokens_and_logs():
    fake = FakeProvider(ok("hello", 12, 3))
    llm.use_client(fake)
    r = llm.generate("Say hello", system="Be brief", purpose="test")
    assert (r.text, r.input_tokens, r.output_tokens, r.requests) == ("hello", 12, 3, 1)
    assert fake.calls[0][1]["system"] == "Be brief"
    assert (llm.usage.requests, llm.usage.input_tokens) == (1, 12)
    entry = json.loads(llm.USAGE_LOG.read_text().splitlines()[0])
    assert entry["purpose"] == "test" and entry["input_tokens"] == 12 and not entry["error"]


def test_rate_limit_is_retried_after_the_wait_it_asks_for():
    err = llm.ProviderError(429, "RESOURCE_EXHAUSTED. Please retry in 7.5s.")
    fake = FakeProvider(err, ok())
    llm.use_client(fake)
    waits = []
    r = llm.generate("x", sleep=waits.append)
    assert r.requests == 2 and waits == [8.5]
    assert len(llm.USAGE_LOG.read_text().splitlines()) == 2  # the failed try is logged too


def test_retry_wait_is_capped_and_has_a_default():
    assert llm._retry_wait('"retryDelay": "300s"') == llm.MAX_RETRY_WAIT_S
    assert llm._retry_wait("quota exceeded") == llm.RETRY_WAIT_S


def test_client_errors_are_not_retried():
    llm.use_client(FakeProvider(llm.ProviderError(400, "API key not valid")))
    with pytest.raises(llm.LLMError, match="400"):
        llm.generate("x", sleep=lambda s: None)


def test_gives_up_after_the_retries():
    errs = [llm.ProviderError(503, "overloaded")] * (llm.RETRIES + 1)
    llm.use_client(FakeProvider(*errs))
    with pytest.raises(llm.LLMError, match="503"):
        llm.generate("x", sleep=lambda s: None)
    assert llm.usage.requests == llm.RETRIES + 1


def test_call_cap_counts_retries():
    llm.use_client(FakeProvider(llm.ProviderError(429, "slow down"), ok(), ok()))
    llm.set_max_calls(2)
    llm.generate("x", sleep=lambda s: None)  # 2 requests: the 429 and the retry
    with pytest.raises(llm.LLMError, match="cap reached"):
        llm.generate("y")


def test_missing_key_is_a_clear_error(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(llm, "ROOT", tmp_path)  # no .env there
    with pytest.raises(llm.LLMError, match="GEMINI_API_KEY is not set"):
        llm.GeminiClient()


def test_missing_anthropic_key_is_a_clear_error(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(llm, "ROOT", tmp_path)
    with pytest.raises(llm.LLMError, match="ANTHROPIC_API_KEY is not set"):
        llm.AnthropicClient()


@pytest.mark.parametrize(
    "value, provider, model",
    [
        (None, "anthropic", "claude-haiku-5-5"),
        ("", "anthropic", "claude-haiku-5-5"),
        ("Gemini", "gemini", "gemini-3.8-flash"),
    ],
)
def test_provider_is_picked_by_llm_provider(monkeypatch, tmp_path, value, provider, model):
    monkeypatch.setattr(llm, "ROOT", tmp_path)
    if value is None:
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
    else:
        monkeypatch.setenv("LLM_PROVIDER", value)
    assert (llm.provider(), llm.default_model()) == (provider, model)


def test_unknown_provider_is_a_clear_error(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "ROOT", tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    with pytest.raises(llm.LLMError, match="LLM_PROVIDER must be one of"):
        llm.provider()


def test_generate_uses_the_providers_model_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "ROOT", tmp_path)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    fake = FakeProvider(ok())
    llm.use_client(fake)
    llm.generate("x")
    assert fake.calls[0][1]["model"] == "claude-haiku-5-5"


def test_strict_schema_closes_every_object():
    schema = {
        "type": "object",
        "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {}}}},
    }
    out = llm.strict_schema(schema)
    assert out["additionalProperties"] is False
    assert out["properties"]["items"]["items"]["additionalProperties"] is False
    assert "additionalProperties" not in schema  # the caller's schema is not changed


# --- the Anthropic backend, against a fake SDK client (no network, no key) -----------------


class FakeMessages:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.kwargs = reply, error, None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.reply


def anthropic_backend(messages):
    backend = llm.AnthropicClient.__new__(llm.AnthropicClient)  # skip __init__: no key needed
    backend._anthropic = anthropic
    backend._client = NS(messages=messages)
    return backend


def claude_reply(text, stop_reason="end_turn", thinking=7):
    return NS(
        content=[NS(type="thinking", thinking=""), NS(type="text", text=text)],
        model="claude-haiku-5-5",
        stop_reason=stop_reason,
        stop_details=NS(category="general_harms") if stop_reason == "refusal" else None,
        usage=NS(
            input_tokens=40,
            output_tokens=12 + thinking,
            output_tokens_details=NS(thinking_tokens=thinking),
        ),
    )


def test_anthropic_request_shape_and_result():
    msgs = FakeMessages(claude_reply('{"items": []}'))
    r = anthropic_backend(msgs).generate(
        "news",
        model="claude-haiku-5-5",
        system="Be brief",
        json_schema={"type": "object", "properties": {}},
        temperature=0.3,
        max_output_tokens=100,
    )
    kw = msgs.kwargs
    assert kw["model"] == "claude-haiku-5-5" and kw["max_tokens"] == 100
    assert kw["system"] == "Be brief"
    assert kw["messages"] == [{"role": "user", "content": "news"}]
    assert "temperature" not in kw  # Haiku 5.5 answers 400 to non-default sampling values
    assert kw["output_config"]["effort"] == "low"
    fmt = kw["output_config"]["format"]
    assert fmt["type"] == "json_schema" and fmt["schema"]["additionalProperties"] is False
    assert r.text == '{"items": []}'
    assert (r.input_tokens, r.output_tokens, r.thinking_tokens) == (40, 12, 7)
    assert r.stop_reason == "end_turn"


def test_anthropic_without_schema_or_system_sends_neither():
    msgs = FakeMessages(claude_reply("OK"))
    anthropic_backend(msgs).generate(
        "x", model="m", system=None, json_schema=None, temperature=0.3, max_output_tokens=64
    )
    assert "system" not in msgs.kwargs and "format" not in msgs.kwargs["output_config"]
    assert "thinking" not in msgs.kwargs  # adaptive, the model's default


def test_anthropic_thinking_off_is_sent_as_disabled_at_low_effort():
    msgs = FakeMessages(claude_reply("OK", thinking=0))
    r = anthropic_backend(msgs).generate(
        "x",
        model="m",
        system=None,
        json_schema=None,
        temperature=0.3,
        max_output_tokens=64,
        thinking=False,
    )
    assert msgs.kwargs["thinking"] == {"type": "disabled"}
    assert msgs.kwargs["output_config"]["effort"] == "low"  # "disabled" 400s at xhigh/max
    assert r.thinking_tokens == 0


def test_generate_passes_thinking_to_the_client():
    fake = FakeProvider(llm.Result(text="ok", model="m"), llm.Result(text="ok", model="m"))
    llm.use_client(fake)
    llm.generate("p", thinking=False)
    llm.generate("p")
    assert [kw["thinking"] for _, kw in fake.calls] == [False, True]


def test_anthropic_errors_become_provider_errors():
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx2.Response(429, headers={"retry-after": "7"}, request=req)
    err = anthropic.RateLimitError("rate limited", response=resp, body=None)
    with pytest.raises(llm.ProviderError) as e:
        anthropic_backend(FakeMessages(error=err)).generate(
            "x", model="m", system=None, json_schema=None, temperature=0.3, max_output_tokens=64
        )
    assert e.value.code == 429 and llm._retry_wait(e.value.message) == 8.0


def test_anthropic_refusal_is_an_error():
    msgs = FakeMessages(claude_reply("", stop_reason="refusal"))
    with pytest.raises(llm.ProviderError, match="refused"):
        anthropic_backend(msgs).generate(
            "x", model="m", system=None, json_schema=None, temperature=0.3, max_output_tokens=64
        )
