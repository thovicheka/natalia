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
    # Gaps found by the live check in task 0.4 (each one ran before these rules existed).
    "Bash(*sh -c *sudo*)",
    "Bash(git push* main)",
    "Bash(git push* main *)",
    "Bash(git push*:main*)",
    "Bash(git push*refs/heads/main*)",
    "Bash(git push* --force*)",
    "Bash(git push* +*)",
    "Bash(git clean*)",
    "Bash(rm -fr*)",
    "Bash(rm -r*)",
    "Read(~/**/.env)",
    "Edit(**/.env)",
    "Bash(*python*'.env*)",
    'Bash(*python*".env*)',
    "Edit(~/projects/cloud-ai-lab/**)",
    "Edit(~/projects/lab-runtime/**)",
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
