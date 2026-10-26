"""Free offline stand-in: a labeled card per scene, for previews and tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageDraw

from ..render.draw import Canvas, draw_text_block, gradient


class PlaceholderImages:
    def __init__(self, cfg: dict):
        self.cfg = cfg

    def generate(self, prompt: str, refs: list[Path], out: Path) -> Path:
        h = hashlib.md5(prompt.encode()).digest()
        cv = Canvas(768, 1344)
        img = gradient(cv, [(h[0], h[1], h[2]), (h[3], h[4], h[5])])
        d = ImageDraw.Draw(img, "RGBA")
        scene = prompt.rsplit("Scene:", 1)[-1].strip()
        draw_text_block(d, cv, scene[:300], 960, 44, max_w=900, box=(0, 0, 0, 120))
        img.save(out)
        return out
