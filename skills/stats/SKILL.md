---
name: stats
description: Show how the user's own Claude Code agent behaves across all their past sessions — repeat rate, most-thrashed file, no-op commands, and how often re-observed state came back different. Invoke when the user asks to see their agent stats, "agent wrapped", session insights, or how much their agent repeats itself.
---

# Cairn — Your Agent, By The Numbers

The user wants to see how their own Claude Code agent has behaved across their session history. Run the bundled local analyzer and present the result.

## Steps

1. Run the analyzer with the Bash tool:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/cc_repro_audit.py"
   ```

   It reads `~/.claude/projects/*/*.jsonl` locally and prints a formatted report. Nothing is uploaded. It is strictly read-only.

2. Show the user the report output as-is (it is already formatted for reading).

3. Then add a short, friendly 2–3 line interpretation in your own words, covering:
   - their repeat rate and the single most-thrashed file or most-repeated command (the fun, screenshot-worthy detail),
   - the "did the world move?" number, explained plainly: a high % means the filesystem/environment changed between the agent's repeated observations — normal for live work, but it is exactly why blind caching of tool outputs is unsafe.

4. If the user wants the raw numbers for scripting, re-run with `--json`.

## Honesty rules (do not violate)

- Do NOT quote dollar or token "savings." For an individual developer the recoverable spend is effectively zero; the value here is behavioral insight, not cost recovery. Say so if asked.
- The "different output" number is filtered to exclude re-reads after the user's own edits, but it can still include changes driven by shell commands that wrote files. Frame it as "the world moved," not "the agent malfunctioned."
- This is a read-only audit. It never changes the user's files or settings.
