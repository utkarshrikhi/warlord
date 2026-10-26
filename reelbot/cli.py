"""reelbot command line."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from . import pipeline
from .config import load_config, load_topics


def cmd_topics(cfg, args):
    for key, t in load_topics(cfg).items():
        print(f"{key:16} {t['name']}\n{'':16} {t['description']}\n")


def cmd_generate(cfg, args):
    folder = pipeline.generate(cfg, topic_key=args.topic, prompt=args.prompt,
                               story_file=args.story, scenes=args.scenes)
    print(f"\nCaption:\n{(folder / 'caption.txt').read_text()}\n")
    if args.post:
        pipeline.post(cfg, folder)


def cmd_post(cfg, args):
    pipeline.post(cfg, Path(args.folder))


def cmd_auto(cfg, args):
    pipeline.auto(cfg, dry_run=args.dry_run)


def cmd_schedule(cfg, args):
    from .scheduler import run_forever

    run_forever(cfg)


def cmd_history(cfg, args):
    for h in pipeline.load_history(cfg)[-args.limit:]:
        status = h.get("permalink") or h.get("media_id") or "not posted"
        print(f"{h.get('created_at', '')[:16]}  {h.get('title', '?'):40}  {status}")


def cmd_check(cfg, args):
    ok = True

    def report(good, label, hint=""):
        nonlocal ok
        ok &= good
        print(f"[{'ok' if good else '!!'}] {label}" + (f" -- {hint}" if hint and not good else ""))

    report(bool(shutil.which("ffmpeg")) and bool(shutil.which("ffprobe")), "ffmpeg/ffprobe on PATH",
           "install ffmpeg")
    report(bool(os.environ.get("ANTHROPIC_API_KEY")), "ANTHROPIC_API_KEY set", "add it to .env")
    try:
        n = len(load_topics(cfg))
        report(n > 0, f"{n} topics loaded")
    except Exception as e:
        report(False, "topics file", str(e))
    music = Path(cfg["music"]["dir"])
    tracks = [p for p in music.glob("*") if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg"}] if music.is_dir() else []
    print(f"[--] {len(tracks)} music tracks in {music}" + ("" if tracks else " (videos will have voice only)"))
    if os.environ.get("IG_USER_ID") and os.environ.get("IG_ACCESS_TOKEN"):
        from .publish.instagram import Instagram, InstagramError

        try:
            acct = Instagram(cfg["instagram"]).account()
            report(True, f"Instagram account @{acct.get('username')}")
        except InstagramError as e:
            report(False, "Instagram token", str(e))
    else:
        report(False, "IG_USER_ID / IG_ACCESS_TOKEN set", "needed for posting")
    sys.exit(0 if ok else 1)


def main(argv=None):
    p = argparse.ArgumentParser(prog="reelbot", description="Auto-generate animated story reels and post them to Instagram.")
    p.add_argument("--config", help="path to config.yaml (default: ./config.yaml)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("topics", help="list preset topics").set_defaults(fn=cmd_topics)

    g = sub.add_parser("generate", help="write a story and render the video")
    src = g.add_mutually_exclusive_group()
    src.add_argument("--topic", help="preset topic key from topics.yaml (default: next in rotation)")
    src.add_argument("--prompt", help="your own plot idea, e.g. 'a penguin who wants to see the desert'")
    src.add_argument("--story", type=Path, help="render an existing story.json (skips Claude)")
    g.add_argument("--scenes", type=int, help="number of scenes (default from config)")
    g.add_argument("--post", action="store_true", help="post to Instagram right after rendering")
    g.set_defaults(fn=cmd_generate)

    po = sub.add_parser("post", help="post a generated folder to Instagram")
    po.add_argument("folder")
    po.set_defaults(fn=cmd_post)

    a = sub.add_parser("auto", help="pick the next topic, generate and post (one run; good for cron)")
    a.add_argument("--dry-run", action="store_true", help="generate only, do not post")
    a.set_defaults(fn=cmd_auto)

    sub.add_parser("schedule", help="run forever, posting at schedule.times").set_defaults(fn=cmd_schedule)

    h = sub.add_parser("history", help="show generated/posted reels")
    h.add_argument("--limit", type=int, default=20)
    h.set_defaults(fn=cmd_history)

    sub.add_parser("check", help="verify ffmpeg, API keys and the Instagram token").set_defaults(fn=cmd_check)

    args = p.parse_args(argv)
    cfg = load_config(args.config)
    try:
        args.fn(cfg, args)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        if os.environ.get("REELBOT_DEBUG"):
            raise
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
