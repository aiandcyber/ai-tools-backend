#!/usr/bin/env bash
# Register task definition and create/update ECS service on the EXISTING
# ai-engineer-construction cluster (same VPC/roles/subnets/SG as construction BFF).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
CLUSTER="ai-engineer-construction"
SERVICE="ai-tools-backend"
FAMILY="ai-tools-backend"
REPO="ai-tools/backend"
TAG="${IMAGE_TAG:-latest}"
SECRET_NAME="ai-tools/backend"

SECRET_ARN="$(aws secretsmanager describe-secret --secret-id "$SECRET_NAME" --region "$REGION" --query ARN --output text)"
# ECS secrets valueFrom for JSON keys needs: arn:…:secret:name-XXXXXX:KEY::
# describe-secret ARN already includes the random suffix.
IMAGE="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO}:${TAG}"

TMP="$(mktemp)"
python3 - "$ROOT/task-definition.template.json" "$TMP" "$IMAGE" "$SECRET_ARN" <<'PY'
import json, sys
src, dst, image, secret_arn = sys.argv[1:5]
td = json.load(open(src))
for c in td["containerDefinitions"]:
    if c.get("image", "").endswith("PLACEHOLDER_TAG") or c.get("name") == "api":
        if c["name"] == "api":
            c["image"] = image
    for s in c.get("secrets") or []:
        s["valueFrom"] = s["valueFrom"].replace(
            "arn:aws:secretsmanager:us-east-1:639986415410:secret:REPLACE_SECRET_ARN_SUFFIX",
            secret_arn,
        )
json.dump(td, open(dst, "w"), indent=2)
print(dst)
PY

echo "Registering task definition with image ${IMAGE} ..."
TD_ARN="$(aws ecs register-task-definition \
  --cli-input-json "file://${TMP}" \
  --region "$REGION" \
  --query 'taskDefinition.taskDefinitionArn' \
  --output text)"
echo "Task definition: ${TD_ARN}"

# Same network as ai-engineer-construction-bff
SUBNETS="subnet-02215d0f860b77809,subnet-05366d54dc10f324e,subnet-0dbce84a0245f10cf,subnet-0ca0d120aff1ba583,subnet-0efd94c736a254fd6,subnet-0fa8f842712eefbce"
SG="sg-0ea13223146bd44a0"

if aws ecs describe-services --cluster "$CLUSTER" --services "$SERVICE" --region "$REGION" \
    --query 'services[0].status' --output text 2>/dev/null | grep -q ACTIVE; then
  aws ecs update-service \
    --cluster "$CLUSTER" \
    --service "$SERVICE" \
    --task-definition "$TD_ARN" \
    --force-new-deployment \
    --region "$REGION" \
    --query 'service.{name:serviceName,task:taskDefinition,desired:desiredCount}' \
    --output json
  echo "Updated service ${SERVICE}"
else
  aws ecs create-service \
    --cluster "$CLUSTER" \
    --service-name "$SERVICE" \
    --task-definition "$TD_ARN" \
    --desired-count 1 \
    --launch-type FARGATE \
    --platform-version LATEST \
    --network-configuration "awsvpcConfiguration={subnets=[${SUBNETS}],securityGroups=[${SG}],assignPublicIp=ENABLED}" \
    --deployment-configuration "maximumPercent=200,minimumHealthyPercent=0,deploymentCircuitBreaker={enable=true,rollback=true}" \
    --region "$REGION" \
    --query 'service.{name:serviceName,task:taskDefinition,desired:desiredCount}' \
    --output json
  echo "Created service ${SERVICE} on cluster ${CLUSTER}"
fi

rm -f "$TMP"
echo "Done. Ensure Cloudflare Tunnel hostname points at http://localhost:8000 in the task."
