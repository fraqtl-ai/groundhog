# Groundhog — Your Agent's Groundhog Day

A tiny, local, read-only Claude Code plugin. Run one command and see how your
agent *actually* behaved across every session you've ever run — how often it
woke up and did the same thing again:

- how often it repeated work it already did,
- which file it re-touched the most,
- how many no-op commands it fired (`true`, `echo`, `pwd`…),
- and — the interesting one — how often, when it looked at something twice,
  **the world had moved underneath it.**

Everything runs on your machine. Nothing is uploaded. It never edits anything.

## Install

```
/plugin marketplace add fraqtl/groundhog
/plugin install groundhog@fraqtl
```

Then in any Claude Code session:

```
/groundhog:stats
```

## What it is (and isn't)

This is the friendly, single-developer front end to a bigger piece of work:
measuring **tool-call reproducibility** in coding agents. On one person's
interactive history there's almost no money to save — you're in the loop
correcting the agent constantly. The number that *is* interesting is how often
a repeated observation comes back different: on large **autonomous** agent runs
(no human in the loop) that rate is high, and it's why naively caching agent
tool-outputs is unsafe. Groundhog lets you see a small version of that on your
own history.

Read-only. Local. bytes/4 token proxy. No cost claims — on purpose.

Built by [fraQtl](https://github.com/fraqtl-ai).
