"""Thin S3 wrapper that talks to LocalStack."""
from __future__ import annotations
import boto3
from botocore.config import Config


def make_s3_client(endpoint: str, region: str,
                   access_key: str, secret_key: str):
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        # path-style addressing — LocalStack-friendly
        config=Config(s3={"addressing_style": "path"}, signature_version="s3v4"),
    )


def ensure_bucket(s3, bucket: str) -> None:
    try:
        s3.head_bucket(Bucket=bucket)
    except Exception:
        s3.create_bucket(Bucket=bucket)
