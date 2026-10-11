# AWS deploy — reuse ai-engineer Fargate settings

This deploy kit mirrors the **working** `ai-engineer-construction` setup in account `639986415410` / `us-east-1`.

## What is reused (fast path)

| Resource | Value (from existing construction BFF) |
|---|---|
| ECS cluster | `ai-engineer-construction` |
| Launch type | Fargate |
| CPU / memory | 1024 / 2048 |
| Execution role | `ai-engineer-construction-ecs-execution-role` |
| Task role | `ai-engineer-construction-ecs-task-role` |
| Subnets | same 6 public subnets as construction BFF |
| Security group | `sg-0ea13223146bd44a0` |
| Sidecar | `cloudflare/cloudflared` + `TUNNEL_TOKEN` (same pattern) |

## What is new (Tools-specific)

| Resource | Name |
|---|---|
| ECR repo | `ai-tools/backend` |
| Secrets Manager | `ai-tools/backend` |
| Task family | `ai-tools-backend` |
| ECS service | `ai-tools-backend` |
| Log group | `/ecs/ai-tools-backend` |
| Cloudflare tunnel | **new** tunnel for Tools API host (do not reuse construction token) |

## Steps

### 1) Create ECR

```bash
cd /home/tar_a/ai-tools/backend
chmod +x deploy/*.sh
./deploy/01-create-ecr.sh
```

### 2) Fill secrets

```bash
cp deploy/secrets.example.json deploy/secrets.json
# edit deploy/secrets.json:
#   OPENROUTER_API_KEY
#   SEARXNG_URL   (reachable from the task; not 127.0.0.1 unless SearXNG is in the same task)
#   TUNNEL_TOKEN  (from Cloudflare Zero Trust → Tunnel for api.tools… or similar)
./deploy/03-upsert-secret.sh deploy/secrets.json
```

Grant the **execution role** permission to read `ai-tools/backend` if it does not already allow `secretsmanager:GetSecretValue` on `ai-tools/*` (construction secret policy may be name-scoped — check IAM if tasks fail to start).

### 3) Build & push image

```bash
./deploy/02-build-push.sh
# note IMAGE_TAG printed at the end, or:
export IMAGE_TAG=latest
```

Image build installs LibreOffice/Tesseract — expect **many minutes** the first time.

### 4) Register task + create/update service

```bash
export IMAGE_TAG=latest   # or the tag from step 3
./deploy/04-register-and-deploy.sh
```

### 5) Cloudflare

1. Create a tunnel (or named public hostname) to `http://localhost:8000` for the API (e.g. `api.tools.ai-forall.org`).
2. Put that tunnel’s token into `TUNNEL_TOKEN` in the secret; re-run `03-upsert-secret.sh` and force a new deployment.
3. On Cloudflare Pages for the frontend, set `VITE_API_BASE=https://api.tools.ai-forall.org` (or your chosen API host).

### 6) Verify

```bash
aws ecs describe-services --cluster ai-engineer-construction --services ai-tools-backend --region us-east-1 \
  --query 'services[0].{status:status,running:runningCount,desired:desiredCount,task:taskDefinition}'
curl -sS https://api.tools.ai-forall.org/api/health
```

## Notes

- Construction BFF currently has `desiredCount=0`; Tools service defaults to **1**.
- SearXNG is **not** in this image. Point `SEARXNG_URL` at a shared SearXNG reachable from Fargate (public URL, VPC service, or later a sidecar).
- Do not commit `deploy/secrets.json`.
