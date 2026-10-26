"""Story model and Claude-powered story writer.

The schema is deliberately constrained to the vocabulary the renderer knows
(backgrounds, character kinds, actions, props, effects), so every story Claude
writes can be drawn without any image generation.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

BACKGROUNDS = [
    "meadow", "forest", "city", "beach", "ocean", "space", "night_sky",
    "desert", "snow", "mountains", "room", "castle",
]
CHARACTER_KINDS = ["person", "cat", "dog", "bird", "fox", "bear", "robot", "alien", "monster"]
ACTIONS = [
    "idle", "talk", "walk_left", "walk_right", "jump", "wave", "dance",
    "sleep", "shiver", "celebrate", "sad",
]
PROPS = [
    "tree", "house", "rock", "flower", "star", "heart", "gift", "treasure",
    "lamp", "rocket", "cloud", "umbrella", "book", "cake", "ball",
]
EFFECTS = ["none", "rain", "snow", "sparkles", "confetti", "hearts", "stars"]
TIMES_OF_DAY = ["morning", "day", "sunset", "night"]
COLORS = [
    "red", "orange", "yellow", "green", "teal", "blue", "purple", "pink",
    "brown", "gray", "white", "black",
]
POSITIONS = ["left", "center", "right"]


@dataclass
class CharacterInScene:
    name: str
    action: str
    position: str
    line: str = ""  # optional speech bubble text


@dataclass
class Scene:
    narration: str
    background: str
    time_of_day: str
    effect: str
    props: list[str]
    characters: list[CharacterInScene]


@dataclass
class Character:
    name: str
    kind: str
    color: str


@dataclass
class Story:
    title: str
    hook: str
    moral: str
    characters: list[Character]
    scenes: list[Scene]
    caption: str
    hashtags: list[str]
    topic: str = ""
    extra: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "Story":
        chars = [Character(**c) for c in d["characters"]]
        scenes = [
            Scene(
                narration=s["narration"],
                background=s["background"],
                time_of_day=s["time_of_day"],
                effect=s["effect"],
                props=list(s.get("props", [])),
                characters=[CharacterInScene(**c) for c in s.get("characters", [])],
            )
            for s in d["scenes"]
        ]
        return cls(
            title=d["title"], hook=d["hook"], moral=d.get("moral", ""),
            characters=chars, scenes=scenes, caption=d["caption"],
            hashtags=list(d["hashtags"]), topic=d.get("topic", ""),
            extra=d.get("extra", {}),
        )

    def full_caption(self, always_tags: list[str] | None = None, max_tags: int = 30) -> str:
        """Caption text + hashtags, de-duplicated and within Instagram's limits."""
        tags: list[str] = []
        for t in list(self.hashtags) + list(always_tags or []):
            t = "#" + t.lstrip("#").replace(" ", "")
            if t.lower() not in (x.lower() for x in tags):
                tags.append(t)
        text = f"{self.caption.strip()}\n\n{' '.join(tags[:max_tags])}"
        return text[:2200]


def _enum(values: list[str]) -> dict:
    return {"type": "string", "enum": values}


STORY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "hook", "moral", "characters", "scenes", "caption", "hashtags"],
    "properties": {
        "title": {"type": "string"},
        "hook": {"type": "string"},
        "moral": {"type": "string"},
        "characters": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "kind", "color"],
                "properties": {
                    "name": {"type": "string"},
                    "kind": _enum(CHARACTER_KINDS),
                    "color": _enum(COLORS),
                },
            },
        },
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["narration", "background", "time_of_day", "effect", "props", "characters"],
                "properties": {
                    "narration": {"type": "string"},
                    "background": _enum(BACKGROUNDS),
                    "time_of_day": _enum(TIMES_OF_DAY),
                    "effect": _enum(EFFECTS),
                    "props": {"type": "array", "items": _enum(PROPS)},
                    "characters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["name", "action", "position", "line"],
                            "properties": {
                                "name": {"type": "string"},
                                "action": _enum(ACTIONS),
                                "position": _enum(POSITIONS),
                                "line": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
        "caption": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
}

SYSTEM_PROMPT = """You write very short animated stories for Instagram Reels.

The video is drawn by a simple 2D renderer, so you can only use the backgrounds, \
character kinds, colors, actions, props and effects allowed by the output schema. \
Pick the ones that best show what the narration says.

Story rules:
- Open with a hook: the first scene's narration must make a viewer want to keep watching.
- A clear arc: setup, a small problem, a turning point, a satisfying ending.
- Each narration is one or two short spoken sentences (about 8-25 words); it is read aloud by text-to-speech.
- 1 to 3 named characters. Each scene lists only the characters on screen, at distinct positions.
- "line" is an optional speech bubble of at most 6 words; use an empty string when the character says nothing.
- Keep it family-friendly and original; no real people, brands or copyrighted characters.

Caption rules:
- 1-3 sentences that tease the story without spoiling the ending, then a call to action (e.g. ask a question or ask viewers to follow).
- May include up to two emoji.
- hashtags: 8-15 relevant tags without the # sign, mixing broad and niche tags."""


def build_prompt(topic: dict, scene_count: int, recent_titles: list[str], language: str) -> str:
    parts = [f"Topic: {topic['name']}"]
    if topic.get("description"):
        parts.append(f"Brief: {topic['description']}")
    if topic.get("mood"):
        parts.append(f"Mood: {topic['mood']}")
    if topic.get("audience"):
        parts.append(f"Audience: {topic['audience']}")
    parts.append(f"Write exactly {scene_count} scenes.")
    parts.append(f"Write the narration, lines and caption in {language}.")
    if topic.get("hashtags"):
        parts.append("Hashtags to consider: " + ", ".join(topic["hashtags"]))
    if recent_titles:
        parts.append(
            "Recently posted stories (make this one clearly different): "
            + "; ".join(recent_titles[-15:])
        )
    return "\n".join(parts)


class StoryError(RuntimeError):
    pass


def write_story(topic: dict, *, model: str, effort: str, scene_count: int,
                recent_titles: list[str] | None = None, language: str = "English") -> Story:
    """Ask Claude for a story matching STORY_SCHEMA."""
    import anthropic

    client = anthropic.Anthropic()
    try:
        response = client.messages.create(
            model=model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": build_prompt(topic, scene_count, recent_titles or [], language),
            }],
            thinking={"type": "adaptive"},
            output_config={
                "effort": effort,
                "format": {"type": "json_schema", "schema": STORY_SCHEMA},
            },
        )
    except anthropic.AuthenticationError as e:
        raise StoryError("Anthropic authentication failed; check ANTHROPIC_API_KEY") from e
    except anthropic.RateLimitError as e:
        raise StoryError("Anthropic rate limit hit; try again later") from e
    except anthropic.APIStatusError as e:
        raise StoryError(f"Anthropic API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise StoryError("Could not reach the Anthropic API") from e

    if response.stop_reason == "refusal":
        raise StoryError(f"Claude declined this topic: {topic['name']}")
    if response.stop_reason == "max_tokens":
        raise StoryError("Story generation was cut off (max_tokens)")

    text = next(b.text for b in response.content if b.type == "text")
    story = Story.from_dict(json.loads(text))
    story.topic = topic["name"]
    return sanitize(story)


def sanitize(story: Story) -> Story:
    """Make sure every scene only references known characters at unique positions."""
    names = {c.name for c in story.characters}
    for scene in story.scenes:
        used: set[str] = set()
        kept = []
        for c in scene.characters:
            if c.name not in names:
                continue
            if c.position in used:
                free = [p for p in POSITIONS if p not in used]
                if not free:
                    continue
                c.position = free[0]
            used.add(c.position)
            kept.append(c)
        scene.characters = kept
    return story
