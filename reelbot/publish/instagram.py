"""Publish a Reel through the official Instagram Graph API.

Flow: create a REELS media container -> upload the video (resumable upload
straight from disk, or a public URL) -> wait until Instagram has processed
it -> media_publish.

Requires an Instagram Business or Creator account and a long-lived access
token with instagram_basic + instagram_content_publish (Facebook Login) or
instagram_business_basic + instagram_business_content_publish (Instagram
Login, set graph_host to graph.instagram.com).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from . import hosting


class InstagramError(RuntimeError):
    pass


@dataclass
class PublishResult:
    media_id: str
    permalink: str | None


class Instagram:
    def __init__(self, cfg: dict, hosting_cfg: dict | None = None):
        self.cfg = cfg
        self.hosting_cfg = hosting_cfg or {}
        self.user_id = os.environ.get("IG_USER_ID", "")
        self.token = os.environ.get("IG_ACCESS_TOKEN", "")
        if not self.user_id or not self.token:
            raise InstagramError("Set IG_USER_ID and IG_ACCESS_TOKEN (see README)")
        self.base = f"https://{cfg['graph_host']}/{cfg['api_version']}"

    # ------------------------------------------------------------ helpers
    def _call(self, method: str, url: str, **kw) -> dict:
        kw.setdefault("timeout", 120)
        resp = requests.request(method, url, **kw)
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if resp.status_code >= 400 or "error" in data:
            err = data.get("error", {})
            msg = err.get("error_user_msg") or err.get("message") or resp.text[:300]
            raise InstagramError(f"Graph API {resp.status_code}: {msg}")
        return data

    def account(self) -> dict:
        return self._call("GET", f"{self.base}/{self.user_id}",
                          params={"fields": "username,media_count", "access_token": self.token})

    # ------------------------------------------------------------ publish
    def publish_reel(self, video: Path, caption: str, cover_offset_ms: int = 1200, log=print) -> PublishResult:
        params = {
            "media_type": "REELS",
            "caption": caption,
            "share_to_feed": "true" if self.cfg.get("share_to_feed", True) else "false",
            "thumb_offset": str(cover_offset_ms),
            "access_token": self.token,
        }
        if self.cfg.get("upload_mode", "resumable") == "resumable":
            params["upload_type"] = "resumable"
            container = self._call("POST", f"{self.base}/{self.user_id}/media", data=params)
            cid = container["id"]
            log(f"  container {cid}: uploading {video.stat().st_size / 1e6:.1f} MB")
            upload_uri = container.get("uri") or \
                f"https://rupload.facebook.com/ig-api-upload/{self.cfg['api_version']}/{cid}"
            with open(video, "rb") as f:
                self._call("POST", upload_uri, data=f, timeout=600, headers={
                    "Authorization": f"OAuth {self.token}",
                    "offset": "0",
                    "file_size": str(video.stat().st_size),
                })
        else:
            url = hosting.upload(video, self.hosting_cfg)
            log(f"  hosted at {url}")
            params["video_url"] = url
            cid = self._call("POST", f"{self.base}/{self.user_id}/media", data=params)["id"]
            log(f"  container {cid}")

        self._wait(cid, log)
        media_id = self._call("POST", f"{self.base}/{self.user_id}/media_publish",
                              data={"creation_id": cid, "access_token": self.token})["id"]
        permalink = None
        try:
            permalink = self._call("GET", f"{self.base}/{media_id}",
                                   params={"fields": "permalink", "access_token": self.token}).get("permalink")
        except InstagramError:
            pass
        return PublishResult(media_id, permalink)

    def _wait(self, cid: str, log) -> None:
        deadline = time.time() + self.cfg.get("publish_timeout", 900)
        while time.time() < deadline:
            data = self._call("GET", f"{self.base}/{cid}",
                              params={"fields": "status_code,status", "access_token": self.token})
            code = data.get("status_code")
            if code in ("FINISHED", "PUBLISHED"):
                return
            if code in ("ERROR", "EXPIRED"):
                raise InstagramError(f"Instagram could not process the video: {data.get('status', code)}")
            log(f"  processing ({code})...")
            time.sleep(10)
        raise InstagramError("Timed out waiting for Instagram to process the video")
