"""Google Gemini image models ("Nano Banana") via the Interactions API."""

from __future__ import annotations

import base64
import time
from pathlib import Path

from . import ImageError, _mime, api_key


class GeminiImages:
    def __init__(self, cfg: dict):
        from google import genai

        self.cfg = cfg
        self.model = cfg.get("gemini_model", "gemini-nano-banana-2.1")
        self.client = genai.Client(api_key=api_key("GEMINI_API_KEY", "GOOGLE_API_KEY"))

    def generate(self, prompt: str, refs: list[Path], out: Path) -> Path:
        content = [{"type": "text", "text": prompt}]
        for ref in refs:
            content.append({"type": "image", "mime_type": _mime(ref),
                            "data": base64.b64encode(ref.read_bytes()).decode()})
        fmt = {"type": "image", "aspect_ratio": self.cfg.get("aspect_ratio", "9:16")}
        if self.cfg.get("image_size"):
            fmt["image_size"] = self.cfg["image_size"]

        last_err = None
        for attempt in range(3):
            try:
                interaction = self.client.interactions.create(
                    model=self.model, input=content, response_format=fmt,
                )
                img = interaction.output_image
                if img is None or not img.data:
                    raise ImageError(f"Gemini returned no image (text: {interaction.output_text[:200]!r})")
                data = img.data if isinstance(img.data, bytes) else base64.b64decode(img.data)
                out.write_bytes(data)
                return out
            except ImageError as e:
                last_err = e  # usually a safety block or a text-only reply; retry once or twice
            except Exception as e:  # network / rate limit
                last_err = e
            time.sleep(4 * (attempt + 1))
        raise ImageError(f"Gemini image generation failed: {last_err}")
