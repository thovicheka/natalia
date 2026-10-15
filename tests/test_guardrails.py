"""Checks that the agent guardrails in .claude/settings.json stay in place."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_DENY = [
    "Bash(sudo:*)",
    "Bash(git push origin main:*)",
    "Bash(git push --force:*)",
    "Bash(git push -f:*)",
    "Bash(git merge:*)",
    "Bash(rm -rf:*)",
    "Read(./.env)",
    "Read(**/.env)",
    "Bash(cat .env:*)",
    "Bash(prefect deployment run:*)",
    "Bash(*prefect deployment run*)",
]


def test_settings_deny_rules():
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text())
    deny = settings["permissions"]["deny"]
    missing = [rule for rule in REQUIRED_DENY if rule not in deny]
    assert not missing, f"missing deny rules: {missing}"


def test_env_is_git_ignored():
    lines = (ROOT / ".gitignore").read_text().splitlines()
    assert ".env" in lines
    assert ".venv" in lines


def test_only_llm_wrapper_imports_genai():
    offenders = []
    for path in (ROOT / "natalia").rglob("*.py"):
        text = path.read_text()
        if path.name != "llm.py" and ("google.genai" in text or "from google import genai" in text):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"only natalia/llm.py may import google-genai: {offenders}"
