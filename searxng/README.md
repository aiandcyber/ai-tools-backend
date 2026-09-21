# Shared SearXNG config (reference)

This directory is **configuration for a separate SearXNG deployment**, not code that runs inside the AI Tools API container.

- Local today: often mounted from another path into the `searxng` Docker container  
- Production: one shared SearXNG service; set `SEARXNG_URL` on every consumer (`ai-tools-backend`, later `realtime-ai`, etc.)  
- Later: move this folder into a dedicated `ai-forall-infra` repo if preferred  
