---
name: groundhog
description: Audit how this Codex agent has actually behaved across its sessions — repeat rate, non-reproducibility ("did the world move?"), no-op planning churn, and the most-thrashed file. Read-only and local. Use when the user asks to run groundhog, audit their Codex agent, or see their agent's reliability/behavior stats.
---

# Groundhog — your Codex agent, in hindsight

Run the bundled local analyzer and present the result. Read-only; nothing is uploaded.

## Steps
1. Run: `python3 ~/.codex/skills/groundhog/codex_audit.py`
   (reads ~/.codex/sessions/**/*.jsonl locally and prints a formatted report)
2. Show the report output as-is.
3. Add a short, friendly 2–3 line read:
   - the repeat rate + the most screenshot-worthy detail (most-thrashed file, most-repeated call, or update_plan churn);
   - the "did the world move?" number, explained plainly: a high % means the environment changed between the agent's repeated observations — normal for live work, but exactly why blindly caching agent tool-outputs is unsafe.

## Honesty rules
- Read-only audit. No dollar/token "savings" claims — the value is behavioral insight.
- The "different output" number can include legitimate state change; frame it as "the world moved," not "the agent malfunctioned."
