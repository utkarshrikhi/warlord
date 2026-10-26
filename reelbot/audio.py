"""Voiceover (text-to-speech) and the final audio mix."""

from __future__ import annotations

import asyncio
import json
import os
import random
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac"}


@dataclass
class Speech:
    path: Path | None
    duration: float
    # (start, end, text) in seconds relative to the start of the clip
    words: list[tuple[float, float, str]] = field(default_factory=list)


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def estimate_duration(text: str, words_per_sec: float = 2.6) -> float:
    return max(1.5, len(text.split()) / words_per_sec)


def synthesize(text: str, path: Path, cfg: dict) -> Speech:
    """Speak `text` into `path` with the configured TTS provider."""
    provider = cfg.get("provider", "edge")
    if provider == "none" or not text.strip():
        return Speech(None, estimate_duration(text))
    if provider == "edge":
        return asyncio.run(_edge_tts(text, path, cfg))
    if provider == "gtts":
        from gtts import gTTS

        gTTS(text, lang=cfg.get("language", "en")).save(str(path))
        return Speech(path, probe_duration(path))
    raise ValueError(f"Unknown tts provider: {provider}")


async def _edge_tts(text: str, path: Path, cfg: dict) -> Speech:
    import edge_tts

    comm = edge_tts.Communicate(
        text,
        cfg.get("voice", "en-US-AnaNeural"),
        rate=cfg.get("rate", "+0%"),
        pitch=cfg.get("pitch", "+0Hz"),
        boundary="WordBoundary",
        proxy=os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"),
    )
    words = []
    with open(path, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7  # 100-nanosecond units
                words.append((start, start + chunk["duration"] / 1e7, chunk["text"]))
    return Speech(path, probe_duration(path), words)


def subtitle_chunks(text: str, speech: Speech, max_chars: int = 28) -> list[tuple[float, float, str]]:
    """Split narration into short on-screen chunks timed to the voice."""
    words = speech.words
    if not words:
        # No word timings: spread the text evenly over the clip.
        tokens = text.split()
        total = sum(len(t) + 1 for t in tokens) or 1
        words, t = [], 0.0
        for tok in tokens:
            dt = speech.duration * (len(tok) + 1) / total
            words.append((t, t + dt, tok))
            t += dt
    else:
        # Re-attach punctuation from the original text to the spoken words.
        tokens = text.split()
        if len(tokens) == len(words):
            words = [(s, e, tok) for (s, e, _), tok in zip(words, tokens)]

    chunks, cur, start = [], [], None
    for s, e, w in words:
        if start is None:
            start = s
        cur.append(w)
        line = " ".join(cur)
        if len(line) >= max_chars or w.endswith((".", "!", "?", ",")):
            chunks.append([start, e, line])
            cur, start = [], None
    if cur:
        chunks.append([start, words[-1][1], " ".join(cur)])
    # keep each chunk on screen until the next one starts
    for a, b in zip(chunks, chunks[1:]):
        a[1] = b[0]
    if chunks:
        chunks[-1][1] = max(chunks[-1][1], speech.duration)
    return [tuple(c) for c in chunks]


def pick_music(music_dir: Path, rnd: random.Random) -> Path | None:
    if not music_dir.is_dir():
        return None
    tracks = sorted(p for p in music_dir.iterdir() if p.suffix.lower() in AUDIO_EXTS)
    return rnd.choice(tracks) if tracks else None


def mix_track(clips: list[tuple[float, Path]], total: float, music: Path | None,
              music_volume: float, out: Path) -> Path | None:
    """Place each voice clip at its start time, add looping background music
    (ducked under the voice) and write a single AAC-ready WAV."""
    if not clips and music is None:
        return None
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    filters, labels = [], []
    for i, (start, path) in enumerate(clips):
        cmd += ["-i", str(path)]
        ms = int(start * 1000)
        filters.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms}[v{i}]")
        labels.append(f"[v{i}]")
    if music is not None:
        idx = len(clips)
        cmd += ["-stream_loop", "-1", "-i", str(music)]
        fade_start = max(0.0, total - 2.0)
        filters.append(
            f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total:.3f},"
            f"volume={music_volume},afade=t=in:d=1,afade=t=out:st={fade_start:.3f}:d=2[m]"
        )
        labels.append("[m]")
    filters.append(
        f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest,"
        f"apad,atrim=0:{total:.3f}[out]"
    )
    cmd += ["-filter_complex", ";".join(filters), "-map", "[out]", "-ar", "48000", str(out)]
    subprocess.run(cmd, check=True)
    return out
