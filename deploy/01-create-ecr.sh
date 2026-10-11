#!/usr/bin/env bash
# Create ECR repository for AI Tools backend (reuse same AWS account/region as ai-engineer).
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
REPO="ai-tools/backend"

aws ecr describe-repositories --repository-names "$REPO" --region "$REGION" >/dev/null 2>&1 \
  || aws ecr create-repository \
       --repository-name "$REPO" \
       --region "$REGION" \
       --image-scanning-configuration scanOnPush=true \
       --encryption-configuration encryptionType=AES256

echo "ECR ready: ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO}"
