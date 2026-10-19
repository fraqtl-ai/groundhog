#!/usr/bin/env python3
"""Groundhog for Codex — how your Codex agent actually behaved (local, read-only).

Reads ~/.codex/sessions/**/*.jsonl rollouts, pairs each tool call with its result,
and reports repeated work, non-reproducibility ("the world moved"), no-op planning
churn, and the files it thrashed. Nothing is uploaded. Zero-dep.

Usage: python3 codex_audit.py [--root ~/.codex/sessions] [--json]
"""
from __future__ import annotations
import argparse, hashlib, json, re
from collections import Counter, defaultdict
from pathlib import Path

_VOL = [re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.\d]*Z?"),
        re.compile(r"0x[0-9a-fA-F]{4,}"), re.compile(r"\b[0-9a-f]{12,40}\b"),
        re.compile(r"\b\d+(\.\d+)?\s?(ms|s|sec|seconds)\b")]
NOOP_TOOLS = {"update_plan"}                 # planning churn, not real work
OBSERVE = {"shell", "exec", "read", "web_search_call"}  # calls that observe state

def canon(s):
    for p in _VOL: s = p.sub("·", s)
    return re.sub(r"\s+", " ", s).strip()
def sha(s): return hashlib.sha256(canon(s).encode("utf-8", "replace")).hexdigest()

def cmd_of(name, args):
    """Readable work-key: the shell command, patched file, or query."""
    try: a = json.loads(args) if isinstance(args, str) else (args or {})
    except Exception: a = {}
    if isinstance(a, dict):
        c = a.get("command")
        if isinstance(c, list):  # ['bash','-lc','...'] -> the script
            return next((str(x) for x in reversed(c) if len(str(x)) > 3), " ".join(map(str, c)))
        if c: return str(c)
        for k in ("path", "file_path", "query"):
            if a.get(k): return str(a[k])
    s = args if isinstance(args, str) else json.dumps(a)
    return (name + ":" + s)[:200]

def parse_session(path):
    pend = {}  # call_id -> (tool, key)
    events = []
    try: lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception: return events
    for line in lines:
        line = line.strip()
        if not line: continue
        try: d = json.loads(line)
        except Exception: continue
        if d.get("type") != "response_item": continue
        p = d.get("payload", {}) or {}
        pt = p.get("type")
        if pt in ("function_call", "custom_tool_call"):
            name = p.get("name", "?")
            key = f"{name}:{cmd_of(name, p.get('arguments') or p.get('input'))}"
            pend[p.get("call_id")] = (name, key)
        elif pt == "web_search_call":
            q = (p.get("action") or {}).get("query", "")
            events.append({"tool": "web_search", "key": f"web_search:{q}", "out": q, "path": None})
        elif pt in ("function_call_output", "custom_tool_call_output"):
            cid = p.get("call_id")
            if cid not in pend: continue
            name, key = pend.pop(cid)
            out = p.get("output")
            out = out if isinstance(out, str) else json.dumps(out)
            path_m = re.search(r"/[\w./-]+\.\w+", key)
            events.append({"tool": name, "key": key, "out": out,
                           "path": path_m.group(0) if path_m else None})
    return events

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path.home() / ".codex" / "sessions"))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    files = sorted(Path(args.root).expanduser().rglob("*.jsonl"))

    sess = calls = repeats = ident = changed = noops = 0
    redundant_tok = 0
    by_tool = defaultdict(lambda: {"calls": 0, "repeats": 0, "changed": 0})
    repeated = Counter(); thrash = Counter()
    for f in files:
        ev = parse_session(f)
        if not ev: continue
        sess += 1
        last = {}; last_i = {}; file_mut = {}
        for i, e in enumerate(ev):
            calls += 1; by_tool[e["tool"]]["calls"] += 1
            if e["tool"] in NOOP_TOOLS: noops += 1
            if e["path"]: thrash[e["path"]] += 1
            if e["tool"] in ("apply_patch", "write"):
                if e["path"]: file_mut[e["path"]] = i
            k = e["key"]; h = sha(e["out"])
            if k in last:
                repeats += 1; by_tool[e["tool"]]["repeats"] += 1; repeated[k] += 1
                mutated = e["path"] and file_mut.get(e["path"], -1) >= last_i.get(k, -1)
                if e["tool"] in OBSERVE and not mutated and e["out"].strip() and last[k]:
                    if h == last[k]: ident += 1
                    else: changed += 1; by_tool[e["tool"]]["changed"] += 1
            last[k] = h; last_i[k] = i
    dec = ident + changed
    def pct(a, b): return 100 * a / b if b else 0
    top_cmd = repeated.most_common(1)[0] if repeated else (None, 0)
    top_file = thrash.most_common(1)[0] if thrash else (None, 0)

    if args.json:
        print(json.dumps({"sessions": sess, "tool_calls": calls, "repeats": repeats,
            "decidable": dec, "non_reproducible": changed, "non_repro_rate": pct(changed, dec)/100,
            "noops": noops, "top_cmd": top_cmd[0], "top_file": top_file[0]}, indent=2)); return

    print("═" * 60)
    print("  YOUR CODEX AGENT, IN HINDSIGHT  ·  Groundhog")
    print("═" * 60)
    print(f"  {sess:,} sessions   ·   {calls:,} tool calls")
    top = sorted(by_tool.items(), key=lambda kv: kv[1]['calls'], reverse=True)[:1]
    if top: print(f"  Most-used tool: {top[0][0]} ({top[0][1]['calls']:,} calls)")
    print("\n  ── How much it repeated itself ──")
    print(f"  {repeats:,} calls ({pct(repeats,calls):.0f}%) redid work already done.")
    if top_file[0]: print(f"  Most re-touched file: {Path(top_file[0]).name} ({top_file[1]}x)")
    if top_cmd[0]: print(f"  Most-repeated call: {top_cmd[0][:52]} ({top_cmd[1]}x)")
    if noops: print(f"  Planning-only (update_plan) churn: {noops}x")
    print("\n  ── When it looked again, had the world moved? ──")
    print(f"  Of {dec:,} re-observations with a clean before/after,")
    print(f"  {changed:,} ({pct(changed,dec):.0f}%) came back DIFFERENT.")
    print(f"  ({ident:,} identical — provably redundant.)")
    print("═" * 60)
    print("  Read-only. Nothing left your machine. Codex rollouts @ ~/.codex/sessions.")

if __name__ == "__main__": main()
