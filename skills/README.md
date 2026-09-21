# Strands Agent Skills (AgentSkills.io)

Each subdirectory is one skill. Directory name **must** match the `name` in `SKILL.md` frontmatter.

Loaded by `app/agent.py` via `strands.vended_plugins.skills.AgentSkills`.

| Skill | Used by |
|---|---|
| `tools-orchestrator` | Top-level multi-agent coordinator |
| `search-tools` | Search specialist |
| `pdf-tools` | PDF specialist |
| `office-tools` | Office specialist |
| `image-tools` | Image specialist |
| `media-tools` | Media specialist |
| `utility-tools` | Utility specialist |
| `ai-tools` | AI specialist |

The orchestrator loads the whole `skills/` folder. Specialists load their category skill plus `tools-orchestrator`.
