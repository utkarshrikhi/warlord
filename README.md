# reelbot

Auto-generates short animated story videos and posts them to Instagram as Reels.

1. **Story**: Claude writes a short story from a preset topic or your own idea: title, 4-7 scenes, speech bubbles, a moral, a caption and hashtags.
2. **Visuals**: a built-in 2D renderer draws every scene in code (12 backgrounds, 9 character types, 15 props, weather/particle effects, walking/jumping/dancing/talking animation). No image API and no per-image cost.
3. **Audio**: free neural text-to-speech narration (edge-tts), burned-in subtitles synced word by word to the voice, and optional background music mixed under it.
4. **Posting**: uploads through the official Instagram Graph API, either on demand or on a schedule.

Output is a 1080x1920 H.264/AAC MP4 (Reels spec), typically 25-45 seconds.

## Setup

Requires Python 3.10+ and [ffmpeg](https://ffmpeg.org/download.html) on your PATH.

```bash
pip install -e .            # or: pip install -e ".[s3]" if you'll host videos on S3
cp .env.example .env        # then fill in your keys
reelbot check               # verifies ffmpeg, keys and the Instagram token
```

Optional: put royalty-free music tracks in `assets/music/` (one is picked per video).

### Anthropic API key

Create one at https://console.anthropic.com and set `ANTHROPIC_API_KEY` in `.env`. Each story is one request.

### Instagram access

The Graph API only publishes to **Instagram Business or Creator accounts**:

1. Switch your Instagram account to Professional (Creator or Business) in the Instagram app.
2. Create an app at https://developers.facebook.com (type: Business) and add the **Instagram** product.
3. Choose one login flow:
   - **Instagram Login** (simplest, no Facebook Page needed): grant `instagram_business_basic` and `instagram_business_content_publish`, then set `instagram.graph_host: graph.instagram.com` in `config.yaml`.
   - **Facebook Login**: link the Instagram account to a Facebook Page and grant `instagram_basic`, `instagram_content_publish` and `pages_read_engagement`. Keep the default `graph_host: graph.facebook.com`.
4. Generate a **long-lived access token** (valid 60 days; refresh it before it expires) and put it in `IG_ACCESS_TOKEN`.
5. Put your Instagram user ID (the professional account ID, not your username) in `IG_USER_ID`.

Run `reelbot check`; it should print `Instagram account @yourname`.

By default videos are sent with Instagram's **resumable upload**, straight from your disk, so no public hosting is needed. If you'd rather Instagram fetch a public URL, set `instagram.upload_mode: url` and configure `hosting` (S3 or Cloudinary).

## Usage

```bash
reelbot topics                                    # list preset plots
reelbot generate --topic space                    # make a video from a preset
reelbot generate --prompt "a shy penguin who wants to see the desert"
reelbot generate --topic bedtime --post           # make it and post it
reelbot generate --story examples/sample_story.json   # render a story file without calling Claude
reelbot post output/20261026-150545-pip-and-the-lost-star
reelbot auto --dry-run                            # next topic in rotation, don't post
reelbot history
```

Each run writes a folder in `output/` with `video.mp4`, `caption.txt`, `story.json` and `thumbnail.jpg`. To tweak a story before posting, edit `story.json` and re-render it with `--story`.

### Topics

`topics.yaml` holds the preset plots: friendship, bedtime fable, space adventure, funny animals, never give up, kindness, little mystery and seasonal. Add your own:

```yaml
dragons:
  name: Tiny dragon
  description: A baby dragon who can't breathe fire yet finds another way to be a hero.
  mood: funny and sweet
  audience: kids
  hashtags: [dragon, kidsstories, animation]
```

## Posting automatically

You have two options.

**A. Your own computer or a server**: set `schedule.times` and `schedule.timezone` in `config.yaml`, then:

```bash
reelbot schedule        # runs forever; posts at each time, rotating topics
```

or call `reelbot auto` from cron, e.g. `30 9 * * * cd /path/to/warlord && reelbot auto`.

**B. GitHub Actions** (no machine to keep running): `.github/workflows/post-reel.yml` is included.

1. Add repository secrets `ANTHROPIC_API_KEY`, `IG_USER_ID` and `IG_ACCESS_TOKEN`.
2. Add the repository variable `REELBOT_ENABLED` = `true` to turn on the schedule (edit the `cron` lines for your times, in UTC).
3. You can also run it by hand from the Actions tab, with an optional topic or prompt. Every run uploads the video as a downloadable artifact.

Topic rotation uses `output/history.json` (kept in the Actions cache), so it picks the least recently used topic and tells Claude which titles it has already posted.

## Configuration

`config.yaml` holds all settings; anything you leave out uses the defaults in `reelbot/config.py`. The ones you're most likely to change:

| Setting | What it does |
|---|---|
| `claude.scenes` | scenes per story (4-7 keeps reels short) |
| `claude.language` | language for narration and caption |
| `tts.voice` | any edge-tts voice; list them with `edge-tts --list-voices` |
| `music.volume` | background music level under the voice |
| `instagram.always_hashtags` | tags added to every post |
| `instagram.max_hashtags` | cap on hashtags per post |
| `schedule.topics` | limit the rotation to some topic keys |

## Notes

- Instagram limits accounts to 50 API-published posts per 24 hours.
- Long-lived tokens expire after 60 days; `reelbot check` reports when yours stops working.
- Set `REELBOT_DEBUG=1` to see full tracebacks.
- Tests: `pip install pytest && pytest`.
