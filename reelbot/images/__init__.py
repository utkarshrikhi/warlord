"""Scene image generation: pluggable providers + prompt building.

Providers implement `generate(prompt, refs, out)`: draw one 9:16 image for
`prompt`, using the reference images `refs` (mascot sheet, earlier scene) to
keep characters and style consistent, and save it to `out`.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


class ImageError(RuntimeError):
    pass


def get_provider(cfg: dict):
    name = cfg.get("provider", "gemini")
    if name == "gemini":
        from .gemini import GeminiImages
        return GeminiImages(cfg)
    if name == "openai":
        from .openai_images import OpenAIImages
        return OpenAIImages(cfg)
    if name == "placeholder":
        from .placeholder import PlaceholderImages
        return PlaceholderImages(cfg)
    raise ValueError(f"Unknown image provider: {name}")


def _mime(path: Path) -> str:
    return "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"


# ------------------------------------------------------------------ prompts

def character_lines(story, names: list[str], mascot: dict) -> list[str]:
    by_name = {c.name: c for c in story.characters}
    lines = []
    for n in names:
        if mascot.get("name") == n:
            lines.append(f"- {n}: {mascot.get('description', '')} (must look exactly like the character "
                         f"in the first reference image)")
        elif n in by_name and by_name[n].description:
            lines.append(f"- {n}: {by_name[n].description}")
    return lines


def scene_prompt(story, index: int, icfg: dict, mascot: dict, has_mascot_ref: bool, has_style_ref: bool) -> str:
    sc = story.scenes[index]
    cast = sc.cast or [c.name for c in story.characters]
    parts = [
        f"Art style: {icfg['style'].strip()}",
        "Format: vertical 9:16 illustration. Keep the main characters and action in the middle of the "
        "frame; leave the bottom fifth uncluttered. Absolutely no text, letters, captions, logos, "
        "watermarks or speech bubbles.",
    ]
    chars = character_lines(story, cast, mascot if has_mascot_ref else {**mascot, "name": None})
    if chars:
        parts.append("Characters in this picture:\n" + "\n".join(chars))
    if has_style_ref:
        parts.append(f"The {'second' if has_mascot_ref else 'first'} reference image is an earlier scene of "
                     "the same story: match its art style, line weight, colors and the look of any recurring "
                     "characters. Do not copy its composition.")
    parts.append(f"Scene: {sc.image_prompt or sc.narration}")
    return "\n\n".join(parts)


def mascot_prompt(icfg: dict, mascot: dict) -> str:
    return (f"Art style: {icfg['style'].strip()}\n\n"
            f"Character reference sheet for {mascot['name']}: {mascot['description']}. "
            "One full-body view, standing, facing the viewer at a slight angle, friendly neutral expression, "
            "centered on a plain light gray background. Vertical 9:16. No text.")


# ------------------------------------------------------------------ batch

def ensure_mascot(cfg: dict, log=print, force: bool = False) -> Path | None:
    mascot = cfg.get("mascot") or {}
    if not mascot.get("name"):
        return None
    ref = Path(mascot.get("reference", "assets/mascot.png"))
    if ref.is_file() and not force:
        return ref
    log(f"  drawing mascot reference sheet for {mascot['name']} -> {ref}")
    ref.parent.mkdir(parents=True, exist_ok=True)
    get_provider(cfg["images"]).generate(mascot_prompt(cfg["images"], mascot), [], ref)
    return ref


def generate_scene_images(story, cfg: dict, folder: Path, log=print) -> list[Path]:
    """Draw every missing scene image in `folder`; existing ones are reused,
    so deleting one image and re-rendering redraws only that scene."""
    icfg = cfg["images"]
    mascot = cfg.get("mascot") or {}
    provider = get_provider(icfg)
    mascot_ref = ensure_mascot(cfg, log)
    paths = [folder / f"scene_{i:02d}.png" for i in range(len(story.scenes))]

    def draw(i: int) -> None:
        if paths[i].is_file():
            return
        refs = [mascot_ref] if mascot_ref else []
        style_ref = i > 0 and paths[0].is_file()
        if style_ref:
            refs.append(paths[0])
        prompt = scene_prompt(story, i, icfg, mascot, bool(mascot_ref), style_ref)
        log(f"  drawing scene {i + 1}/{len(paths)}")
        (folder / f"scene_{i:02d}.prompt.txt").write_text(prompt)
        provider.generate(prompt, refs, paths[i])

    # scene 1 first: it becomes the style reference for the rest
    draw(0)
    workers = int(icfg.get("parallel", 3))
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        list(pool.map(draw, range(1, len(paths))))
    return paths


def api_key(*names: str) -> str:
    for n in names:
        if os.environ.get(n):
            return os.environ[n]
    raise ImageError(f"Set {' or '.join(names)} in .env")
