"""High-level steps: pick a topic, generate a reel, post it, remember it."""

from __future__ import annotations

import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path

from .config import load_topics
from .story import Story, write_story
from .video import make_thumbnail, make_video


# ------------------------------------------------------------------ history

def _history_path(cfg: dict) -> Path:
    return Path(cfg["paths"]["output"]) / "history.json"


def load_history(cfg: dict) -> list[dict]:
    p = _history_path(cfg)
    return json.loads(p.read_text()) if p.is_file() else []


def save_history(cfg: dict, history: list[dict]) -> None:
    p = _history_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(history, indent=2))


def _record(cfg: dict, folder: Path, **fields) -> None:
    history = load_history(cfg)
    entry = next((h for h in history if h["folder"] == str(folder)), None)
    if entry is None:
        entry = {"folder": str(folder)}
        history.append(entry)
    entry.update(fields)
    save_history(cfg, history)


# ------------------------------------------------------------------ topics

def pick_topic(cfg: dict, rnd: random.Random | None = None) -> str:
    """Least-recently-used topic from the schedule's list (or all topics)."""
    rnd = rnd or random.Random()
    topics = load_topics(cfg)
    pool = [t for t in (cfg["schedule"].get("topics") or list(topics)) if t in topics]
    if not pool:
        raise ValueError("No valid topics to choose from")
    last_used = {}
    for i, h in enumerate(load_history(cfg)):
        if h.get("topic_key"):
            last_used[h["topic_key"]] = i
    rnd.shuffle(pool)
    return min(pool, key=lambda k: last_used.get(k, -1))


def resolve_topic(cfg: dict, key: str | None, prompt: str | None) -> tuple[str | None, dict]:
    if prompt:
        return None, {"name": prompt[:80], "description": prompt}
    topics = load_topics(cfg)
    key = key or pick_topic(cfg)
    if key not in topics:
        raise KeyError(f"Unknown topic '{key}'. Available: {', '.join(topics)}")
    return key, topics[key]


# ------------------------------------------------------------------ steps

def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "story"


def generate(cfg: dict, *, topic_key: str | None = None, prompt: str | None = None,
             story_file: Path | None = None, scenes: int | None = None, log=print) -> Path:
    if story_file:
        story = Story.from_dict(json.loads(Path(story_file).read_text()))
        key = None
    else:
        key, topic = resolve_topic(cfg, topic_key, prompt)
        recent = [h["title"] for h in load_history(cfg) if h.get("title")]
        c = cfg["claude"]
        log(f"Writing a story for: {topic['name']}")
        story = write_story(topic, model=c["model"], effort=c["effort"],
                            scene_count=scenes or c["scenes"], recent_titles=recent,
                            language=c.get("language", "English"))
    log(f"Story: {story.title} ({len(story.scenes)} scenes)")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = Path(cfg["paths"]["output"]) / f"{stamp}-{slugify(story.title)}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "story.json").write_text(story.to_json())
    ig = cfg["instagram"]
    caption = story.full_caption(ig.get("always_hashtags"), ig.get("max_hashtags", 15))
    (folder / "caption.txt").write_text(caption)

    make_video(story, cfg, folder, log=log)
    make_thumbnail(story, cfg, folder / "thumbnail.jpg")
    _record(cfg, folder, title=story.title, topic_key=key, topic=story.topic,
            created_at=datetime.now(timezone.utc).isoformat())
    log(f"Done: {folder / 'video.mp4'}")
    return folder


def post(cfg: dict, folder: Path, log=print) -> dict:
    from .publish.instagram import Instagram

    folder = Path(folder)
    video = folder / "video.mp4"
    caption = (folder / "caption.txt").read_text()
    if not video.is_file():
        raise FileNotFoundError(video)
    entry = next((h for h in load_history(cfg) if h["folder"] == str(folder)), {})
    if entry.get("media_id"):
        raise RuntimeError(f"Already posted as {entry.get('permalink') or entry['media_id']}")

    log(f"Posting {folder.name} to Instagram")
    result = Instagram(cfg["instagram"], cfg["hosting"]).publish_reel(video, caption, log=log)
    _record(cfg, folder, media_id=result.media_id, permalink=result.permalink,
            posted_at=datetime.now(timezone.utc).isoformat())
    log(f"Posted: {result.permalink or result.media_id}")
    return {"media_id": result.media_id, "permalink": result.permalink}


def auto(cfg: dict, *, dry_run: bool = False, log=print) -> Path:
    folder = generate(cfg, log=log)
    if dry_run or not cfg["schedule"].get("auto_post", True):
        log("Not posting (dry run / auto_post is off)")
    else:
        post(cfg, folder, log=log)
    return folder
