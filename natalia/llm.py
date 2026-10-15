"""The one thin wrapper for every LLM call.

This is the only module allowed to import the `google-genai` SDK. Everything else calls
`generate()` here, so the provider can be swapped later, tests can use a fake, and every
call's token use can be logged in one place.

Stub for task 0.2: no SDK, no network. Task 1.7 implements it (Gemini Flash on the free
tier, key `GEMINI_API_KEY` from `.env`, token logging, retry on rate limits).
Never pass private data here: the free tier may use prompts to improve Google's models.
"""


def generate(prompt: str) -> str:
    """Send `prompt` to the LLM and return its text reply. Not implemented until task 1.7."""
    raise NotImplementedError("natalia.llm.generate is implemented in task 1.7")
