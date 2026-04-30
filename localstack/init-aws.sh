#!/bin/bash
# Runs inside the LocalStack container once it's ready.
set -e
echo "[init-aws] creating S3 bucket rag-uploads"
awslocal s3 mb s3://rag-uploads || true
awslocal s3api put-bucket-versioning \
  --bucket rag-uploads \
  --versioning-configuration Status=Enabled || true
echo "[init-aws] done"
