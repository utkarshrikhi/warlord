"""Renders illustrated stills with slow pan/zoom, crossfades and text overlays."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from . import draw as D
from .engine import Renderer, Segment, ease

CROSSFADE = 0.4
# (start zoom, end zoom, start x/y focus, end x/y focus); focus 0..1 within the free margin
MOTIONS = [
    (1.00, 1.10, (0.5, 0.5), (0.5, 0.45)),  # push in
    (1.10, 1.02, (0.5, 0.4), (0.5, 0.5)),   # pull out
    (1.08, 1.08, (0.0, 0.5), (1.0, 0.5)),   # pan right
    (1.08, 1.08, (1.0, 0.5), (0.0, 0.5)),   # pan left
    (1.08, 1.10, (0.5, 0.0), (0.5, 0.7)),   # tilt down
]


class StillsRenderer(Renderer):
    def __init__(self, story, segments: list[Segment], cfg: dict, images: list[Path]):
        super().__init__(story, segments, cfg)
        self.paths = images
        self.motion = cfg.get("motion", True)
        self._stills: dict[int, Image.Image] = {}
        self._end: Image.Image | None = None

    def still(self, i: int) -> Image.Image:
        """Scene image cover-fitted to the frame with headroom for zooming."""
        if i not in self._stills:
            img = Image.open(self.paths[i]).convert("RGB")
            k = 1.12 if self.motion else 1.0
            size = (int(self.cv.w * k), int(self.cv.h * k))
            if img.width / img.height > 1.3 * size[0] / size[1]:
                # much wider than the frame (e.g. a 16:9 image): cropping would cut the
                # characters off, so fit it to the width over a blurred copy of itself
                back = ImageOps.fit(img, size, Image.BILINEAR).filter(ImageFilter.GaussianBlur(30 * self.cv.s))
                back = Image.blend(back, Image.new("RGB", size, (0, 0, 0)), 0.35)
                fg = ImageOps.contain(img, (size[0], size[1]), Image.LANCZOS)
                back.paste(fg, (0, int((size[1] - fg.height) * 0.42)))
                self._stills[i] = back
            else:
                self._stills[i] = ImageOps.fit(img, size, Image.LANCZOS, centering=(0.5, 0.45))
        return self._stills[i]

    def _camera(self, i: int, p: float) -> Image.Image:
        base = self.still(i)
        if not self.motion:
            return base
        z0, z1, (fx0, fy0), (fx1, fy1) = MOTIONS[i % len(MOTIONS)]
        e = ease(p)
        z = z0 + (z1 - z0) * e
        fx, fy = fx0 + (fx1 - fx0) * e, fy0 + (fy1 - fy0) * e
        bw, bh = base.size
        # frame-shaped window; zoom 1.0 shows the whole (12% oversized) still,
        # so even the tightest zoom is still downscaled and stays sharp
        cw, ch = bw / z, bh / z
        x = (bw - cw) * fx
        y = (bh - ch) * fy
        return base.resize((self.cv.w, self.cv.h), Image.BILINEAR, box=(x, y, x + cw, y + ch))

    def _picture(self, seg: Segment, lt: float) -> Image.Image:
        if seg.scene_index is None:
            return self._end_picture()
        return self._camera(seg.scene_index, lt / seg.duration)

    def _end_picture(self) -> Image.Image:
        if self._end is None:
            last = len(self.paths) - 1
            img = ImageOps.fit(Image.open(self.paths[last]).convert("RGB"), (self.cv.w, self.cv.h), Image.LANCZOS)
            img = img.filter(ImageFilter.GaussianBlur(18 * self.cv.s))
            self._end = Image.blend(img, Image.new("RGB", img.size, (0, 0, 0)), 0.45)
        return self._end

    def frame(self, t: float) -> Image.Image:
        idx = next((k for k, s in enumerate(self.segments) if s.start <= t < s.end), len(self.segments) - 1)
        seg = self.segments[idx]
        lt = t - seg.start
        img = self._picture(seg, lt)

        # crossfade from the previous picture (fade from black at the very start)
        if lt < CROSSFADE:
            a = lt / CROSSFADE
            if idx == 0:
                prev = self.black
            else:
                p = self.segments[idx - 1]
                prev = self._picture(p, p.duration)
            img = Image.blend(prev, img, a)
        if t > self.total - 0.5:
            img = Image.blend(self.black, img, max(0.0, (self.total - t) / 0.5))

        d = ImageDraw.Draw(img, "RGBA")
        if seg.scene_index is None:
            self._end_text(d)
        else:
            if seg.scene_index == 0 and lt < 3.0 and self.cfg.get("show_title", True):
                alpha = int(255 * min(1.0, (3.0 - lt) / 0.4, lt / 0.3 if lt < 0.3 else 1.0))
                D.draw_text_block(d, self.cv, self.story.title, 300, 84, fill=(255, 255, 255),
                                  box=(0, 0, 0, int(alpha * 0.55)), font_path=self.font, alpha=alpha)
            self._subtitles(d, seg, lt)
        return img

    def _end_text(self, d):
        cv = self.cv
        D.draw_text_block(d, cv, self.cfg.get("end_title", "The End"), 600, 110,
                          fill=(255, 230, 100), font_path=self.font)
        if self.story.moral:
            D.draw_text_block(d, cv, self.story.moral, 850, 56, max_w=860, font_path=self.font)
        D.draw_text_block(d, cv, self.cfg.get("outro_text", "Follow for more stories!"), 1400, 60,
                          box=(0, 0, 0, 150), font_path=self.font)
