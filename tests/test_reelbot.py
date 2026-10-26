import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from reelbot import pipeline, story as story_mod
from reelbot.audio import Speech, subtitle_chunks
from reelbot.config import DEFAULTS, _merge
from reelbot.scheduler import next_run
from reelbot.story import Story

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = json.loads((ROOT / "examples" / "sample_story.json").read_text())


@pytest.fixture
def cfg(tmp_path):
    return _merge(DEFAULTS, {
        "paths": {"output": str(tmp_path / "out"), "topics": str(ROOT / "topics.yaml")},
        "music": {"dir": str(tmp_path / "no-music")},
        "tts": {"provider": "none"},
        "video": {"width": 216, "height": 384, "fps": 6, "preset": "ultrafast"},
    })


def test_story_roundtrip_and_caption():
    s = Story.from_dict(SAMPLE)
    again = Story.from_dict(json.loads(s.to_json()))
    assert again.title == s.title and len(again.scenes) == 5
    cap = s.full_caption(["#Cartoon", "extra tag"], max_tags=5)
    tags = cap.split("\n\n")[1].split()
    assert len(tags) == 5 and tags.count("#cartoon") == 1  # de-duplicated case-insensitively
    assert cap.startswith(s.caption)


def test_sanitize_drops_unknown_and_fixes_positions():
    d = json.loads(json.dumps(SAMPLE))
    d["scenes"][0]["characters"] = [
        {"name": "Pip", "action": "idle", "position": "left", "line": ""},
        {"name": "Ghost", "action": "idle", "position": "center", "line": ""},
        {"name": "Zib", "action": "idle", "position": "left", "line": ""},
    ]
    s = story_mod.sanitize(Story.from_dict(d))
    chars = s.scenes[0].characters
    assert [c.name for c in chars] == ["Pip", "Zib"]
    assert len({c.position for c in chars}) == 2


def test_subtitle_chunks_with_and_without_timings():
    text = "One night, a tiny star crashed right into the backyard."
    even = subtitle_chunks(text, Speech(None, 5.0))
    assert even[0][2] == "One night," and even[-1][1] == pytest.approx(5.0)
    words = [(i * 0.4, i * 0.4 + 0.3, w.strip(",.")) for i, w in enumerate(text.split())]
    timed = subtitle_chunks(text, Speech(None, 4.0, words))
    assert timed[0][2] == "One night,"  # punctuation re-attached
    assert all(a[1] == b[0] for a, b in zip(timed, timed[1:]))  # no gaps


def test_next_run_wraps_to_tomorrow():
    now = datetime(2026, 1, 1, 20, 0)
    assert next_run(now, ["09:00", "18:00"]) == datetime(2026, 1, 2, 9, 0)
    assert next_run(datetime(2026, 1, 1, 10, 0), ["09:00", "18:00"]) == datetime(2026, 1, 1, 18, 0)


def test_topic_rotation_prefers_unused(cfg):
    cfg["schedule"]["topics"] = ["space", "bedtime"]
    pipeline.save_history(cfg, [{"folder": "a", "topic_key": "space"}])
    assert pipeline.pick_topic(cfg) == "bedtime"


def test_write_story_request_and_parsing(monkeypatch):
    captured = {}

    class FakeMessages:
        def create(self, **kw):
            captured.update(kw)
            return SimpleNamespace(stop_reason="end_turn",
                                   content=[SimpleNamespace(type="thinking"),
                                            SimpleNamespace(type="text", text=json.dumps(SAMPLE))])

    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", lambda: SimpleNamespace(messages=FakeMessages()))
    s = story_mod.write_story({"name": "Space adventure", "description": "x"}, model="claude-opus-5-5",
                              effort="medium", scene_count=5, recent_titles=["Old one"])
    assert s.title == SAMPLE["title"] and s.topic == "Space adventure"
    assert captured["output_config"]["format"]["type"] == "json_schema"
    assert captured["thinking"] == {"type": "adaptive"}
    assert "Old one" in captured["messages"][0]["content"]


def test_write_story_refusal(monkeypatch):
    import anthropic

    class FakeMessages:
        def create(self, **kw):
            return SimpleNamespace(stop_reason="refusal", content=[])

    monkeypatch.setattr(anthropic, "Anthropic", lambda: SimpleNamespace(messages=FakeMessages()))
    with pytest.raises(story_mod.StoryError):
        story_mod.write_story({"name": "t", "description": "d"}, model="m", effort="low", scene_count=3)


def test_instagram_resumable_flow(tmp_path, monkeypatch):
    from reelbot.publish import instagram

    video = tmp_path / "v.mp4"
    video.write_bytes(b"0" * 1000)
    calls = []

    def fake_request(method, url, **kw):
        calls.append((method, url, kw))
        if url.endswith("/media"):
            body = {"id": "C1", "uri": "https://rupload.example/C1"}
        elif url.startswith("https://rupload"):
            body = {"success": True}
        elif url.endswith("/C1"):
            body = {"status_code": "FINISHED"}
        elif url.endswith("/media_publish"):
            body = {"id": "M1"}
        else:
            body = {"permalink": "https://instagram.com/reel/x"}
        return SimpleNamespace(status_code=200, json=lambda: body, text="")

    monkeypatch.setenv("IG_USER_ID", "123")
    monkeypatch.setenv("IG_ACCESS_TOKEN", "tok")
    monkeypatch.setattr(instagram.requests, "request", fake_request)
    res = instagram.Instagram(DEFAULTS["instagram"]).publish_reel(video, "hi #tag", log=lambda *a: None)
    assert res.media_id == "M1" and res.permalink.endswith("/x")
    create = calls[0][2]["data"]
    assert create["media_type"] == "REELS" and create["upload_type"] == "resumable"
    assert calls[1][2]["headers"]["file_size"] == "1000"
    assert calls[3][2]["data"]["creation_id"] == "C1"


def test_instagram_error_surfaces(monkeypatch):
    from reelbot.publish import instagram

    monkeypatch.setenv("IG_USER_ID", "123")
    monkeypatch.setenv("IG_ACCESS_TOKEN", "tok")
    monkeypatch.setattr(instagram.requests, "request", lambda *a, **k: SimpleNamespace(
        status_code=400, json=lambda: {"error": {"message": "Invalid token"}}, text=""))
    with pytest.raises(instagram.InstagramError, match="Invalid token"):
        instagram.Instagram(DEFAULTS["instagram"]).account()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_render_end_to_end(cfg, tmp_path):
    story_file = tmp_path / "s.json"
    d = json.loads(json.dumps(SAMPLE))
    d["scenes"] = d["scenes"][:2]
    story_file.write_text(json.dumps(d))
    folder = pipeline.generate(cfg, story_file=story_file, log=lambda *a: None)
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", str(folder / "video.mp4")], capture_output=True, text=True)
    assert out.stdout.strip() == "216,384"
    assert (folder / "caption.txt").read_text().startswith(d["caption"])
    assert pipeline.load_history(cfg)[-1]["title"] == d["title"]
