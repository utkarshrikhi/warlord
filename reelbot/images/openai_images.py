"""OpenAI GPT Image models."""

from __future__ import annotations

import base64
import time
from contextlib import ExitStack
from pathlib import Path

from . import ImageError, api_key


class OpenAIImages:
    def __init__(self, cfg: dict):
        from openai import OpenAI

        self.cfg = cfg
        self.model = cfg.get("openai_model", "gpt-image-2")
        self.client = OpenAI(api_key=api_key("OPENAI_API_KEY"))

    def generate(self, prompt: str, refs: list[Path], out: Path) -> Path:
        kw = dict(model=self.model, prompt=prompt, size=self.cfg.get("openai_size", "1024x1536"),
                  quality=self.cfg.get("openai_quality", "medium"))
        last_err = None
        for attempt in range(3):
            try:
                with ExitStack() as stack:
                    if refs:
                        files = [stack.enter_context(open(r, "rb")) for r in refs]
                        resp = self.client.images.edit(image=files, **kw)
                    else:
                        resp = self.client.images.generate(**kw)
                out.write_bytes(base64.b64decode(resp.data[0].b64_json))
                return out
            except Exception as e:
                last_err = e
                time.sleep(4 * (attempt + 1))
        raise ImageError(f"OpenAI image generation failed: {last_err}")
