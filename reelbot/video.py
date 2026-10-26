"""Story -> narrated, subtitled, scored MP4."""

from __future__ import annotations

import random
from pathlib import Path

from . import audio
from .render.engine import Renderer, Segment
from .story import Story

VOICE_LEAD_IN = 0.45  # seconds of picture before the narrator starts
VOICE_TAIL = 0.7      # pause after the narrator finishes


def make_video(story: Story, cfg: dict, out_dir: Path, log=print) -> Path:
    vcfg = cfg["video"]
    tcfg = cfg["tts"]
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "work"
    work.mkdir(exist_ok=True)

    segments: list[Segment] = []
    clips: list[tuple[float, Path]] = []
    t = 0.0

    texts = [(i, s.narration) for i, s in enumerate(story.scenes)]
    outro = " ".join(x for x in (story.moral, vcfg.get("outro_voice", "")) if x)
    texts.append((None, outro))

    for idx, text in texts:
        name = f"scene_{idx:02d}.mp3" if idx is not None else "outro.mp3"
        log(f"  voice: {name}")
        speech = audio.synthesize(text, work / name, tcfg)
        min_len = vcfg.get("min_scene_seconds", 3.0) if idx is not None else vcfg.get("end_card_seconds", 3.5)
        dur = max(min_len, VOICE_LEAD_IN + speech.duration + VOICE_TAIL)
        seg = Segment(start=t, duration=dur, scene_index=idx, voice_offset=VOICE_LEAD_IN,
                      subtitles=audio.subtitle_chunks(text, speech) if idx is not None else [])
        segments.append(seg)
        if speech.path:
            clips.append((t + VOICE_LEAD_IN, speech.path))
        t += dur

    total = t
    music = audio.pick_music(Path(cfg["music"]["dir"]), random.Random(story.title))
    if music:
        log(f"  music: {music.name}")
    track = audio.mix_track(clips, total, music, cfg["music"].get("volume", 0.12), work / "mix.wav")

    out = out_dir / "video.mp4"
    if vcfg.get("style", "illustrated") == "illustrated":
        from .images import generate_scene_images
        from .render.stills import StillsRenderer

        images = generate_scene_images(story, cfg, out_dir, log=log)
        renderer = StillsRenderer(story, segments, vcfg, images)
    else:
        renderer = Renderer(story, segments, vcfg)
    log(f"  rendering {total:.1f}s at {vcfg['width']}x{vcfg['height']} {vcfg['fps']}fps")
    renderer.write(out, track, progress=lambda i, n: log(f"    frame {i}/{n}") if i % (vcfg["fps"] * 5) == 0 else None)
    return out


def make_thumbnail(story: Story, cfg: dict, out: Path) -> Path:
    """Still from the first scene, for previews or as a cover image."""
    seg = Segment(start=0, duration=4, scene_index=0)
    first = out.parent / "scene_00.png"
    if cfg["video"].get("style", "illustrated") == "illustrated" and first.is_file():
        from .render.stills import StillsRenderer

        renderer = StillsRenderer(story, [seg], cfg["video"], [first])
    else:
        renderer = Renderer(story, [seg], cfg["video"])
    renderer.frame(1.2).convert("RGB").save(out, quality=90)
    return out
