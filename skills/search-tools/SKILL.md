---
name: search-tools
description: Search people and topics with regional priority via SearXNG and /api/search. Use for names, topics, news-oriented queries.
---

# Search tools

## When to use

- User asks to find a person, company contact footprint, or a topic on the web.
- User wants news-style or multi-source results with regional priority.

## How to run

Call `run_search_tool` with:

- `tool_id`: `web_search`
- `options_json` example:
  `{"query":"Amirtharaj thankaraj","mode":"person","region":"SG","language":"en","interests":"","industry":"","location":""}`

### Modes

- `person` — people-oriented query expansion (profiles, news, social categories)
- `topic` — topic/news/it/science expansion
- `auto` — infer person vs topic from the query

### Regions

`SG`, `IN`, `MY`, `US`, `GB`, `AU`, `GLOBAL` (default `SG`)

## Limitations (TODO)

Official LinkedIn / Meta / X / Google API keys are not wired yet. SearXNG may miss social profiles and can hit CAPTCHA. Tell the user when engines are unavailable; do not invent LinkedIn URLs.
