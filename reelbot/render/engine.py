"""Composes frames for a timed story and streams them into ffmpeg."""

from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

from ..story import Story
from . import draw as D


@dataclass
class Segment:
    """One stretch of the timeline: a story scene or the end card."""
    start: float
    duration: float
    scene_index: int | None  # None = end card
    voice_offset: float = 0.0
    subtitles: list[tuple[float, float, str]] = field(default_factory=list)

    @property
    def end(self) -> float:
        return self.start + self.duration


def ease(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


class Renderer:
    def __init__(self, story: Story, segments: list[Segment], cfg: dict):
        self.story = story
        self.segments = segments
        self.cfg = cfg
        self.cv = D.Canvas(cfg["width"], cfg["height"])
        self.fps = cfg["fps"]
        self.font = cfg.get("font")
        self.chars = {c.name: c for c in story.characters}
        self._bg_cache: dict[int, Image.Image] = {}
        self.black = Image.new("RGB", (self.cv.w, self.cv.h), (0, 0, 0))

    @property
    def total(self) -> float:
        return self.segments[-1].end

    # ------------------------------------------------------------ backgrounds
    def background(self, i: int) -> Image.Image:
        if i not in self._bg_cache:
            sc = self.story.scenes[i]
            img = D.draw_background(self.cv, sc.background, sc.time_of_day, seed=i * 101)
            d = ImageDraw.Draw(img, "RGBA")
            taken = {D.POSITION_X[c.position] for c in sc.characters}
            slots = [x for x in D.GROUND_PROP_SLOTS if all(abs(x - t) > 150 for t in taken)] or D.GROUND_PROP_SLOTS
            ground_props = [p for p in sc.props if p not in D.SKY_PROPS]
            for prop, x in zip(ground_props, slots):
                D.draw_ground_prop(d, self.cv, prop, x, D.GROUND_Y - 25)
            self._bg_cache[i] = img
        return self._bg_cache[i]

    def end_background(self) -> Image.Image:
        if -1 not in self._bg_cache:
            img = D.gradient(self.cv, [(60, 40, 120), (200, 90, 140), (250, 170, 110)])
            d = ImageDraw.Draw(img, "RGBA")
            d.rectangle(self.cv.p(0, D.GROUND_Y - 30, 1080, 1920), fill=(60, 40, 90, 160))
            self._bg_cache[-1] = img
        return self._bg_cache[-1]

    # ------------------------------------------------------------ frames
    def frame(self, t: float) -> Image.Image:
        seg = next((s for s in self.segments if s.start <= t < s.end), self.segments[-1])
        lt = t - seg.start
        if seg.scene_index is None:
            img = self._end_card(t, lt, seg)
        else:
            img = self._scene(t, lt, seg)

        # slow push-in for a bit of camera life
        z = 1.0 + 0.045 * ease(lt / seg.duration)
        if z > 1.001:
            w, h = self.cv.w, self.cv.h
            cw, ch = w / z, h / z
            box = ((w - cw) / 2, (h - ch) * 0.45, (w + cw) / 2, (h - ch) * 0.45 + ch)
            img = img.resize((w, h), Image.BILINEAR, box=box)

        # fade through black between segments
        fade_in, fade_out = 0.3, 0.25
        a = 1.0
        if lt < fade_in:
            a = lt / fade_in
        elif seg.duration - lt < fade_out:
            a = (seg.duration - lt) / fade_out
        if a < 1.0:
            img = Image.blend(self.black, img, max(a, 0.0))
        return img

    def _subtitles(self, d, seg: Segment, lt: float):
        st = self.cfg.get("subtitles", True)
        if not st:
            return
        vt = lt - seg.voice_offset
        for s, e, text in seg.subtitles:
            if s <= vt < e:
                D.draw_text_block(d, self.cv, text, 1500, 62, max_w=900,
                                  box=(0, 0, 0, 150), font_path=self.font)
                break

    def _scene(self, t: float, lt: float, seg: Segment) -> Image.Image:
        sc = self.story.scenes[seg.scene_index]
        img = self.background(seg.scene_index).copy()
        d = ImageDraw.Draw(img, "RGBA")
        cv = self.cv

        D.draw_ambient(d, cv, sc.background, sc.time_of_day, t, seg.scene_index)
        sky_props = [p for p in sc.props if p in D.SKY_PROPS]
        for j, prop in enumerate(sky_props):
            D.draw_sky_prop(d, cv, prop, 200 + j * 330, 760 + (j % 2) * 90, t)

        k = 0.85 if len(sc.characters) >= 3 else 1.0
        bubbles = []
        for j, c in enumerate(sc.characters):
            ch = self.chars.get(c.name)
            if ch is None:
                continue
            target = D.POSITION_X[c.position]
            action = c.action
            facing = {"left": 1, "right": -1}.get(c.position, 1)
            x = target
            if action in ("walk_left", "walk_right"):
                start = -220 if action == "walk_right" else 1300
                p = min(1.0, lt / max(0.8, seg.duration * 0.55))
                x = start + (target - start) * ease(p)
                facing = 1 if action == "walk_right" else -1
                if p >= 1.0:
                    action = "talk" if c.line else "idle"
            elif action == "idle" and c.line:
                action = "talk"
            head_x, head_top = D.draw_character(d, cv, ch.kind, ch.color, x, t, action,
                                                facing=facing, k=k, local_t=lt + j * 0.37)
            if c.line:
                bubbles.append((j, c.line, head_x, head_top))

        D.draw_effect(d, cv, sc.effect, t, seed=seg.scene_index * 31)

        for j, line, hx, top in bubbles:
            appear = 0.5 + j * 0.9
            if lt >= appear:
                alpha = int(255 * min(1.0, (lt - appear) / 0.25))
                D.speech_bubble(d, cv, line, hx, top, alpha=alpha, font_path=self.font)

        if seg.scene_index == 0 and lt < 3.0:
            alpha = int(255 * min(1.0, (3.0 - lt) / 0.4))
            D.draw_text_block(d, cv, self.story.title, 300, 88, fill=(255, 225, 90),
                              font_path=self.font, alpha=alpha)

        self._subtitles(d, seg, lt)
        return img

    def _end_card(self, t: float, lt: float, seg: Segment) -> Image.Image:
        img = self.end_background().copy()
        d = ImageDraw.Draw(img, "RGBA")
        cv = self.cv
        D.draw_effect(d, cv, "confetti", t, seed=99)
        D.draw_text_block(d, cv, self.cfg.get("end_title", "The End"), 330, 110,
                          fill=(255, 230, 100), font_path=self.font)
        if self.story.moral:
            D.draw_text_block(d, cv, self.story.moral, 560, 56, max_w=860, font_path=self.font)
        chars = self.story.characters[:3]
        xs = {1: [540], 2: [360, 720], 3: [250, 540, 830]}[len(chars)] if chars else []
        for j, (ch, x) in enumerate(zip(chars, xs)):
            D.draw_character(d, cv, ch.kind, ch.color, x, t, "celebrate", k=0.85, local_t=lt + j * 0.3)
        D.draw_text_block(d, cv, self.cfg.get("outro_text", "Follow for more stories!"), 1520, 60,
                          box=(0, 0, 0, 150), font_path=self.font)
        return img

    # ------------------------------------------------------------ encoding
    def write(self, out: Path, audio: Path | None, progress=None) -> Path:
        w, h = self.cv.w, self.cv.h
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(self.fps), "-i", "-",
        ]
        if audio:
            cmd += ["-i", str(audio)]
        cmd += ["-c:v", "libx264", "-preset", self.cfg.get("preset", "medium"), "-crf", "20",
                "-pix_fmt", "yuv420p", "-r", str(self.fps)]
        if audio:
            cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest"]
        cmd += ["-movflags", "+faststart", str(out)]

        n = int(math.ceil(self.total * self.fps))
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        try:
            for i in range(n):
                proc.stdin.write(self.frame(i / self.fps).tobytes())
                if progress and i % self.fps == 0:
                    progress(i, n)
        finally:
            proc.stdin.close()
            code = proc.wait()
        if code != 0:
            raise RuntimeError(f"ffmpeg exited with code {code}")
        return out
