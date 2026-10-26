"""Public-URL hosting, only needed when instagram.upload_mode is "url".

The default "resumable" mode uploads straight from disk and needs none of this.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

import requests


def upload(video: Path, cfg: dict) -> str:
    provider = cfg.get("provider", "s3")
    if provider == "s3":
        return _s3(video, cfg)
    if provider == "cloudinary":
        return _cloudinary(video)
    raise ValueError(f"Unknown hosting provider: {provider}")


def _s3(video: Path, cfg: dict) -> str:
    import boto3  # optional dependency: pip install boto3

    bucket = cfg.get("s3_bucket")
    if not bucket:
        raise ValueError("hosting.s3_bucket is not set")
    key = f"{cfg.get('s3_prefix', '')}{int(time.time())}-{video.name}"
    s3 = boto3.client("s3", region_name=cfg.get("s3_region") or None)
    s3.upload_file(str(video), bucket, key, ExtraArgs={"ContentType": "video/mp4"})
    # a presigned GET URL is enough for Instagram to fetch the file once
    return s3.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=6 * 3600)


def _cloudinary(video: Path) -> str:
    cloud = os.environ["CLOUDINARY_CLOUD_NAME"]
    key = os.environ["CLOUDINARY_API_KEY"]
    secret = os.environ["CLOUDINARY_API_SECRET"]
    ts = str(int(time.time()))
    signature = hashlib.sha1(f"timestamp={ts}{secret}".encode()).hexdigest()
    with open(video, "rb") as f:
        resp = requests.post(
            f"https://api.cloudinary.com/v1_1/{cloud}/video/upload",
            data={"api_key": key, "timestamp": ts, "signature": signature},
            files={"file": f}, timeout=600,
        )
    resp.raise_for_status()
    return resp.json()["secure_url"]
