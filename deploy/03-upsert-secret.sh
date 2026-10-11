#!/usr/bin/env bash
# Create/update Secrets Manager secret used by the Fargate task (mirrors ai-engineer-construction/backend).
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
SECRET_NAME="ai-tools/backend"
EXAMPLE="$(cd "$(dirname "$0")" && pwd)/secrets.example.json"
FILE="${1:-$EXAMPLE}"

if [[ ! -f "$FILE" ]]; then
  echo "Usage: $0 path/to/secrets.json" >&2
  exit 1
fi

if aws secretsmanager describe-secret --secret-id "$SECRET_NAME" --region "$REGION" >/dev/null 2>&1; then
  aws secretsmanager put-secret-value \
    --secret-id "$SECRET_NAME" \
    --secret-string "file://${FILE}" \
    --region "$REGION" >/dev/null
  echo "Updated secret: $SECRET_NAME"
else
  aws secretsmanager create-secret \
    --name "$SECRET_NAME" \
    --secret-string "file://${FILE}" \
    --region "$REGION" >/dev/null
  echo "Created secret: $SECRET_NAME"
fi

aws secretsmanager describe-secret --secret-id "$SECRET_NAME" --region "$REGION" \
  --query '{ARN:ARN,Name:Name}' --output json
