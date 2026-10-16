"""Tests for the LLM wrapper (task 1.7), with a fake provider: no network, no key, no quota."""

import json

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
