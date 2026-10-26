"""2D drawing primitives: skies, backgrounds, characters, props and effects.

Everything is laid out in a 1080x1920 coordinate space and multiplied by
`Canvas.s` so the same code renders at any 9:16 resolution.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

PALETTE = {
    "red": (226, 74, 74), "orange": (245, 145, 50), "yellow": (247, 207, 64),
    "green": (92, 184, 92), "teal": (48, 178, 170), "blue": (70, 130, 220),
    "purple": (150, 95, 205), "pink": (240, 128, 170), "brown": (150, 100, 60),
    "gray": (150, 150, 160), "white": (240, 240, 240), "black": (55, 55, 65),
}
OUTLINE = (40, 35, 50)
SKIN = (250, 205, 170)

SKIES = {
    "morning": [(255, 214, 170), (160, 205, 245)],
    "day": [(110, 175, 240), (200, 230, 255)],
    "sunset": [(70, 50, 120), (240, 120, 90), (255, 190, 110)],
    "night": [(10, 15, 45), (35, 45, 95)],
}

GROUND_Y = 1330  # feet line in 1080x1920 space
POSITION_X = {"left": 270, "center": 540, "right": 810}

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def load_font(size: int, path: str | None = None) -> ImageFont.FreeTypeFont:
    for p in ([path] if path else []) + FONT_CANDIDATES:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def mix(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def darker(c, f=0.75):
    return tuple(int(v * f) for v in c[:3])


def lighter(c, f=0.35):
    return mix(c[:3], (255, 255, 255), f)


@dataclass
class Canvas:
    w: int
    h: int

    @property
    def s(self) -> float:
        return self.w / 1080

    def p(self, *vals):
        """Scale 1080-space coordinates to pixels."""
        return [v * self.s for v in vals]


# ---------------------------------------------------------------- sky & land

def gradient(cv: Canvas, stops, top=0, bottom=None) -> Image.Image:
    bottom = cv.h if bottom is None else bottom
    img = Image.new("RGB", (1, 256))
    for y in range(256):
        t = y / 255 * (len(stops) - 1)
        i = min(int(t), len(stops) - 2)
        img.putpixel((0, y), mix(stops[i], stops[i + 1], t - i))
    return img.resize((cv.w, int(bottom - top)), Image.BILINEAR)


def effective_time(background: str, time_of_day: str) -> str:
    if background in ("space", "night_sky"):
        return "night"
    return time_of_day


def draw_background(cv: Canvas, background: str, time_of_day: str, seed: int) -> Image.Image:
    """Static scene layer (sky, scenery, ground)."""
    rnd = random.Random(seed)
    tod = effective_time(background, time_of_day)
    img = Image.new("RGB", (cv.w, cv.h))
    gy = GROUND_Y * cv.s
    sky = SKIES[tod] if background != "space" else [(5, 5, 20), (25, 15, 55)]
    img.paste(gradient(cv, sky, 0, gy + 60 * cv.s), (0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    P = cv.p

    if background != "room":
        _sun_or_moon(d, cv, tod)

    fn = BACKDROPS.get(background, _meadow)
    fn(d, cv, tod, rnd)

    # soft vignette band under the ground for subtitle readability
    d.rectangle(P(0, 1720, 1080, 1920), fill=(0, 0, 0, 60))
    return img


def _sun_or_moon(d, cv, tod):
    P = cv.p
    if tod == "night":
        # crescent: a full moon masked by an offset disc, so any sky shows through
        size = int(160 * cv.s)
        mask = Image.new("L", (size, size), 0)
        md = ImageDraw.Draw(mask)
        md.ellipse((0, 0, size - 1, size - 1), fill=255)
        md.ellipse((size * 0.3, -size * 0.12, size * 1.3, size * 0.88), fill=0)
        moon = Image.new("RGB", (size, size), (245, 240, 210))
        d._image.paste(moon, (int(820 * cv.s), int(520 * cv.s)), mask)
    elif tod == "sunset":
        d.ellipse(P(700, 900, 940, 1140), fill=(255, 170, 90, 200))
    elif tod == "morning":
        d.ellipse(P(120, 600, 300, 780), fill=(255, 225, 140))
    else:
        for r, a in ((150, 50), (110, 255)):
            d.ellipse(P(820 - r, 300 - r, 820 + r, 300 + r), fill=(255, 230, 110, a))


def _ground(d, cv, color, y=GROUND_Y - 30):
    d.rectangle(cv.p(0, y, 1080, 1920), fill=color)
    d.rectangle(cv.p(0, y, 1080, y + 14), fill=lighter(color, 0.15))


def _hills(d, cv, color, rnd, base=GROUND_Y - 20):
    for i in range(4):
        x = rnd.randint(-200, 1000)
        r = rnd.randint(300, 520)
        d.ellipse(cv.p(x, base - r * 0.45, x + 2 * r, base + r), fill=mix(color, (255, 255, 255), 0.12 * (i % 2)))


def _tree(d, cv, x, base, k=1.0, color=(70, 150, 70), snow=False):
    P = cv.p
    d.rectangle(P(x - 18 * k, base - 160 * k, x + 18 * k, base), fill=(120, 80, 50))
    for dx, dy, r in ((0, -260, 110), (-70, -200, 80), (70, -200, 80)):
        d.ellipse(P(x + dx * k - r * k, base + dy * k - r * k, x + dx * k + r * k, base + dy * k + r * k),
                  fill=color, outline=darker(color), width=max(1, int(4 * cv.s)))
    if snow:
        d.ellipse(P(x - 80 * k, base - 380 * k, x + 80 * k, base - 300 * k), fill=(250, 250, 255))


def _pine(d, cv, x, base, k=1.0, snow=False):
    P = cv.p
    d.rectangle(P(x - 14 * k, base - 60 * k, x + 14 * k, base), fill=(110, 75, 45))
    for i in range(3):
        top = base - (170 + i * 90) * k
        w = (120 - i * 30) * k
        d.polygon(P(x - w, top + 130 * k, x + w, top + 130 * k, x, top), fill=(40, 110, 70))
        if snow:
            d.polygon(P(x - w * 0.4, top + 50 * k, x + w * 0.4, top + 50 * k, x, top), fill=(250, 250, 255))


def _meadow(d, cv, tod, rnd):
    green = (110, 190, 90) if tod != "night" else (40, 80, 60)
    _hills(d, cv, darker(green, 0.9), rnd)
    _ground(d, cv, green)
    for _ in range(40):
        x, y = rnd.randint(0, 1080), rnd.randint(GROUND_Y, 1700)
        d.line(cv.p(x, y, x - 6, y - 22), fill=darker(green), width=int(4 * cv.s))


def _forest(d, cv, tod, rnd):
    g = (60, 140, 70) if tod != "night" else (25, 60, 45)
    for i in range(7):
        _tree(d, cv, 60 + i * 160 + rnd.randint(-30, 30), GROUND_Y - 20, 0.8 + rnd.random() * 0.4, darker(g, 0.85 + 0.15 * (i % 2)))
    _ground(d, cv, (90, 140, 60) if tod != "night" else (35, 60, 40))


def _city(d, cv, tod, rnd):
    x = -20
    while x < 1080:
        w, h = rnd.randint(110, 190), rnd.randint(350, 800)
        col = (90, 100, 130) if tod != "night" else (35, 40, 70)
        col = mix(col, (255, 255, 255), rnd.random() * 0.15)
        d.rectangle(cv.p(x, GROUND_Y - 20 - h, x + w, GROUND_Y), fill=col)
        for wy in range(int(GROUND_Y - h + 20), GROUND_Y - 60, 60):
            for wx in range(x + 18, x + w - 30, 42):
                lit = tod == "night" and rnd.random() < 0.6
                d.rectangle(cv.p(wx, wy, wx + 22, wy + 30),
                            fill=(255, 220, 120) if lit else (170, 190, 220, 160))
        x += w + rnd.randint(0, 20)
    _ground(d, cv, (120, 120, 130))
    for i in range(0, 1080, 160):
        d.rectangle(cv.p(i, 1560, i + 90, 1580), fill=(240, 240, 240))


def _beach(d, cv, tod, rnd):
    sea = (60, 150, 210) if tod != "night" else (20, 50, 90)
    d.rectangle(cv.p(0, 1050, 1080, GROUND_Y), fill=sea)
    for y in range(1080, GROUND_Y - 40, 50):
        d.arc(cv.p(rnd.randint(0, 900), y, rnd.randint(0, 900) + 160, y + 30), 200, 340, fill=lighter(sea), width=int(4 * cv.s))
    _ground(d, cv, (240, 215, 150))
    # palm tree
    P = cv.p
    d.line(P(960, GROUND_Y, 930, 900), fill=(140, 95, 55), width=int(30 * cv.s))
    for ang in (200, 240, 290, 330, 20):
        a = math.radians(ang)
        d.line(P(930, 900, 930 + 170 * math.cos(a), 900 + 90 * math.sin(a)), fill=(60, 160, 70), width=int(26 * cv.s))


def _ocean(d, cv, tod, rnd):
    sea = (50, 120, 200) if tod != "night" else (15, 40, 80)
    d.rectangle(cv.p(0, 950, 1080, 1920), fill=sea)
    for y in range(980, 1900, 70):
        for x in range(-40, 1080, 180):
            d.arc(cv.p(x + rnd.randint(0, 40), y, x + 140, y + 40), 200, 340, fill=lighter(sea), width=int(5 * cv.s))
    # wooden dock for characters to stand on
    d.rectangle(cv.p(60, GROUND_Y - 30, 1020, GROUND_Y + 40), fill=(150, 105, 65))
    for x in range(60, 1020, 80):
        d.line(cv.p(x, GROUND_Y - 30, x, GROUND_Y + 40), fill=(110, 75, 45), width=int(4 * cv.s))
    for x in (120, 540, 960):
        d.rectangle(cv.p(x - 15, GROUND_Y + 40, x + 15, GROUND_Y + 220), fill=(110, 75, 45))


def _space(d, cv, tod, rnd):
    P = cv.p
    d.ellipse(P(80, 300, 380, 600), fill=(200, 120, 90))
    d.arc(P(20, 410, 440, 490), 160, 380, fill=(240, 200, 150), width=int(12 * cv.s))
    d.ellipse(P(-300, GROUND_Y - 120, 1380, GROUND_Y + 1200), fill=(170, 170, 180))
    for _ in range(9):
        x, y, r = rnd.randint(0, 1000), rnd.randint(GROUND_Y - 40, 1750), rnd.randint(25, 70)
        d.ellipse(P(x, y, x + r * 2, y + r), fill=(140, 140, 152))


def _night_sky(d, cv, tod, rnd):
    _hills(d, cv, (25, 40, 50), rnd)
    _ground(d, cv, (30, 55, 50))


def _desert(d, cv, tod, rnd):
    sand = (235, 190, 120) if tod != "night" else (110, 85, 70)
    _hills(d, cv, darker(sand, 0.92), rnd)
    _ground(d, cv, sand)
    P = cv.p
    for x in (150, 900):
        d.rounded_rectangle(P(x - 25, 1000, x + 25, GROUND_Y), radius=25 * cv.s, fill=(70, 150, 80))
        d.rounded_rectangle(P(x - 85, 1080, x - 55, 1180), radius=15 * cv.s, fill=(70, 150, 80))
        d.rectangle(P(x - 85, 1160, x - 20, 1185), fill=(70, 150, 80))


def _snow(d, cv, tod, rnd):
    for i in range(6):
        _pine(d, cv, 80 + i * 190 + rnd.randint(-30, 30), GROUND_Y - 20, 0.9 + rnd.random() * 0.4, snow=True)
    _ground(d, cv, (235, 240, 250) if tod != "night" else (170, 180, 210))


def _mountains(d, cv, tod, rnd):
    P = cv.p
    rock = (110, 115, 140) if tod != "night" else (45, 50, 75)
    for x, h in ((-100, 650), (300, 820), (700, 600)):
        d.polygon(P(x, GROUND_Y, x + 550, GROUND_Y, x + 275, GROUND_Y - h), fill=rock)
        d.polygon(P(x + 205, GROUND_Y - h + 140, x + 345, GROUND_Y - h + 140, x + 275, GROUND_Y - h), fill=(245, 245, 250))
    _ground(d, cv, (100, 170, 90) if tod != "night" else (35, 70, 50))


def _room(d, cv, tod, rnd):
    P = cv.p
    d.rectangle(P(0, 0, 1080, GROUND_Y), fill=(235, 215, 185))
    for x in range(0, 1080, 90):
        d.rectangle(P(x, 0, x + 45, GROUND_Y), fill=(228, 205, 175))
    # window shows the time of day
    win = gradient(Canvas(int(380 * cv.s), int(380 * cv.s)), SKIES[tod])
    d._image.paste(win, (int(350 * cv.s), int(380 * cv.s)))
    d.rectangle(P(350, 380, 730, 760), outline=(120, 85, 55), width=int(18 * cv.s))
    d.line(P(540, 380, 540, 760), fill=(120, 85, 55), width=int(12 * cv.s))
    d.line(P(350, 570, 730, 570), fill=(120, 85, 55), width=int(12 * cv.s))
    d.rectangle(P(90, 450, 250, 640), fill=(200, 120, 90), outline=(120, 85, 55), width=int(10 * cv.s))
    _ground(d, cv, (170, 120, 80))
    d.ellipse(P(200, GROUND_Y + 60, 880, GROUND_Y + 220), fill=(190, 80, 90))
    if tod == "night":
        d.rectangle(P(0, 0, 1080, 1920), fill=(10, 10, 40, 90))


def _castle(d, cv, tod, rnd):
    P = cv.p
    stone = (170, 165, 185) if tod != "night" else (70, 70, 100)
    d.rectangle(P(240, 700, 840, GROUND_Y), fill=stone)
    for x in (180, 780):
        d.rectangle(P(x, 550, x + 120, GROUND_Y), fill=darker(stone, 0.9))
        d.polygon(P(x - 15, 550, x + 135, 550, x + 60, 400), fill=(170, 70, 90))
        d.line(P(x + 60, 400, x + 60, 340), fill=OUTLINE, width=int(5 * cv.s))
        d.polygon(P(x + 60, 340, x + 110, 360, x + 60, 380), fill=(240, 200, 70))
    for x in range(240, 840, 60):
        d.rectangle(P(x, 660, x + 35, 700), fill=stone)
    d.chord(P(460, 1050, 620, 1300), 180, 360, fill=(90, 60, 40))
    d.rectangle(P(460, 1175, 620, GROUND_Y), fill=(90, 60, 40))
    _ground(d, cv, (100, 170, 90) if tod != "night" else (35, 70, 50))


BACKDROPS = {
    "meadow": _meadow, "forest": _forest, "city": _city, "beach": _beach,
    "ocean": _ocean, "space": _space, "night_sky": _night_sky, "desert": _desert,
    "snow": _snow, "mountains": _mountains, "room": _room, "castle": _castle,
}


# ---------------------------------------------------------------- props

GROUND_PROP_SLOTS = [120, 400, 680, 960]
SKY_PROPS = {"star", "heart", "cloud"}


def draw_ground_prop(d, cv, kind, x, base=GROUND_Y):
    P = cv.p
    w = max(1, int(5 * cv.s))
    if kind == "tree":
        _tree(d, cv, x, base, 1.0)
    elif kind == "house":
        d.rectangle(P(x - 130, base - 230, x + 130, base), fill=(230, 180, 120), outline=OUTLINE, width=w)
        d.polygon(P(x - 160, base - 230, x + 160, base - 230, x, base - 380), fill=(190, 70, 60), outline=OUTLINE)
        d.rectangle(P(x - 35, base - 120, x + 35, base), fill=(120, 80, 50))
        d.rectangle(P(x + 60, base - 190, x + 110, base - 140), fill=(160, 210, 250), outline=OUTLINE, width=w)
    elif kind == "rock":
        d.ellipse(P(x - 90, base - 90, x + 90, base + 10), fill=(140, 140, 150), outline=OUTLINE, width=w)
    elif kind == "flower":
        for dx in (-40, 0, 40):
            d.line(P(x + dx, base, x + dx, base - 90), fill=(60, 140, 60), width=int(7 * cv.s))
            for a in range(0, 360, 72):
                r = math.radians(a)
                cx, cy = x + dx + 18 * math.cos(r), base - 95 + 18 * math.sin(r)
                d.ellipse(P(cx - 14, cy - 14, cx + 14, cy + 14), fill=(240, 120, 170))
            d.ellipse(P(x + dx - 10, base - 105, x + dx + 10, base - 85), fill=(250, 210, 60))
    elif kind in ("gift", "treasure"):
        col = (220, 70, 90) if kind == "gift" else (150, 95, 45)
        d.rectangle(P(x - 70, base - 110, x + 70, base), fill=col, outline=OUTLINE, width=w)
        d.rectangle(P(x - 80, base - 140, x + 80, base - 100), fill=darker(col, 0.85), outline=OUTLINE, width=w)
        band = (250, 210, 70)
        d.rectangle(P(x - 12, base - 140, x + 12, base), fill=band)
        if kind == "treasure":
            d.ellipse(P(x - 50, base - 175, x + 50, base - 125), fill=(255, 215, 80))
    elif kind == "lamp":
        d.rectangle(P(x - 10, base - 360, x + 10, base), fill=(60, 60, 70))
        d.ellipse(P(x - 45, base - 410, x + 45, base - 330), fill=(255, 230, 140), outline=OUTLINE, width=w)
    elif kind == "rocket":
        d.polygon(P(x - 60, base - 60, x - 120, base, x - 40, base), fill=(220, 70, 70))
        d.polygon(P(x + 60, base - 60, x + 120, base, x + 40, base), fill=(220, 70, 70))
        d.rounded_rectangle(P(x - 60, base - 330, x + 60, base - 20), radius=50 * cv.s, fill=(235, 235, 245), outline=OUTLINE, width=w)
        d.polygon(P(x - 60, base - 290, x + 60, base - 290, x, base - 420), fill=(220, 70, 70), outline=OUTLINE)
        d.ellipse(P(x - 30, base - 250, x + 30, base - 190), fill=(110, 180, 240), outline=OUTLINE, width=w)
    elif kind == "umbrella":
        d.line(P(x, base, x, base - 260), fill=OUTLINE, width=int(8 * cv.s))
        d.pieslice(P(x - 130, base - 340, x + 130, base - 180), 180, 360, fill=(80, 140, 230), outline=OUTLINE)
    elif kind == "book":
        d.polygon(P(x - 80, base - 20, x, base - 5, x, base - 90, x - 80, base - 105), fill=(250, 250, 240), outline=OUTLINE)
        d.polygon(P(x + 80, base - 20, x, base - 5, x, base - 90, x + 80, base - 105), fill=(245, 245, 235), outline=OUTLINE)
        d.rectangle(P(x - 85, base - 20, x + 85, base), fill=(70, 110, 200))
    elif kind == "cake":
        d.rectangle(P(x - 90, base - 110, x + 90, base), fill=(250, 220, 230), outline=OUTLINE, width=w)
        d.rectangle(P(x - 90, base - 110, x + 90, base - 80), fill=(240, 120, 160))
        for dx in (-40, 0, 40):
            d.rectangle(P(x + dx - 6, base - 160, x + dx + 6, base - 110), fill=(120, 170, 240))
            d.ellipse(P(x + dx - 9, base - 185, x + dx + 9, base - 160), fill=(255, 190, 60))
    elif kind == "ball":
        d.ellipse(P(x - 50, base - 100, x + 50, base), fill=(240, 90, 80), outline=OUTLINE, width=w)
        d.arc(P(x - 50, base - 75, x + 50, base - 25), 0, 180, fill=(255, 255, 255), width=int(8 * cv.s))


def draw_sky_prop(d, cv, kind, x, y, t):
    P = cv.p
    bob = math.sin(t * 2 + x) * 15
    y += bob
    if kind == "star":
        pts = []
        for i in range(10):
            r = 60 if i % 2 == 0 else 26
            a = math.radians(-90 + i * 36)
            pts += [x + r * math.cos(a), y + r * math.sin(a)]
        d.polygon(P(*pts), fill=(255, 220, 80), outline=OUTLINE)
    elif kind == "heart":
        _heart(d, cv, x, y, 55, (235, 80, 110))
    elif kind == "cloud":
        cloud(d, cv, x, y, 1.0, (255, 255, 255, 230))


def _heart(d, cv, x, y, r, col):
    P = cv.p
    d.ellipse(P(x - r, y - r * 0.6, x, y + r * 0.4), fill=col)
    d.ellipse(P(x, y - r * 0.6, x + r, y + r * 0.4), fill=col)
    d.polygon(P(x - r * 0.97, y - 0.0, x + r * 0.97, y - 0.0, x, y + r * 1.1), fill=col)


def cloud(d, cv, x, y, k, col):
    P = cv.p
    for dx, dy, r in ((0, 0, 60), (60, -25, 70), (125, 0, 55), (60, 20, 60)):
        d.ellipse(P(x + (dx - r) * k, y + (dy - r) * k, x + (dx + r) * k, y + (dy + r) * k), fill=col)


# ---------------------------------------------------------------- characters

def draw_character(d, cv, kind, color_name, x, t, action, facing=1, k=1.0, local_t=0.0):
    """Draw a character whose feet sit at (x, GROUND_Y).

    `t` is global time (for blinking), `local_t` the time since the scene began.
    """
    P = cv.p
    col = PALETTE.get(color_name, PALETTE["blue"])
    lw = max(1, int(5 * cv.s))
    base = GROUND_Y

    # --- motion per action
    y_off, x_off, arm_l, arm_r, leg_phase, lean = 0.0, 0.0, 200, 340, 0.0, 0.0
    mouth = "smile"
    eyes = "open"
    if action == "jump":
        y_off = -abs(math.sin(local_t * 4)) * 140
        arm_l, arm_r = 220, 320
    elif action == "wave":
        arm_r = 60 + math.sin(local_t * 9) * 30
    elif action == "dance":
        x_off = math.sin(local_t * 6) * 35
        y_off = -abs(math.sin(local_t * 6)) * 40
        arm_l = 200 + math.sin(local_t * 6) * 40 - 40
        arm_r = 340 + math.sin(local_t * 6 + 1) * 40 + 40
        lean = math.sin(local_t * 6) * 0.15
    elif action == "celebrate":
        y_off = -abs(math.sin(local_t * 5)) * 100
        arm_l, arm_r = 135, 45
        mouth = "open"
    elif action in ("walk_left", "walk_right"):
        y_off = -abs(math.sin(local_t * 8)) * 18
        leg_phase = math.sin(local_t * 8)
    elif action == "sleep":
        eyes = "closed"
        mouth = "flat"
        y_off = math.sin(local_t * 1.5) * 4
    elif action == "shiver":
        x_off = math.sin(local_t * 60) * 6
        mouth = "flat"
    elif action == "sad":
        mouth = "frown"
        eyes = "down"
        arm_l, arm_r = 250, 290
    elif action == "talk":
        mouth = "talk"
    else:  # idle
        y_off = math.sin(local_t * 2.5) * 6

    if eyes == "open" and (t * 1000) % 3700 < 140:
        eyes = "closed"

    x = x + x_off
    by = base + y_off

    def S(v):  # character scale
        return v * k

    # shadow
    d.ellipse(P(x - S(90), base - S(12), x + S(90), base + S(14)), fill=(0, 0, 0, 50))

    head_r = S(78)
    if kind == "robot":
        body = (x - S(85), by - S(230), x + S(85), by - S(40))
        hcx, hcy = x, by - S(300)
    elif kind == "bird":
        body = (x - S(95), by - S(210), x + S(95), by - S(20))
        hcx, hcy = x + facing * S(10), by - S(250)
    else:
        body = (x - S(80), by - S(215), x + S(80), by - S(30))
        hcx, hcy = x + lean * S(80), by - S(290)

    body_col = col
    head_col = SKIN if kind == "person" else (PALETTE["orange"] if kind == "fox" else col)

    # tails behind body
    if kind == "cat":
        d.arc(P(x - facing * S(170), by - S(200), x - facing * S(40), by - S(40)), 90, 270 if facing > 0 else 450,
              fill=darker(col), width=int(S(16) * cv.s))
    elif kind == "fox":
        tx = x - facing * S(110)
        d.ellipse(P(tx - S(70), by - S(170), tx + S(70), by - S(60)), fill=PALETTE["orange"], outline=OUTLINE, width=lw)
        d.ellipse(P(tx - facing * S(40) - S(30), by - S(150), tx - facing * S(40) + S(30), by - S(90)), fill=(250, 250, 250))
    elif kind == "dog":
        d.line(P(x - facing * S(70), by - S(120), x - facing * S(130), by - S(180 + 20 * math.sin(local_t * 12))),
               fill=darker(col), width=int(S(16) * cv.s))

    # legs
    if kind != "bird":
        for side, ph in ((-1, leg_phase), (1, -leg_phase)):
            lx = x + side * S(40) + ph * S(25)
            d.rounded_rectangle(P(lx - S(22), by - S(70), lx + S(22), base if y_off > -5 else by), radius=S(18) * cv.s,
                                fill=darker(body_col, 0.65 if kind == "person" else 0.8), outline=OUTLINE, width=lw)
    else:
        for side in (-1, 1):
            lx = x + side * S(30)
            d.line(P(lx, by - S(30), lx, by), fill=(240, 160, 50), width=int(S(8) * cv.s))

    # arms
    def arm(angle_deg, side):
        sx = x + side * S(70)
        sy = by - S(160)
        a = math.radians(angle_deg)
        ex, ey = sx + math.cos(a) * S(95), sy - math.sin(a) * S(95)
        d.line(P(sx, sy, ex, ey), fill=darker(body_col) if kind != "person" else SKIN, width=int(S(22) * cv.s))
        d.ellipse(P(ex - S(16), ey - S(16), ex + S(16), ey + S(16)),
                  fill=SKIN if kind == "person" else darker(body_col), outline=OUTLINE, width=lw)

    if kind == "bird":
        flap = math.sin(local_t * (14 if action in ("jump", "celebrate", "dance") else 3)) * 20
        for side in (-1, 1):
            wx = x + side * S(95)
            d.ellipse(P(wx - S(35), by - S(170) - flap, wx + S(35), by - S(70) - flap), fill=darker(col), outline=OUTLINE, width=lw)
    else:
        # angles in degrees: 0 = pointing right, 90 = up, 180 = left, 270 = down
        arm(arm_l, -1)
        arm(arm_r, 1)

    # body
    if kind == "robot":
        d.rounded_rectangle(P(*body), radius=S(20) * cv.s, fill=body_col, outline=OUTLINE, width=lw)
        d.rectangle(P(x - S(40), by - S(170), x + S(40), by - S(100)), fill=lighter(body_col), outline=OUTLINE, width=lw)
        blink = (255, 80, 80) if int(t * 2) % 2 else (120, 255, 120)
        d.ellipse(P(x - S(12), by - S(150), x + S(12), by - S(126)), fill=blink)
    else:
        d.ellipse(P(*body), fill=body_col, outline=OUTLINE, width=lw)
        if kind in ("cat", "dog", "bear", "fox", "bird"):
            belly = (250, 245, 235) if kind != "bear" else lighter(col, 0.4)
            d.ellipse(P(x - S(50), by - S(170), x + S(50), by - S(45)), fill=belly)

    # head
    if kind == "robot":
        d.rounded_rectangle(P(hcx - S(80), hcy - S(70), hcx + S(80), hcy + S(65)), radius=S(18) * cv.s,
                            fill=lighter(body_col, 0.2), outline=OUTLINE, width=lw)
        d.line(P(hcx, hcy - S(70), hcx, hcy - S(120)), fill=OUTLINE, width=lw)
        d.ellipse(P(hcx - S(14), hcy - S(140), hcx + S(14), hcy - S(112)), fill=(255, 90, 90))
    else:
        # ears
        if kind in ("cat", "fox"):
            ec = head_col
            for side in (-1, 1):
                ex = hcx + side * S(48)
                d.polygon(P(ex - S(35), hcy - S(45), ex + S(35), hcy - S(45), ex + side * S(10), hcy - S(125)),
                          fill=ec, outline=OUTLINE)
        elif kind == "bear":
            for side in (-1, 1):
                ex = hcx + side * S(58)
                d.ellipse(P(ex - S(32), hcy - S(95), ex + S(32), hcy - S(35)), fill=head_col, outline=OUTLINE, width=lw)
        elif kind == "monster":
            for side in (-1, 1):
                ex = hcx + side * S(45)
                d.polygon(P(ex - S(18), hcy - S(55), ex + S(18), hcy - S(55), ex + side * S(25), hcy - S(130)),
                          fill=(250, 240, 220), outline=OUTLINE)
        elif kind == "alien":
            for side in (-1, 1):
                ex = hcx + side * S(40)
                d.line(P(ex, hcy - S(60), ex + side * S(25), hcy - S(130)), fill=OUTLINE, width=lw)
                d.ellipse(P(ex + side * S(25) - S(14), hcy - S(144), ex + side * S(25) + S(14), hcy - S(116)), fill=(200, 255, 120))
        hr = head_r * (1.1 if kind == "alien" else 1.0)
        d.ellipse(P(hcx - hr, hcy - hr * (1.05 if kind == "alien" else 0.92), hcx + hr, hcy + hr * 0.92),
                  fill=head_col, outline=OUTLINE, width=lw)
        if kind == "dog":
            for side in (-1, 1):
                ex = hcx + side * S(78)
                d.ellipse(P(ex - S(28), hcy - S(55), ex + S(28), hcy + S(35)), fill=darker(col, 0.7), outline=OUTLINE, width=lw)
        if kind == "fox":
            d.ellipse(P(hcx - S(45), hcy + S(5), hcx + S(45), hcy + S(70)), fill=(250, 250, 250))
        if kind == "bear":
            d.ellipse(P(hcx - S(35), hcy + S(5), hcx + S(35), hcy + S(55)), fill=lighter(col, 0.45))
        if kind == "person":
            hair = darker(col, 0.55)
            d.chord(P(hcx - hr - S(4), hcy - hr - S(6), hcx + hr + S(4), hcy + S(20)), 180, 360, fill=hair)

    # face
    ex_off = facing * S(8)
    eye_y = hcy - S(12)
    for side in (-1, 1):
        ex = hcx + side * S(30) + ex_off
        if kind == "robot":
            d.rectangle(P(ex - S(16), eye_y - S(14), ex + S(16), eye_y + S(14)), fill=(120, 230, 255), outline=OUTLINE, width=lw)
        elif eyes == "closed":
            d.arc(P(ex - S(16), eye_y - S(12), ex + S(16), eye_y + S(12)), 0, 180, fill=OUTLINE, width=lw)
        else:
            d.ellipse(P(ex - S(17), eye_y - S(19), ex + S(17), eye_y + S(19)), fill=(255, 255, 255), outline=OUTLINE, width=lw)
            py = eye_y + (S(7) if eyes == "down" else 0)
            d.ellipse(P(ex + ex_off - S(9), py - S(9), ex + ex_off + S(9), py + S(9)), fill=OUTLINE)
    if kind in ("cat", "dog", "fox", "bear"):
        d.ellipse(P(hcx + ex_off - S(12), hcy + S(14), hcx + ex_off + S(12), hcy + S(30)), fill=OUTLINE)
    if kind == "cat":
        for side in (-1, 1):
            for dy in (-6, 8):
                d.line(P(hcx + side * S(30), hcy + S(28), hcx + side * S(85), hcy + S(28 + dy)), fill=OUTLINE, width=max(1, lw // 2))
    if kind == "bird":
        d.polygon(P(hcx + facing * S(70), hcy + S(5), hcx + facing * S(70), hcy + S(35), hcx + facing * S(115), hcy + S(20)),
                  fill=(250, 170, 40), outline=OUTLINE)
    if action == "sad":
        d.ellipse(P(hcx + S(38), eye_y + S(20), hcx + S(50), eye_y + S(40)), fill=(120, 190, 255))

    my = hcy + S(45)
    mx = hcx + ex_off
    if kind == "bird":
        pass  # the beak is the mouth
    elif mouth == "talk":
        open_h = (math.sin(local_t * 16) * 0.5 + 0.5) * S(22) + S(4)
        d.ellipse(P(mx - S(18), my - open_h / 2, mx + S(18), my + open_h / 2), fill=(120, 40, 50), outline=OUTLINE, width=lw)
    elif mouth == "open":
        d.chord(P(mx - S(24), my - S(20), mx + S(24), my + S(20)), 0, 180, fill=(120, 40, 50), outline=OUTLINE)
    elif mouth == "frown":
        d.arc(P(mx - S(22), my, mx + S(22), my + S(26)), 200, 340, fill=OUTLINE, width=lw)
    elif mouth == "flat":
        d.line(P(mx - S(15), my + S(4), mx + S(15), my + S(4)), fill=OUTLINE, width=lw)
    else:
        d.arc(P(mx - S(24), my - S(18), mx + S(24), my + S(12)), 20, 160, fill=OUTLINE, width=lw)
    if kind == "monster":
        for side in (-1, 1):
            d.polygon(P(mx + side * S(14) - S(6), my + S(6), mx + side * S(14) + S(6), my + S(6), mx + side * S(14), my + S(20)), fill=(255, 255, 255))

    if action == "sleep":
        font = load_font(int(S(48) * cv.s))
        for i in range(3):
            ph = (local_t * 0.6 + i / 3) % 1
            d.text(P(hcx + S(70) + ph * S(60), hcy - S(80) - ph * S(140)), "z", font=font,
                   fill=(255, 255, 255, int(255 * (1 - ph))), stroke_width=int(3 * cv.s), stroke_fill=OUTLINE)

    return hcx, hcy - head_r


# ---------------------------------------------------------------- effects

def draw_effect(d, cv, effect, t, seed):
    if effect == "none":
        return
    rnd = random.Random(seed)
    P = cv.p
    n = {"rain": 90, "snow": 70, "sparkles": 30, "confetti": 80, "hearts": 14, "stars": 25}.get(effect, 0)
    for i in range(n):
        x0, y0 = rnd.uniform(0, 1080), rnd.uniform(0, 1920)
        sp = rnd.uniform(0.6, 1.4)
        if effect == "rain":
            y = (y0 + t * 1400 * sp) % 1920
            d.line(P(x0, y, x0 - 8, y + 45), fill=(170, 200, 255, 180), width=max(1, int(4 * cv.s)))
        elif effect == "snow":
            y = (y0 + t * 140 * sp) % 1920
            x = x0 + math.sin(t * 1.5 + i) * 25
            r = 6 + 6 * sp
            d.ellipse(P(x - r, y - r, x + r, y + r), fill=(255, 255, 255, 220))
        elif effect == "confetti":
            y = (y0 + t * 450 * sp) % 1920
            x = x0 + math.sin(t * 3 + i) * 30
            col = list(PALETTE.values())[i % 9]
            w = 10 + 8 * abs(math.sin(t * 6 + i))
            d.rectangle(P(x - w, y - 8, x + w, y + 8), fill=col)
        elif effect == "hearts":
            y = 1920 - (y0 + t * 160 * sp) % 1920
            _heart(d, cv, x0 + math.sin(t * 2 + i) * 30, y, 22 + 10 * sp, (240, 90, 130, 200))
        elif effect in ("sparkles", "stars"):
            if effect == "stars":
                y0 = y0 * 0.55
            a = abs(math.sin(t * 3 * sp + i))
            r = (10 + 18 * a) * (1.4 if effect == "stars" else 1)
            col = (255, 240, 170, int(80 + 175 * a))
            d.polygon(P(x0, y0 - r, x0 + r * 0.25, y0 - r * 0.25, x0 + r, y0, x0 + r * 0.25, y0 + r * 0.25,
                        x0, y0 + r, x0 - r * 0.25, y0 + r * 0.25, x0 - r, y0, x0 - r * 0.25, y0 - r * 0.25), fill=col)


def draw_ambient(d, cv, background, time_of_day, t, seed):
    """Always-on subtle motion: drifting clouds by day, twinkling stars by night."""
    tod = effective_time(background, time_of_day)
    rnd = random.Random(seed + 7)
    if background == "room":
        return
    if tod == "night":
        for i in range(45):
            x, y = rnd.uniform(0, 1080), rnd.uniform(0, 900)
            a = 0.5 + 0.5 * math.sin(t * rnd.uniform(1, 3) + i)
            r = rnd.uniform(2, 5)
            d.ellipse(cv.p(x - r, y - r, x + r, y + r), fill=(255, 255, 230, int(100 + 155 * a)))
    else:
        for i in range(3):
            y = rnd.uniform(150, 650)
            k = rnd.uniform(0.8, 1.4)
            x = (rnd.uniform(0, 1300) + t * 25 * k) % 1500 - 250
            cloud(d, cv, x, y, k, (255, 255, 255, 210))


# ---------------------------------------------------------------- text

def wrap(text, font, max_w, d):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if d.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def draw_text_block(d, cv, text, cy, size, max_w=920, fill=(255, 255, 255), stroke=OUTLINE,
                    box=None, font_path=None, alpha=255):
    font = load_font(int(size * cv.s), font_path)
    lines = wrap(text, font, max_w * cv.s, d)
    lh = size * 1.25 * cv.s
    total = lh * len(lines)
    y = cy * cv.s - total / 2
    if box and lines:
        widest = max(d.textlength(line, font=font) for line in lines)
        pad = 28 * cv.s
        d.rounded_rectangle((cv.w / 2 - widest / 2 - pad, y - pad * 0.6, cv.w / 2 + widest / 2 + pad, y + total + pad * 0.4),
                            radius=30 * cv.s, fill=box)
    for line in lines:
        w = d.textlength(line, font=font)
        d.text((cv.w / 2 - w / 2, y), line, font=font, fill=fill[:3] + (alpha,),
               stroke_width=max(1, int(size * 0.08 * cv.s)), stroke_fill=stroke[:3] + (alpha,))
        y += lh


def speech_bubble(d, cv, text, x, top_y, alpha=255, font_path=None):
    font = load_font(int(40 * cv.s), font_path)
    lines = wrap(text, font, 380 * cv.s, d)
    if not lines:
        return
    lh = 50 * cv.s
    w = max(d.textlength(line, font=font) for line in lines) + 50 * cv.s
    h = lh * len(lines) + 34 * cv.s
    cx = min(max(x * cv.s, w / 2 + 20 * cv.s), cv.w - w / 2 - 20 * cv.s)
    by = top_y * cv.s - 40 * cv.s
    box = (cx - w / 2, by - h, cx + w / 2, by)
    fill = (255, 255, 255, alpha)
    d.rounded_rectangle(box, radius=26 * cv.s, fill=fill, outline=OUTLINE[:3] + (alpha,), width=max(1, int(4 * cv.s)))
    tx = x * cv.s
    d.polygon([(tx - 18 * cv.s, by - 2), (tx + 18 * cv.s, by - 2), (tx, by + 34 * cv.s)], fill=fill)
    y = by - h + 17 * cv.s
    for line in lines:
        lw_ = d.textlength(line, font=font)
        d.text((cx - lw_ / 2, y), line, font=font, fill=OUTLINE[:3] + (alpha,))
        y += lh
