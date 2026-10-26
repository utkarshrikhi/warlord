"""Configuration: config.yaml merged over defaults, secrets from env / .env."""

from __future__ import annotations

import copy
import os
from pathlib import Path

import yaml

DEFAULTS = {
    "claude": {
        "model": "claude-opus-5-5",
        "effort": "medium",
        "scenes": 5,
        "language": "English",
    },
    "video": {
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "preset": "medium",
        "subtitles": True,
        "min_scene_seconds": 3.0,
        "end_card_seconds": 3.5,
        "end_title": "The End",
        "outro_text": "Follow for more stories!",
        "outro_voice": "Follow for more stories!",
        "font": None,
    },
    "tts": {
        "provider": "edge",  # edge | gtts | none
        "voice": "en-US-AnaNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "language": "en",
    },
    "music": {"dir": "assets/music", "volume": 0.12},
    "instagram": {
        "graph_host": "graph.facebook.com",
        "api_version": "v23.0",
        "upload_mode": "resumable",  # resumable | url
        "share_to_feed": True,
        "always_hashtags": [],
        "max_hashtags": 15,
        "publish_timeout": 900,
    },
    "hosting": {"provider": "s3", "s3_bucket": "", "s3_prefix": "reels/", "s3_region": ""},
    "schedule": {
        "timezone": "UTC",
        "times": ["09:00", "18:00"],
        "topics": [],  # empty = rotate through every topic in topics.yaml
        "auto_post": True,
    },
    "paths": {"output": "output", "topics": "topics.yaml"},
}

SECRET_ENV = [
    "ANTHROPIC_API_KEY", "IG_USER_ID", "IG_ACCESS_TOKEN",
    "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET",
]


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_dotenv(path: Path) -> None:
    """Minimal .env reader; real environment variables win."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip("'\""))


def load_config(path: str | None = None) -> dict:
    cfg_path = Path(path or os.environ.get("REELBOT_CONFIG", "config.yaml"))
    load_dotenv(cfg_path.parent / ".env")
    user = yaml.safe_load(cfg_path.read_text()) if cfg_path.is_file() else {}
    cfg = _merge(DEFAULTS, user or {})
    cfg["_config_path"] = str(cfg_path)
    return cfg


def load_topics(cfg: dict) -> dict[str, dict]:
    path = Path(cfg["paths"]["topics"])
    if not path.is_file():
        raise FileNotFoundError(f"Topics file not found: {path}")
    topics = yaml.safe_load(path.read_text()) or {}
    for key, t in topics.items():
        if not t.get("name") or not t.get("description"):
            raise ValueError(f"Topic '{key}' needs a name and a description")
    return topics
