#!/usr/bin/env bash
# Build and push AI Tools backend image to ECR (same pattern as ai-engineer-construction/bff).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
REPO="ai-tools/backend"
TAG="${IMAGE_TAG:-$(date +%Y%m%d-%H%M)}"
URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO}:${TAG}"
LATEST="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO}:latest"

echo "Logging into ECR..."
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

echo "Building ${URI} from ${ROOT} ..."
docker build -t "$URI" -t "$LATEST" "$ROOT"

echo "Pushing..."
docker push "$URI"
docker push "$LATEST"

echo "Pushed:"
echo "  $URI"
echo "  $LATEST"
echo "Export for next step: export IMAGE_TAG=${TAG}"
