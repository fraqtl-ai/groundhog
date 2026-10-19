# Groundhog for Codex — install (as a Codex skill)

Codex 0.117+ uses **skills** (custom prompts are deprecated). Install:

```
mkdir -p ~/.codex/skills/groundhog
curl -sL https://raw.githubusercontent.com/fraqtl-ai/groundhog/main/codex/skills/groundhog/SKILL.md     -o ~/.codex/skills/groundhog/SKILL.md
curl -sL https://raw.githubusercontent.com/fraqtl-ai/groundhog/main/codex/skills/groundhog/codex_audit.py -o ~/.codex/skills/groundhog/codex_audit.py
```

Restart Codex, then either run `/skills` (groundhog will be listed) or just ask:
**"run the groundhog skill"** / **"audit my Codex agent"**.

Read-only. Reads ~/.codex/sessions locally. Nothing uploaded.
