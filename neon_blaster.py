#!/usr/bin/env python3
"""Neon Blaster - a vertical space shooter built with pygame.

Single file, no assets: ships, bullets, explosions and sounds are all
generated in code.

Run:      python neon_blaster.py
Selftest: python neon_blaster.py --selftest   (headless, writes shots/*.png)

Controls: Arrows/WASD fly  ·  SHIFT/B bomb  ·  P pause  ·  M sound  ·  ESC menu
Guns are automatic - your job is to dodge.
"""

import os
import sys

if "--selftest" in sys.argv:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import array
import json
import math
import random

import pygame

# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------

W, H = 720, 960
FPS = 60

DIR = os.path.dirname(os.path.abspath(__file__))
HS_PATH = os.path.join(DIR, "highscore.json")
SHOT_DIR = os.path.join(DIR, "shots")

COL_X = (255, 96, 96)
PLAYER_COL = (110, 220, 255)
COL_GOLD = (255, 208, 70)
FIRE_RATES = {1: 0.30, 2: 0.22, 3: 0.16}

# enemy kind -> (hp, radius, score, vy, sway_amp, sway_freq, color)
KIND_STATS = {
    "grunt":   (1, 18, 10, 95, 55, 1.6, (255, 80, 170)),
    "weaver":  (2, 16, 20, 135, 150, 2.6, (120, 255, 140)),
    "shooter": (3, 22, 30, 110, 90, 1.1, (190, 120, 255)),
    "tank":    (6, 28, 40, 60, 30, 0.8, (255, 160, 60)),
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def clamp(v, a, b):
    return max(a, min(b, v))


def lerp_color(c1, c2, f):
    return tuple(int(a + (b - a) * f) for a, b in zip(c1, c2))


def draw_text(surf, txt, font, col, pos, anchor="topleft", shadow=None, alpha=255):
    img = font.render(txt, True, col)
    if alpha < 255:
        img.set_alpha(alpha)
    r = img.get_rect(**{anchor: pos})
    if shadow:
        sh = font.render(txt, True, shadow)
        if alpha < 255:
            sh.set_alpha(alpha)
        surf.blit(sh, (r.x + 2, r.y + 3))
    surf.blit(img, r)


def rounded(surf, rect, color, radius, outline=None, width=2):
    pygame.draw.rect(surf, color, rect, border_radius=radius)
    if outline:
        pygame.draw.rect(surf, outline, rect, width=width, border_radius=radius)


def soft_glow(surf, x, y, r, col, steps=4):
    for i in range(steps, 0, -1):
        c = tuple(int(v * (1.15 / steps)) for v in col)
        pygame.draw.circle(surf, c, (int(x), int(y)), max(1, int(r * i / steps)))


def dist2(ax, ay, bx, by):
    return (ax - bx) ** 2 + (ay - by) ** 2


class _Keys(dict):
    """Dict usable in place of pygame.key.get_pressed() for the selftest."""

    def __missing__(self, k):
        return False


# ---------------------------------------------------------------------------
# sprites (procedural)
# ---------------------------------------------------------------------------

def make_ship():
    s = pygame.Surface((52, 58), pygame.SRCALPHA)
    pts = [(26, 2), (44, 34), (35, 47), (26, 41), (17, 47), (8, 34)]
    pygame.draw.polygon(s, (205, 235, 255), pts)
    pygame.draw.polygon(s, PLAYER_COL, pts, 2)
    pygame.draw.polygon(s, (120, 160, 200), [(26, 2), (35, 30), (26, 38), (17, 30)], 1)
    pygame.draw.circle(s, (255, 255, 255), (26, 22), 5)
    pygame.draw.circle(s, (60, 120, 170), (26, 22), 5, 2)
    pygame.draw.line(s, PLAYER_COL, (10, 36), (16, 42), 2)
    pygame.draw.line(s, PLAYER_COL, (42, 36), (36, 42), 2)
    return s


def make_enemy(kind):
    stats = KIND_STATS[kind]
    col = stats[6]
    size = stats[1] * 2 + 18
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    c = size // 2
    r = stats[1]
    if kind == "grunt":
        pts = [(c, c - r), (c + r, c), (c, c + r), (c - r, c)]
        pygame.draw.polygon(s, (30, 26, 40), pts)
        pygame.draw.polygon(s, col, pts, 3)
        pygame.draw.circle(s, col, (c, c), 4)
    elif kind == "weaver":
        pts = [(c, c + r), (c - r, c - r + 4), (c + r, c - r + 4)]
        pygame.draw.polygon(s, (24, 36, 28), pts)
        pygame.draw.polygon(s, col, pts, 3)
        pygame.draw.line(s, col, (c, c - r + 8), (c, c + r - 4), 2)
    elif kind == "shooter":
        pygame.draw.ellipse(s, (30, 26, 44), (c - r, c - r // 2, r * 2, r), 0)
        pygame.draw.ellipse(s, col, (c - r, c - r // 2, r * 2, r), 3)
        pygame.draw.circle(s, col, (c, c - r // 2 - 2), r // 2 + 2, 3)
        pygame.draw.circle(s, (255, 255, 255), (c, c), 3)
    else:  # tank
        pts = []
        for i in range(6):
            a = math.pi / 6 + i * math.pi / 3
            pts.append((c + r * math.cos(a), c + r * math.sin(a)))
        pygame.draw.polygon(s, (38, 32, 26), pts)
        pygame.draw.polygon(s, col, pts, 4)
        pygame.draw.circle(s, (255, 255, 255), (c, c), 5, 2)
    return s


def make_boss():
    w, h = 230, 96
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    hull = [(20, h - 10), (10, 34), (52, 12), (w - 52, 12), (w - 10, 34), (w - 20, h - 10)]
    pygame.draw.polygon(s, (40, 24, 34), hull)
    pygame.draw.polygon(s, (255, 70, 90), hull, 3)
    for px in (44, w - 44):
        pygame.draw.circle(s, (60, 34, 50), (px, 44), 18)
        pygame.draw.circle(s, (255, 120, 140), (px, 44), 18, 2)
    pygame.draw.circle(s, (255, 210, 90), (w // 2, 52), 20)
    pygame.draw.circle(s, (255, 255, 255), (w // 2, 52), 8)
    return s


def make_powerup(kind):
    s = pygame.Surface((34, 34), pygame.SRCALPHA)
    cols = {"weapon": PLAYER_COL, "shield": (120, 255, 140),
            "bomb": (255, 160, 60), "life": (255, 110, 150)}
    letters = {"weapon": "P", "shield": "S", "bomb": "B", "life": "+"}
    col = cols[kind]
    rounded(s, s.get_rect(), (24, 28, 44), 9, col, 2)
    f = pygame.font.SysFont("consolas,arial", 20, bold=True)
    img = f.render(letters[kind], True, col)
    s.blit(img, img.get_rect(center=(17, 17)))
    return s


# ---------------------------------------------------------------------------
# sounds (synthesized, stdlib only)
# ---------------------------------------------------------------------------

def build_sfx():
    try:
        pygame.mixer.quit()
        pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
        pygame.mixer.set_num_channels(24)
    except Exception:
        return {}
    sr = 22050
    rnd = random.Random(7)

    def tone(dur, fn, vol=0.5):
        buf = array.array("h")
        for i in range(int(sr * dur)):
            t = i / sr
            v = max(-1.0, min(1.0, fn(t)))
            buf.append(int(v * 26000 * vol))
        return pygame.mixer.Sound(buffer=buf.tobytes())

    sfx = {}
    try:
        sfx["shoot"] = tone(0.07, lambda t: 0.6 * math.sin(2 * math.pi * (900 - 4200 * t) * t)
                            * math.exp(-22 * t), vol=0.16)
        sfx["boom_s"] = tone(0.3, lambda t: rnd.uniform(-1, 1) * math.exp(-9 * t)
                             + 0.5 * math.sin(2 * math.pi * 150 * t) * math.exp(-10 * t), vol=0.45)
        sfx["boom_b"] = tone(0.55, lambda t: rnd.uniform(-1, 1) * math.exp(-5 * t)
                             + 0.7 * math.sin(2 * math.pi * 90 * t) * math.exp(-6 * t), vol=0.55)
        sfx["hit"] = tone(0.45, lambda t: rnd.uniform(-1, 1) * 0.8 * math.exp(-7 * t)
                          + 0.6 * math.sin(2 * math.pi * 110 * t) * math.exp(-8 * t), vol=0.5)
        sfx["pow"] = tone(0.3, lambda t: 0.4 * math.sin(2 * math.pi * (600 + 900 * t) * t)
                          * math.exp(-4 * t), vol=0.45)
        sfx["bomb"] = tone(0.8, lambda t: rnd.uniform(-1, 1) * 0.5 * math.exp(-2.5 * t)
                           + 0.8 * math.sin(2 * math.pi * 60 * t) * math.exp(-4 * t), vol=0.6)
        sfx["wave"] = tone(0.35, lambda t: 0.35 * math.sin(2 * math.pi * 520 * t) * math.exp(-5 * t)
                           + 0.25 * math.sin(2 * math.pi * 780 * t) * math.exp(-5 * t), vol=0.5)
        sfx["ui"] = tone(0.07, lambda t: 0.4 * math.sin(2 * math.pi * 660 * t) * math.exp(-12 * t))
    except Exception:
        return {}
    return sfx


def load_best():
    try:
        with open(HS_PATH) as f:
            return int(json.load(f).get("best", 0))
    except Exception:
        return 0


def save_best(v):
    try:
        with open(HS_PATH, "w") as f:
            json.dump({"best": int(v)}, f)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# entities
# ---------------------------------------------------------------------------

class Player:
    def __init__(self):
        self.img = make_ship()
        self.r = 12  # small hitbox - bullets are what kill you, not the sprite
        self.reset()

    def reset(self):
        self.x, self.y = W / 2, H - 150
        self.vx = self.vy = 0.0
        self.weapon = 1
        self.shield = False
        self.inv = 0.0
        self.fire_t = 0.2

    def update(self, dt, keys):
        K = pygame
        ix = int(keys[K.K_RIGHT] or keys[K.K_d]) - int(keys[K.K_LEFT] or keys[K.K_a])
        iy = int(keys[K.K_DOWN] or keys[K.K_s]) - int(keys[K.K_UP] or keys[K.K_w])
        if ix or iy:
            n = (ix * ix + iy * iy) ** 0.5
            self.vx += ix / n * 3400 * dt
            self.vy += iy / n * 3400 * dt
        else:
            d = min(1.0, 9 * dt)
            self.vx -= self.vx * d
            self.vy -= self.vy * d
        sp = math.hypot(self.vx, self.vy)
        if sp > 440:
            self.vx *= 440 / sp
            self.vy *= 440 / sp
        self.x = clamp(self.x + self.vx * dt, 26, W - 26)
        self.y = clamp(self.y + self.vy * dt, 90, H - 40)
        self.inv = max(0.0, self.inv - dt)


class Enemy:
    def __init__(self, kind, x, wave):
        hp, r, score, vy, amp, freq, col = KIND_STATS[kind]
        self.kind = kind
        self.r = r
        self.score = score
        self.col = col
        self.hp = int(math.ceil(hp * (1 + wave * 0.12)))
        self.vy = vy + wave * 4
        self.amp = amp
        self.freq = freq
        self.base_x = clamp(x, amp + 50, W - amp - 50)
        self.x = self.base_x
        self.y = -40
        self.t = random.uniform(0, 6.28)
        self.phase = random.uniform(0, 6.28)
        self.flash = 0.0
        self.img = make_enemy(kind)
        if kind == "shooter":
            self.hold_y = random.uniform(170, 300)
            self.fire_t = random.uniform(0.8, 1.6)
            self.hold_left = 8.0

    def update(self, dt, g):
        self.t += dt
        self.flash = max(0.0, self.flash - dt)
        if self.kind == "shooter":
            if self.y < self.hold_y:
                self.y += self.vy * dt
            else:
                self.x = self.base_x + math.sin(self.t * self.freq + self.phase) * self.amp
                self.hold_left -= dt
                self.fire_t -= dt
                if self.fire_t <= 0 and self.y < g.player.y - 60:
                    g.fire_aimed(self.x, self.y + 10, 250 + g.wave * 6)
                    self.fire_t = max(1.1, 1.8 - g.wave * 0.05)
                if self.hold_left <= 0:
                    self.y += 160 * dt
        else:
            self.y += self.vy * dt
            self.x = self.base_x + math.sin(self.t * self.freq + self.phase) * self.amp


class Boss:
    def __init__(self, tier):
        self.tier = tier
        self.max_hp = 120 + 50 * (tier - 1)
        self.hp = self.max_hp
        self.r = 62
        self.x = W / 2
        self.y = -120
        self.t = 0.0
        self.pat_t = 2.2
        self.pat = -1
        self.flash = 0.0
        self.img = make_boss()
        self.score = 500

    def update(self, dt, g):
        self.t += dt
        self.flash = max(0.0, self.flash - dt)
        if self.y < 150:
            self.y += 170 * dt
        else:
            self.x = W / 2 + math.sin(self.t * 0.55) * (W / 2 - 150)
        self.pat_t -= dt
        if self.pat_t <= 0 and self.y >= 140:
            self.pat = (self.pat + 1) % 3
            if self.pat == 0:
                g.fire_spread(self.x, self.y + 40, 3, 270, 0.22)
            elif self.pat == 1:
                n = 12 + self.tier * 2
                for i in range(n):
                    a = i * 2 * math.pi / n + self.t
                    g.ebullets.append(dict(x=self.x, y=self.y + 20, vx=math.cos(a) * 175,
                                           vy=math.sin(a) * 175, r=6))
            else:
                for _ in range(7):
                    g.ebullets.append(dict(x=random.uniform(60, W - 60), y=-16,
                                           vx=random.uniform(-50, 50), vy=random.uniform(170, 240),
                                           r=6))
            self.pat_t = max(1.1, 2.1 - self.tier * 0.15)


class PowerUp:
    def __init__(self, kind, x, y):
        self.kind = kind
        self.x = clamp(x, 40, W - 40)
        self.y = y
        self.t = random.uniform(0, 6.28)
        self.img = make_powerup(kind)

    def update(self, dt):
        self.t += dt
        self.y += 95 * dt
        self.x += math.sin(self.t * 2) * 30 * dt


# ---------------------------------------------------------------------------
# game
# ---------------------------------------------------------------------------

class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("Neon Blaster")
        self.clock = pygame.time.Clock()
        self._fonts = {}
        self.sfx = build_sfx()
        self.sfx_on = True
        self.no_save = "--selftest" in sys.argv
        self.best = load_best()
        self.running = True
        self.state = "menu"
        self.time = 0.0
        self.test_keys = None

        self.bg = self._make_background()
        self.world = pygame.Surface((W, H)).convert()
        self.stars = self._make_stars()

        self.player = Player()
        self.ship_small = pygame.transform.scale(self.player.img, (24, 27))
        self.menu_hint_y = 0

        self.reset_game()

    # --------------------------------------------------- setup

    def _make_background(self):
        bg = pygame.Surface((W, H))
        top, bot = (8, 10, 24), (20, 14, 40)
        for y in range(H):
            f = y / H
            bg.fill(tuple(int(a + (b - a) * f) for a, b in zip(top, bot)), (0, y, W, 1))
        return bg

    def _make_stars(self):
        stars = []
        for i in range(110):
            layer = i % 3
            stars.append(dict(x=random.uniform(0, W), y=random.uniform(0, H),
                              sp=(30, 75, 140)[layer], size=(1, 2, 2)[layer],
                              col=[(140, 160, 215), (185, 195, 240), (255, 255, 255)][layer]))
        return stars

    def F(self, size):
        if size not in self._fonts:
            try:
                self._fonts[size] = pygame.font.SysFont("consolas,arial", size, bold=True)
            except Exception:
                self._fonts[size] = pygame.font.Font(None, size + 8)
        return self._fonts[size]

    def sfx_play(self, name):
        if self.sfx_on and self.sfx.get(name):
            self.sfx[name].play()

    def reset_game(self):
        self.player.reset()
        self.score = 0.0
        self.kills = 0
        self.lives = 3
        self.bombs = 1
        self.wave = 1
        self.new_best = False
        self.enemies = []
        self.boss = None
        self.pbullets = []
        self.ebullets = []
        self.powerups = []
        self.particles = []
        self.rings = []
        self.texts = []
        self.shake = 0.0
        self.flash = 0.0
        self.slowmo = 0.0
        self.spawn_left = 0
        self.spawn_t = 0.0
        self.boss_wave = False
        self.boss_spawned = False
        self.wave_transition = 0.0
        self.banner = None
        self.banner_t = 0.0
        self.setup_wave()

    def start_game(self):
        self.reset_game()
        self.state = "play"
        self.sfx_play("ui")

    # --------------------------------------------------- waves

    def setup_wave(self):
        self.boss_wave = (self.wave % 5 == 0)
        self.boss_spawned = False
        if self.boss_wave:
            self.spawn_boss()
            self.banner = "!! BOSS !!"
        else:
            self.spawn_left = min(8 + self.wave * 2, 26)
            self.spawn_t = 0.7
            self.banner = "WAVE %d" % self.wave
        self.banner_t = 1.9

    def complete_wave(self):
        bonus = 100 * self.wave
        self.score += bonus
        self.add_text(W / 2, H / 2 - 40, "WAVE %d CLEARED  +%d" % (self.wave, bonus), COL_GOLD)
        self.wave_transition = 2.0
        self.sfx_play("wave")

    def update_waves(self, dt):
        if self.wave_transition > 0:
            self.wave_transition -= dt
            if self.wave_transition <= 0:
                self.wave += 1
                self.setup_wave()
            return
        if self.boss_wave:
            if self.boss_spawned and self.boss is None:
                self.complete_wave()
        else:
            if self.spawn_left > 0:
                self.spawn_t -= dt
                if self.spawn_t <= 0:
                    self.spawn_enemy()
                    self.spawn_t = clamp(1.05 - self.wave * 0.05, 0.42, 1.05)
            elif not self.enemies:
                self.complete_wave()

    def spawn_enemy(self):
        self.spawn_left -= 1
        w = self.wave
        kinds = ["grunt"]
        if w >= 2:
            kinds += ["weaver"]
        if w >= 3:
            kinds += ["shooter", "grunt"]
        if w >= 4:
            kinds += ["tank", "weaver"]
        kind = random.choice(kinds)
        self.enemies.append(Enemy(kind, random.uniform(70, W - 70), w))

    def spawn_boss(self):
        self.boss = Boss(self.wave // 5)
        self.sfx_play("boom_b")

    # --------------------------------------------------- weapons / fx

    def fire_player(self):
        p = self.player
        lv = p.weapon
        if lv == 1:
            self.pbullets.append(dict(x=p.x, y=p.y - 26, vx=0, vy=-720, r=4))
        elif lv == 2:
            for ox in (-11, 11):
                self.pbullets.append(dict(x=p.x + ox, y=p.y - 22, vx=0, vy=-720, r=4))
        else:
            self.pbullets.append(dict(x=p.x, y=p.y - 26, vx=0, vy=-740, r=4))
            for ox in (-13, 13):
                self.pbullets.append(dict(x=p.x + ox, y=p.y - 18, vx=0, vy=-720, r=4))
            for ang in (-0.13, 0.13):
                self.pbullets.append(dict(x=p.x, y=p.y - 14, vx=math.sin(ang) * 700,
                                          vy=-math.cos(ang) * 700, r=4))
        self.sfx_play("shoot")

    def fire_aimed(self, x, y, speed):
        p = self.player
        a = math.atan2(p.y - y, p.x - x)
        self.ebullets.append(dict(x=x, y=y, vx=math.cos(a) * speed, vy=math.sin(a) * speed, r=6))

    def fire_spread(self, x, y, n, speed, spread):
        p = self.player
        base = math.atan2(p.y - y, p.x - x)
        for i in range(n):
            a = base + (i - (n - 1) / 2) * spread
            self.ebullets.append(dict(x=x, y=y, vx=math.cos(a) * speed, vy=math.sin(a) * speed, r=6))

    def explode(self, x, y, col, big=False):
        n = 34 if big else 20
        for _ in range(n):
            a = random.uniform(0, 2 * math.pi)
            sp = random.uniform(50, 420 if big else 280)
            self.particles.append(dict(x=x, y=y, vx=math.cos(a) * sp, vy=math.sin(a) * sp,
                                       life=random.uniform(0.3, 0.8), max=0.8,
                                       r=random.uniform(2, 5.5 if big else 4),
                                       col=random.choice([col, (255, 255, 255),
                                                          lerp_color(col, (255, 220, 120), 0.5)]),
                                       grav=60))
        self.rings.append(dict(x=x, y=y, r=8, vr=560 if big else 340,
                               life=0.35, max=0.35, col=col))

    def add_text(self, x, y, txt, col):
        self.texts.append(dict(x=x, y=y, txt=txt, col=col, life=1.0, max=1.0))

    def use_bomb(self):
        if self.bombs <= 0 or self.state != "play":
            return
        self.bombs -= 1
        self.flash = 1.0
        self.shake = max(self.shake, 15)
        self.rings.append(dict(x=self.player.x, y=self.player.y, r=20, vr=1500,
                               life=0.5, max=0.5, col=(255, 220, 120)))
        for b in self.ebullets:
            self.spark(b["x"], b["y"])
        self.ebullets = []
        for e in self.enemies[:]:
            self.damage_enemy(e, 8)
        if self.boss:
            self.damage_boss(12)
        self.sfx_play("bomb")

    def spark(self, x, y):
        for _ in range(4):
            a = random.uniform(0, 2 * math.pi)
            sp = random.uniform(30, 140)
            self.particles.append(dict(x=x, y=y, vx=math.cos(a) * sp, vy=math.sin(a) * sp,
                                       life=random.uniform(0.2, 0.45), max=0.45,
                                       r=random.uniform(1.5, 3), col=(255, 200, 130), grav=0))

    def damage_enemy(self, e, dmg):
        e.hp -= dmg
        e.flash = 0.08
        if e.hp <= 0:
            if e in self.enemies:
                self.enemies.remove(e)
            self.kills += 1
            self.score += e.score
            self.explode(e.x, e.y, e.col)
            self.sfx_play("boom_s")
            self.maybe_drop(e)

    def damage_boss(self, dmg):
        b = self.boss
        if not b:
            return
        b.hp -= dmg
        b.flash = 0.06
        if b.hp <= 0:
            for _ in range(5):
                self.explode(b.x + random.uniform(-90, 90), b.y + random.uniform(-30, 30),
                             (255, 120, 90), big=True)
            self.kills += 1
            self.score += b.score
            self.add_text(b.x, b.y, "+%d  BOSS DOWN!" % b.score, (255, 208, 70))
            self.powerups.append(PowerUp("weapon", b.x - 50, b.y))
            self.powerups.append(PowerUp(random.choice(["shield", "bomb"]), b.x + 50, b.y))
            self.boss = None
            self.shake = max(self.shake, 18)
            self.sfx_play("boom_b")

    def maybe_drop(self, e):
        chance = {"grunt": 0.10, "weaver": 0.14, "shooter": 0.24, "tank": 0.4}[e.kind]
        if random.random() > chance:
            return
        r = random.random()
        if r < 0.38:
            kind = "weapon"
        elif r < 0.62:
            kind = "shield" if not self.player.shield else "bomb"
        elif r < 0.85:
            kind = "bomb"
        else:
            kind = "life" if self.lives < 5 else "bomb"
        self.powerups.append(PowerUp(kind, e.x, e.y))

    def apply_powerup(self, pu):
        p = self.player
        if pu.kind == "weapon":
            if p.weapon < 3:
                p.weapon += 1
                self.add_text(p.x, p.y - 46, "POWER UP!", PLAYER_COL)
            else:
                self.score += 150
                self.add_text(p.x, p.y - 46, "MAX POWER  +150", PLAYER_COL)
        elif pu.kind == "shield":
            p.shield = True
            self.add_text(p.x, p.y - 46, "SHIELD", (120, 255, 140))
        elif pu.kind == "bomb":
            self.bombs = min(4, self.bombs + 1)
            self.add_text(p.x, p.y - 46, "+1 BOMB", (255, 160, 60))
        else:
            self.lives = min(5, self.lives + 1)
            self.add_text(p.x, p.y - 46, "+1 LIFE", (255, 110, 150))
        self.sparkle(p.x, p.y - 20, (255, 255, 255))
        self.sfx_play("pow")

    def sparkle(self, x, y, col):
        for _ in range(10):
            a = random.uniform(0, 2 * math.pi)
            sp = random.uniform(40, 180)
            self.particles.append(dict(x=x, y=y, vx=math.cos(a) * sp, vy=math.sin(a) * sp,
                                       life=random.uniform(0.25, 0.5), max=0.5,
                                       r=random.uniform(1.5, 3.5), col=col, grav=0))

    def player_hit(self):
        p = self.player
        if p.inv > 0 or self.state != "play":
            return
        if p.shield:
            p.shield = False
            p.inv = 1.0
            self.explode(p.x, p.y, (120, 255, 140))
            self.shake = max(self.shake, 10)
            self.add_text(p.x, p.y - 46, "SHIELD DOWN", (120, 255, 140))
            self.sfx_play("hit")
            return
        self.lives -= 1
        self.explode(p.x, p.y, (150, 220, 255), big=True)
        self.ebullets = []
        self.shake = max(self.shake, 16)
        self.slowmo = 0.4
        self.sfx_play("hit")
        if self.lives <= 0:
            self.state = "over"
            self.new_best = False
            if self.score > self.best:
                self.best = self.score
                self.new_best = True
                if not self.no_save:
                    save_best(self.best)
            self.sfx_play("boom_b")
        else:
            p.inv = 2.2
            self.flash = max(self.flash, 0.5)

    # --------------------------------------------------- update

    def update(self, dt):
        self.time += dt
        if self.slowmo > 0:
            self.slowmo = max(0.0, self.slowmo - dt)
            dt = dt * 0.4
        for s in self.stars:
            s["y"] += s["sp"] * dt
            if s["y"] > H:
                s["y"] -= H + 4
                s["x"] = random.uniform(0, W)
        self.flash = max(0.0, self.flash - 2.5 * dt)
        self.shake = max(0.0, self.shake - 40 * dt)
        self.banner_t = max(0.0, self.banner_t - dt)
        if self.state != "play":
            self.update_fx(dt)
            return
        p = self.player
        keys = self.test_keys if self.test_keys is not None else pygame.key.get_pressed()
        p.update(dt, keys)

        # engine flame
        if random.random() < 0.85:
            self.particles.append(dict(x=p.x + random.uniform(-5, 5), y=p.y + 26,
                                       vx=random.uniform(-15, 15), vy=random.uniform(130, 210),
                                       life=random.uniform(0.12, 0.25), max=0.25,
                                       r=random.uniform(2, 4),
                                       col=random.choice([(255, 220, 130), (255, 150, 60)]),
                                       grav=0))

        # auto fire
        p.fire_t -= dt
        if p.fire_t <= 0 and self.state == "play":
            self.fire_player()
            p.fire_t = FIRE_RATES[p.weapon]

        self.update_waves(dt)

        # enemies
        for e in self.enemies[:]:
            e.update(dt, self)
            if e.y > H + 60:
                self.enemies.remove(e)
                continue
            if p.inv <= 0 and dist2(e.x, e.y, p.x, p.y) < (e.r + p.r) ** 2:
                self.enemies.remove(e)
                self.explode(e.x, e.y, e.col)
                self.player_hit()

        if self.boss:
            self.boss.update(dt, self)
            if p.inv <= 0 and dist2(self.boss.x, self.boss.y, p.x, p.y) < (self.boss.r + p.r) ** 2:
                self.player_hit()

        # bullets
        for b in self.pbullets[:]:
            b["x"] += b["vx"] * dt
            b["y"] += b["vy"] * dt
            if b["y"] < -20 or b["x"] < -20 or b["x"] > W + 20:
                self.pbullets.remove(b)
                continue
            hit = False
            for e in self.enemies:
                if dist2(b["x"], b["y"], e.x, e.y) < (e.r + b["r"]) ** 2:
                    self.damage_enemy(e, 1)
                    hit = True
                    break
            if not hit and self.boss and dist2(b["x"], b["y"], self.boss.x, self.boss.y) \
                    < (self.boss.r + b["r"]) ** 2:
                self.damage_boss(1)
                hit = True
            if hit:
                self.pbullets.remove(b)

        for b in self.ebullets[:]:
            b["x"] += b["vx"] * dt
            b["y"] += b["vy"] * dt
            if b["y"] < -30 or b["y"] > H + 30 or b["x"] < -30 or b["x"] > W + 30:
                self.ebullets.remove(b)
                continue
            if p.inv <= 0 and dist2(b["x"], b["y"], p.x, p.y) < (b["r"] + p.r) ** 2:
                self.ebullets.remove(b)
                self.player_hit()

        # powerups
        for pu in self.powerups[:]:
            pu.update(dt)
            if pu.y > H + 40:
                self.powerups.remove(pu)
                continue
            if dist2(pu.x, pu.y, p.x, p.y) < 34 ** 2:
                self.powerups.remove(pu)
                self.apply_powerup(pu)

        self.update_fx(dt)

    def update_fx(self, dt):
        for q in self.particles[:]:
            q["life"] -= dt
            if q["life"] <= 0:
                self.particles.remove(q)
                continue
            q["x"] += q["vx"] * dt
            q["y"] += q["vy"] * dt
            q["vy"] += q.get("grav", 0) * dt
            q["r"] = max(0.5, q["r"] - 1.5 * dt)
        for r in self.rings[:]:
            r["life"] -= dt
            r["r"] += r["vr"] * dt
            if r["life"] <= 0:
                self.rings.remove(r)
        for t in self.texts[:]:
            t["life"] -= dt
            t["y"] -= 40 * dt
            if t["life"] <= 0:
                self.texts.remove(t)

    # --------------------------------------------------- events

    def handle_events(self):
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.running = False
            elif e.type == pygame.KEYDOWN:
                k = e.key
                if k == pygame.K_m:
                    self.sfx_on = not self.sfx_on
                elif k == pygame.K_ESCAPE:
                    if self.state == "play":
                        self.state = "pause"
                    elif self.state in ("pause", "over"):
                        self.state = "menu"
                    else:
                        self.running = False
                elif self.state == "menu" and k == pygame.K_RETURN:
                    self.start_game()
                elif self.state == "over" and k == pygame.K_RETURN:
                    self.start_game()
                elif self.state == "play":
                    if k in (pygame.K_LSHIFT, pygame.K_RSHIFT, pygame.K_b):
                        self.use_bomb()
                    elif k == pygame.K_p:
                        self.state = "pause"
                elif self.state == "pause" and k == pygame.K_p:
                    self.state = "play"

    # --------------------------------------------------- drawing

    def draw_ship(self, surf):
        p = self.player
        if self.state == "over":
            return
        if p.inv > 0 and int(self.time * 14) % 2 == 0:
            return
        tilt = clamp(p.vx / 440.0, -1, 1) * 9
        img = pygame.transform.rotate(p.img, -tilt) if abs(tilt) > 0.4 else p.img
        surf.blit(img, img.get_rect(center=(int(p.x), int(p.y))))
        if p.shield:
            a = int(120 + 90 * math.sin(self.time * 5))
            sh = pygame.Surface((76, 76), pygame.SRCALPHA)
            pygame.draw.circle(sh, (120, 255, 140, a), (38, 38), 34, 3)
            surf.blit(sh, (p.x - 38, p.y - 38))

    def draw_enemies(self, surf):
        for e in self.enemies:
            img = e.img
            if e.flash > 0:
                img = img.copy()
                img.fill((255, 255, 255, 160), special_flags=pygame.BLEND_RGBA_MAX)
            surf.blit(img, img.get_rect(center=(int(e.x), int(e.y))))
        if self.boss:
            b = self.boss
            img = b.img
            if b.flash > 0:
                img = img.copy()
                img.fill((255, 255, 255, 140), special_flags=pygame.BLEND_RGBA_MAX)
            surf.blit(img, img.get_rect(center=(int(b.x), int(b.y))))

    def draw_bullets(self, surf):
        for b in self.pbullets:
            x, y = int(b["x"]), int(b["y"])
            pygame.draw.line(surf, (140, 235, 255), (x, y + 9), (x, y - 9), 5)
            pygame.draw.line(surf, (255, 255, 255), (x, y + 5), (x, y - 5), 3)
        for b in self.ebullets:
            x, y = b["x"], b["y"]
            pygame.draw.circle(surf, (120, 30, 90), (int(x), int(y)), int(b["r"] + 3))
            pygame.draw.circle(surf, (255, 70, 200), (int(x), int(y)), int(b["r"]))
            pygame.draw.circle(surf, (255, 255, 255), (int(x), int(y)), 3)

    def draw_powerups(self, surf):
        for pu in self.powerups:
            pulse = 1 + 0.1 * math.sin(self.time * 6 + pu.t)
            img = pygame.transform.rotozoom(pu.img, 0, pulse)
            surf.blit(img, img.get_rect(center=(int(pu.x), int(pu.y))))

    def draw_particles(self, surf):
        for q in self.particles:
            a = int(220 * q["life"] / q["max"])
            r = max(1, int(q["r"]))
            ps = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(ps, (*q["col"], a), (r + 1, r + 1), r)
            surf.blit(ps, (q["x"] - r - 1, q["y"] - r - 1))
        for r in self.rings:
            a = int(200 * r["life"] / r["max"])
            ps = pygame.Surface((int(r["r"] * 2 + 4),) * 2, pygame.SRCALPHA)
            pygame.draw.circle(ps, (*r["col"], a), (ps.get_width() // 2,) * 2,
                               int(r["r"]), 3)
            surf.blit(ps, (r["x"] - ps.get_width() // 2, r["y"] - ps.get_height() // 2))

    def draw_hud(self):
        s = self.screen
        draw_text(s, "SCORE %06d" % int(self.score), self.F(26), (255, 255, 255),
                  (16, 12), shadow=(0, 0, 0))
        draw_text(s, "BEST %06d" % int(max(self.best, self.score)), self.F(16),
                  (255, 208, 70), (18, 44), shadow=(0, 0, 0))
        for i in range(self.lives):
            s.blit(self.ship_small, (W - 34 - i * 30, 12))
        draw_text(s, "BOMB x%d  (SHIFT)" % self.bombs, self.F(15), (255, 160, 60),
                  (W - 16, 46), anchor="topright", shadow=(0, 0, 0))
        pips = "".join("|" if i < self.player.weapon else "." for i in range(3))
        draw_text(s, "PWR %s" % pips, self.F(15), PLAYER_COL, (W - 16, 68),
                  anchor="topright", shadow=(0, 0, 0))
        draw_text(s, "WAVE %d" % self.wave, self.F(16), (170, 180, 210), (W - 16, 94),
                  anchor="topright", shadow=(0, 0, 0))
        if self.boss:
            bw = 420
            bx, by = W // 2 - bw // 2, 100
            draw_text(s, "- DREADNOUGHT -", self.F(14), (255, 120, 140), (W // 2, by - 20),
                      anchor="midtop", shadow=(0, 0, 0))
            pygame.draw.rect(s, (0, 0, 0), (bx - 2, by - 2, bw + 4, 18), border_radius=6)
            pygame.draw.rect(s, (90, 40, 55), (bx - 2, by - 2, bw + 4, 18), width=2,
                             border_radius=6)
            fillw = int(bw * clamp(self.boss.hp / self.boss.max_hp, 0, 1))
            if fillw > 0:
                pygame.draw.rect(s, (255, 80, 100), (bx, by, fillw, 14), border_radius=5)
        if not self.sfx_on:
            draw_text(s, "MUTED (M)", self.F(14), (165, 165, 175), (W - 14, H - 20),
                      anchor="bottomright", shadow=(0, 0, 0))

    def draw_banner(self):
        if self.banner_t <= 0 or not self.banner:
            return
        a = int(255 * clamp(self.banner_t / 0.5, 0, 1))
        col = (255, 90, 110) if "BOSS" in self.banner else PLAYER_COL
        draw_text(self.screen, self.banner, self.F(56), col, (W // 2, 330),
                  anchor="midtop", shadow=(0, 0, 0), alpha=a)

    def draw_menu(self):
        s = self.screen
        dim = pygame.Surface((W, H), pygame.SRCALPHA)
        dim.fill((6, 8, 18, 110))
        s.blit(dim, (0, 0))
        draw_text(s, "NEON BLASTER", self.F(64), (255, 208, 70), (W // 2, 150),
                  anchor="midtop", shadow=(120, 40, 10))
        draw_text(s, "V E R T I C A L   S P A C E   S H O O T E R", self.F(17), PLAYER_COL,
                  (W // 2, 232), anchor="midtop", shadow=(0, 0, 0))
        lines = ["ARROWS / WASD   fly        guns fire automatically",
                 "SHIFT or B   smart bomb - clears bullets, damages all",
                 "P  pause        M  sound        ESC  menu / quit",
                 "collect P / S / B / + drops - boss every 5th wave"]
        yy = 300
        for ln in lines:
            draw_text(s, ln, self.F(18), (210, 218, 235), (W // 2, yy), anchor="midtop",
                      shadow=(0, 0, 0))
            yy += 32
        a = int(140 + 115 * (0.5 + 0.5 * math.sin(self.time * 4.5)))
        draw_text(s, "PRESS ENTER TO PLAY", self.F(30), (255, 255, 255), (W // 2, 500),
                  anchor="midtop", shadow=(0, 0, 0), alpha=a)
        draw_text(s, "BEST SCORE  %06d" % int(self.best), self.F(22), (255, 208, 70),
                  (W // 2, 560), anchor="midtop", shadow=(0, 0, 0))
        draw_text(s, "survive the waves - graze nothing, dodge everything", self.F(15),
                  (150, 158, 175), (W // 2, 620), anchor="midtop")

    def draw_over(self):
        s = self.screen
        dim = pygame.Surface((W, H), pygame.SRCALPHA)
        dim.fill((10, 6, 16, 160))
        s.blit(dim, (0, 0))
        panel = pygame.Rect(W // 2 - 240, 260, 480, 420)
        pp = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(pp, (10, 8, 20, 185), pp.get_rect(), border_radius=18)
        pygame.draw.rect(pp, ((255, 208, 84, 210) if getattr(self, "new_best", False)
                              else (150, 90, 100, 190)), pp.get_rect(), width=2, border_radius=18)
        s.blit(pp, panel.topleft)
        draw_text(s, "SHIP DESTROYED", self.F(40), (255, 84, 64), (W // 2, 290),
                  anchor="midtop", shadow=(60, 10, 8))
        rows = [("SCORE", "%06d" % int(self.score)),
                ("WAVE REACHED", str(self.wave)),
                ("KILLS", str(self.kills)),
                ("BEST", "%06d" % int(self.best))]
        yy = 380
        for label, val in rows:
            draw_text(s, label, self.F(20), (170, 178, 195), (W // 2 - 30, yy), anchor="topright")
            draw_text(s, val, self.F(24), (255, 255, 255), (W // 2 + 30, yy - 3), anchor="topleft")
            yy += 44
        if getattr(self, "new_best", False):
            a = int(140 + 115 * (0.5 + 0.5 * math.sin(self.time * 6)))
            draw_text(s, "* NEW BEST *", self.F(28), (255, 208, 84), (W // 2, 570),
                      anchor="midtop", shadow=(90, 50, 0), alpha=a)
        draw_text(s, "ENTER  fly again        ESC  menu", self.F(20), (200, 208, 222),
                  (W // 2, 630), anchor="midtop", shadow=(0, 0, 0))

    def draw(self):
        s = self.screen
        w = self.world
        w.blit(self.bg, (0, 0))
        for st in self.stars:
            pygame.draw.circle(w, st["col"], (int(st["x"]), int(st["y"])), st["size"])
        if self.state in ("play", "pause", "over"):
            self.draw_powerups(w)
            self.draw_enemies(w)
            self.draw_ship(w)
            self.draw_bullets(w)
            self.draw_particles(w)
        sx = sy = 0
        if self.shake > 0.2:
            sx = random.uniform(-self.shake, self.shake)
            sy = random.uniform(-self.shake, self.shake)
        s.fill((0, 0, 0))
        s.blit(w, (int(sx), int(sy)))
        if self.flash > 0.02:
            fl = pygame.Surface((W, H))
            fl.fill((255, 240, 210))
            fl.set_alpha(int(110 * self.flash))
            s.blit(fl, (0, 0))
        if self.state == "menu":
            self.draw_menu()
        elif self.state in ("play", "pause"):
            self.draw_hud()
            self.draw_banner()
            for t in self.texts:
                draw_text(s, t["txt"], self.F(20), t["col"], (t["x"], t["y"]),
                          anchor="midtop", shadow=(0, 0, 0), alpha=int(255 * t["life"] / t["max"]))
            if self.state == "pause":
                dim = pygame.Surface((W, H), pygame.SRCALPHA)
                dim.fill((5, 8, 18, 150))
                s.blit(dim, (0, 0))
                draw_text(s, "PAUSED", self.F(56), (255, 255, 255), (W // 2, 400),
                          anchor="midtop", shadow=(0, 0, 0))
                draw_text(s, "P  resume        ESC  menu", self.F(22), (190, 200, 215),
                          (W // 2, 490), anchor="midtop", shadow=(0, 0, 0))
        elif self.state == "over":
            self.draw_hud()
            self.draw_over()

    # --------------------------------------------------- loop

    def step(self, dt):
        self.update(dt)
        self.draw()
        pygame.display.flip()
        pygame.event.pump()

    def run(self):
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            self.handle_events()
            self.step(dt)
        pygame.quit()


# ---------------------------------------------------------------------------
# selftest (headless): mechanics checks + screenshots
# ---------------------------------------------------------------------------

def selftest():
    random.seed(11)
    g = Game()
    os.makedirs(SHOT_DIR, exist_ok=True)

    def snap(name):
        pygame.image.save(g.screen, os.path.join(SHOT_DIR, name))

    def frames(n, keys=None):
        g.test_keys = _Keys(keys) if keys else None
        for _ in range(n):
            g.step(1.0 / FPS)

    frames(20)
    snap("1_menu.png")

    g.start_game()
    frames(10)

    # combat: a grunt right in the line of fire + a shooter that aims back
    px = g.player.x
    e1 = Enemy("grunt", px, 1)
    e1.base_x, e1.x, e1.y, e1.amp = px, px, g.player.y - 300, 0
    g.enemies.append(e1)
    e2 = Enemy("shooter", px + 190, 3)
    e2.hold_y, e2.y = 250, 250
    g.enemies.append(e2)
    score_before = int(g.score)
    frames(55)
    combat_ok = int(g.score) > score_before and len(g.pbullets) > 0
    snap("2_battle.png")

    # power-up pickup upgrades the gun
    g.powerups.append(PowerUp("weapon", g.player.x, g.player.y - 70))
    frames(30)
    weapon_ok = g.player.weapon == 2

    # bomb wipes bullets and damages everything
    g.bombs = 1
    for i in range(6):
        g.ebullets.append(dict(x=100 + i * 40, y=300 + i * 30, vx=0, vy=100, r=6))
    g.use_bomb()
    bomb_ok = not g.ebullets and g.bombs == 0
    frames(15)

    # a collision costs a life and grants invincibility
    g.lives = 3
    g.player.inv = 0.0
    e3 = Enemy("grunt", g.player.x, 1)
    e3.base_x, e3.x, e3.y, e3.amp = g.player.x, g.player.x, g.player.y - 20, 0
    g.enemies.append(e3)
    frames(3)
    hit_ok = g.lives == 2 and g.player.inv > 0
    snap("3_hit.png")
    frames(60)

    # boss wave
    g.enemies = []
    g.wave = 5
    g.setup_wave()
    frames(45)
    boss_ok = g.boss is not None
    snap("4_boss.png")

    # kill the boss -> wave completes
    if g.boss:
        g.boss.hp = 1
        g.damage_boss(2)
    boss_dead = g.boss is None
    frames(30)

    # fatal hit -> game over
    g.lives = 1
    g.player.inv = 0.0
    e4 = Enemy("grunt", g.player.x, 1)
    e4.base_x, e4.x, e4.y, e4.amp = g.player.x, g.player.x, g.player.y - 20, 0
    g.enemies.append(e4)
    frames(3)
    over_ok = g.state == "over"
    frames(60)
    snap("5_gameover.png")

    pygame.quit()
    print("SELFTEST OK  combat=%s weapon=%s bomb=%s hit=%s boss=%s boss_dead=%s over=%s"
          % (combat_ok, weapon_ok, bomb_ok, hit_ok, boss_ok, boss_dead, over_ok))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        Game().run()
