"""Upload a file to Cloudflare R2 via boto3 (S3-compatible).

Why not the ``aws`` CLI? aws-cli v2 adds "flexible checksum" trailers to every
PutObject that R2 does not fold into its SigV4 signature, so uploads fail with
``SignatureDoesNotMatch`` no matter how correct the keys are. boto3 lets us turn
those checksums off explicitly, which R2 accepts.

Usage::

    python scripts/r2_upload.py LOCAL_FILE KEY [--content-type audio/mpeg]
                                                [--cache-control no-cache]

Reads credentials from the environment (same names the workflow already sets):
``R2_ACCOUNT_ID``, ``R2_BUCKET``, ``AWS_ACCESS_KEY_ID``, ``AWS_SECRET_ACCESS_KEY``.
"""

from __future__ import annotations

import argparse
import os
import sys

import boto3
from botocore.config import Config


def _client():
    account_id = os.environ["R2_ACCOUNT_ID"]
    endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
    # region_name="auto" is R2's convention. The two checksum knobs are the
    # crucial bit: they stop boto3 adding the integrity trailers that trip R2's
    # SigV4 check (the aws-cli SignatureDoesNotMatch failure).
    config = Config(
        region_name="auto",
        signature_version="s3v4",
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
        retries={"max_attempts": 3, "mode": "standard"},
    )
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        config=config,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload a file to Cloudflare R2.")
    parser.add_argument("local_file", help="Path to the file to upload")
    parser.add_argument("key", help="Destination object key in the bucket")
    parser.add_argument("--content-type", default="application/octet-stream")
    parser.add_argument("--cache-control", default=None)
    args = parser.parse_args()

    bucket = os.environ["R2_BUCKET"]
    extra = {"ContentType": args.content_type}
    if args.cache_control:
        extra["CacheControl"] = args.cache_control

    with open(args.local_file, "rb") as fh:
        _client().put_object(Bucket=bucket, Key=args.key, Body=fh, **extra)

    print(f"✅ Uploaded {args.local_file} -> s3://{bucket}/{args.key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
