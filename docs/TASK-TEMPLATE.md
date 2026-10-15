# Task template

The prompt format for giving an agent one task. Copy the block, fill in the `<…>` parts, and paste it into Claude Code. Keep each part short; the rules in [`CLAUDE.md`](../CLAUDE.md) and the task in [`ROADMAP.md`](ROADMAP.md) carry the detail.

```markdown
Context: Natalia, a personal AI news agent (~/projects/natalia). Read CLAUDE.md, docs/ROADMAP.md
and docs/STATUS.md first. <Anything since the last run: what was merged, keys added, results pasted.>

Branch: task/<id>-<short-name>, from origin/main. <Or: continue on task/<id>-<short-name>.>

Job: do task <id> (<title>) from docs/ROADMAP.md.
- <Step or detail, if the roadmap entry needs one>
- <...>

Decisions: <choices already made for this task, so the agent doesn't ask or swap them.
Leave out what ROADMAP.md's "Decisions already made" table already says.>

Limits: <task-specific limits on top of CLAUDE.md, e.g. "no Gemini calls", "at most 5 Gemini
calls", "read-only on the database", "don't touch the bot service">.
Install nothing, create no accounts, no sudo, spend no money.

Finish: commit and push the branch, update docs/STATUS.md (real output, ✅/❌), then stop and
list the 🧑 steps I need to do, with exact commands.
```

## Example

```markdown
Context: Natalia, a personal AI news agent (~/projects/natalia). Read CLAUDE.md, docs/ROADMAP.md
and docs/STATUS.md first. Task 0.2 is merged; nothing else has changed.

Branch: task/1.1-sources, from origin/main.

Job: do task 1.1 (Sources and feeds) from docs/ROADMAP.md.
- Include at least two Khmer-language feeds for the Cambodia topic, if any exist.

Decisions: paywalled sources stay as headline + excerpt + link only.

Limits: fetch each feed at most twice; no article scraping yet (that's 1.3); no Gemini calls.
Install nothing, create no accounts, no sudo, spend no money.

Finish: commit and push the branch, update docs/STATUS.md (real output, ✅/❌), then stop and
list the 🧑 steps I need to do, with exact commands.
```
