#!/usr/bin/env python3
"""Cairn — Claude Code reproducibility & re-work audit (self-contained, zero-dep).

Reads your own Claude Code session logs (~/.claude/projects/*/*.jsonl), pairs each
tool call with its result, and reports:
  - how much repeated tool work the agent did within sessions
  - how often a repeated call returned DIFFERENT output (non-reproducibility)
  - how many tokens the provably-redundant (identical) repeats cost

Everything runs locally. Nothing is uploaded.

Usage:
    python3 cc_repro_audit.py [--root ~/.claude/projects] [--price-input-per-m 3.0]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

BYTES_PER_TOKEN = 4

# Tools whose "same call" is inherently expected to change (not counted as non-repro).
VOLATILE_TOOLS = {"TodoWrite", "Task"}

# Strip obviously-volatile substrings before hashing output, so timestamps/durations
# don't masquerade as real non-reproducibility (mirrors the volatility probe).
_VOLATILE_PATTERNS = [
    re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.\d]*Z?"),  # ISO timestamps
    re.compile(r"\b\d+(\.\d+)?\s?(ms|s|sec|seconds|minutes|hours)\b"),  # durations
    re.compile(r"0x[0-9a-fA-F]{4,}"),  # hex addresses
    re.compile(r"\b[0-9a-f]{7,40}\b"),  # hashes / short shas
]


def approx_tokens(text: str) -> int:
    n = len(text.encode("utf-8", errors="replace"))
    return (n + BYTES_PER_TOKEN - 1) // BYTES_PER_TOKEN if n else 0


def canon_output(text: str) -> str:
    out = text
    for pat in _VOLATILE_PATTERNS:
        out = pat.sub("·", out)
    return out.strip()


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def work_key(tool: str, tool_input: dict) -> str:
    """A stable identity for 'the same piece of work'."""
    if not isinstance(tool_input, dict):
        return f"{tool}:{tool_input}"
    if tool == "Bash":
        return f"Bash:{str(tool_input.get('command','')).strip()}"
    if tool in ("Read", "Write", "Edit", "NotebookEdit"):
        return f"{tool}:{tool_input.get('file_path','')}"
    if tool == "Grep":
        return f"Grep:{tool_input.get('pattern','')}|{tool_input.get('path','')}|{tool_input.get('glob','')}"
    if tool == "Glob":
        return f"Glob:{tool_input.get('pattern','')}|{tool_input.get('path','')}"
    # generic: tool + sorted input
    return tool + ":" + json.dumps(tool_input, sort_keys=True, ensure_ascii=False)[:400]


def result_text(block: dict) -> str:
    c = block.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts = []
        for b in c:
            if isinstance(b, dict) and b.get("type") == "text":
                parts.append(b.get("text", ""))
            elif isinstance(b, str):
                parts.append(b)
        return "\n".join(parts)
    return "" if c is None else str(c)


def parse_session(path: Path):
    """Yield ordered events {tool, key, out_text, out_hash, is_error} for one session file."""
    pending = {}  # tool_use_id -> (tool, key)
    events = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return events
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = d.get("type")
        msg = d.get("message") or {}
        content = msg.get("content")
        if t == "assistant" and isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    pending[b.get("id")] = (b.get("name", "?"), b.get("input") or {})
        elif t == "user" and isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    tid = b.get("tool_use_id")
                    if tid not in pending:
                        continue
                    tool, tinput = pending.pop(tid)
                    txt = result_text(b)
                    fp = tinput.get("file_path") or tinput.get("path") if isinstance(tinput, dict) else None
                    events.append({
                        "tool": tool,
                        "key": work_key(tool, tinput),
                        "path": fp,
                        "out_text": txt,
                        "out_hash": sha(canon_output(txt)),
                        "is_error": bool(b.get("is_error")),
                    })
    return events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path.home() / ".claude" / "projects"))
    ap.add_argument("--price-input-per-m", type=float, default=3.0)
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of the report.")
    args = ap.parse_args()

    root = Path(args.root).expanduser()
    files = sorted(root.rglob("*.jsonl"))

    sessions = 0
    total_calls = 0
    repeats = 0
    repeat_tokens = 0
    identical = 0          # repeat, same output -> provably redundant
    changed = 0            # repeat, different output -> non-reproducible
    redundant_tokens = 0   # tokens in identical repeats (conservative "waste")
    by_tool = defaultdict(lambda: {"calls": 0, "repeats": 0, "changed": 0, "identical": 0, "redundant_tokens": 0})
    repeated_cmds = Counter()

    OBSERVE = {"Read", "Grep", "Glob", "Bash"}   # calls that observe state
    MUTATE = {"Edit", "Write", "NotebookEdit"}    # calls that change a file

    NOOP_CMDS = {"true", ":", "clear", "echo", "pwd"}
    no_ops = 0
    errors = 0
    thrash = Counter()   # file_path -> times touched (read/edit) across all sessions

    for f in files:
        events = parse_session(f)
        if not events:
            continue
        sessions += 1
        last = {}       # key -> out_hash
        last_seq = {}   # key -> event index at last observation
        file_mut = {}   # file_path -> latest event index it was mutated
        for i, ev in enumerate(events):
            total_calls += 1
            by_tool[ev["tool"]]["calls"] += 1
            k = ev["key"]
            path = ev.get("path")
            if ev["is_error"]:
                errors += 1
            if ev["tool"] == "Bash" and k[len("Bash:"):].strip() in NOOP_CMDS:
                no_ops += 1
            if path:
                thrash[path] += 1
            if ev["tool"] in MUTATE and path:
                file_mut[path] = i
            if k in last:
                repeats += 1
                toks = approx_tokens(ev["out_text"])
                repeat_tokens += toks
                by_tool[ev["tool"]]["repeats"] += 1
                repeated_cmds[k] += 1
                # skip volatile tools and any repeat whose target was mutated in between
                mutated_between = path is not None and file_mut.get(path, -1) >= last_seq.get(k, -1)
                if ev["tool"] in VOLATILE_TOOLS or ev["tool"] not in OBSERVE or mutated_between:
                    last[k] = ev["out_hash"]; last_seq[k] = i
                    continue
                if ev["out_text"].strip() and last[k]:
                    if ev["out_hash"] == last[k]:
                        identical += 1
                        redundant_tokens += toks
                        by_tool[ev["tool"]]["identical"] += 1
                        by_tool[ev["tool"]]["redundant_tokens"] += toks
                    else:
                        changed += 1
                        by_tool[ev["tool"]]["changed"] += 1
            last[k] = ev["out_hash"]; last_seq[k] = i

    decidable = identical + changed
    def pct(a, b): return (100.0 * a / b) if b else 0.0
    top_tool = max(by_tool.items(), key=lambda kv: kv[1]["calls"], default=("—", {"calls": 0}))
    top_cmd = repeated_cmds.most_common(1)[0] if repeated_cmds else (None, 0)
    top_file = max(((p, n) for p, n in thrash.items()), key=lambda x: x[1], default=(None, 0))

    if args.json:
        print(json.dumps({
            "sessions": sessions, "tool_calls": total_calls, "repeated_calls": repeats,
            "repeat_rate": pct(repeats, total_calls) / 100,
            "decidable_repeats": decidable, "non_reproducible": changed,
            "non_reproducible_rate": pct(changed, decidable) / 100,
            "redundant_identical": identical, "no_ops": no_ops, "errors": errors,
            "top_tool": top_tool[0], "most_repeated_command": top_cmd[0], "most_repeated_count": top_cmd[1],
            "most_touched_file": top_file[0], "most_touched_count": top_file[1],
        }, indent=2))
        return

    print("═" * 60)
    print("  YOUR AGENT'S GROUNDHOG DAY  ·  Groundhog for Claude Code")
    print("═" * 60)
    print(f"  {sessions:,} sessions   ·   {total_calls:,} tool calls   ·   {errors:,} errors")
    print(f"  Most-used tool: {top_tool[0]} ({top_tool[1]['calls']:,} calls)")
    print()
    print("  ── How much your agent repeated itself ──")
    print(f"  {repeats:,} calls ({pct(repeats,total_calls):.0f}%) redid work it had already done.")
    if top_file[0]:
        print(f"  Most re-touched file: {Path(top_file[0]).name}  ({top_file[1]}x)")
    if top_cmd[0] and top_cmd[0].startswith("Bash:"):
        print(f"  Most-repeated command: {top_cmd[0][5:][:44]}  ({top_cmd[1]}x)")
    if no_ops:
        print(f"  No-op commands (true/echo/pwd/…) run: {no_ops}x  🙃")
    print()
    print("  ── When it looked again, had the world moved? ──")
    print(f"  Of {decidable:,} re-observations with a clean before/after,")
    print(f"  {changed:,} ({pct(changed,decidable):.0f}%) came back DIFFERENT — the filesystem")
    print(f"  moved under the agent between look and look-again.")
    print(f"  ({identical:,} came back identical — provably redundant.)")
    print("═" * 60)
    print("  Read-only. Nothing left your machine. Token/cost figures omitted")
    print("  on purpose — for a solo dev the recoverable spend is ~nil; the")
    print("  interesting part is the behavior, not the pennies.")
    print("  The same engine on autonomous agent fleets tells a bigger story.")


if __name__ == "__main__":
    main()
