#!/usr/bin/env python3
"""commit-burgers: turn a year of git commits into a 3D burger skyline (SVG) and a marimba song (WAV).

    python commit_burgers.py [REPO] [--author NAME] [--since DATE] [-o OUT]     # your repo
    python commit_burgers.py --demo -o out                                      # synthetic year

Skyline geometry is ported from zhutoumeme/mcd-git (card_skyline.py, MIT): one burger layer per commit,
max 4 layers plus a "+", a flag on the busiest day. The notes are ported from Leonxlnx/earshot
(forge/recipes/mallet.py, MIT): the same struck-bar model, without the contact noise and the room.
"""
import argparse
import datetime as dt
import html
import random
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------- skyline (from mcd-git card_skyline.py)
WIDTH, HEIGHT = 1200, 624
WX, WY, DX, DY = 18, 4, -9, 7  # screen step for one week (down-right) and one weekday (down-left)
OX, OY = 150, 215
GAP, SIDE = 0.12, 0.76
LAYER, MAX_LAYERS = 14, 4
DURATION, FLAG_DELAY, LEFT, FULL_WEEKS = 0.6, 0.2, 60, 53
AREA_TOP, AREA_BOTTOM, MAX_SCALE, FLAG_HEIGHT = 108, 500, 3.0, 42
SLICES = ((0.22, "#E9B66B", "#C9914A"), (0.26, "#8A4B2A", "#6E3A20"), (0.10, "#FFD24A", "#E5B42E"),
          (0.10, "#7DBE4E", "#5E9C38"), (0.32, "#F2B95C", "#D39A41"))  # bun, patty, cheese, lettuce, bun
MONO = 'ui-monospace,"SF Mono",Menlo,Consolas,monospace'
CSS = (
    "\nsvg{font-family:-apple-system,\"Segoe UI\",sans-serif}\n"
    f".mo{{font-family:{MONO};white-space:pre}}\n"
    ".h{font-size:30px;font-weight:800}.s{font-size:14px}.k{font-size:13px}.v{font-size:20px;font-weight:700}.m{font-size:11px}\n"
    ".t1{fill:#F4EFE6}.t2{fill:#9AA0B4}.bd{stroke:#2C3142;stroke-width:1}.tl{fill:#262A38}.tm{fill:#5A2E2B}"
    ".g0{stop-color:#3A2E2A}.g1{stop-color:#161925}.pole{stroke:#E8E3D8}\n"
    f".f{{animation:drop {DURATION}s cubic-bezier(.3,1.25,.5,1) both}}.idle .f{{animation:none}}\n"
    "@keyframes drop{0%{transform:translateY(-90px);opacity:0}35%{opacity:1}100%{transform:translateY(0);opacity:1}}\n"
    "@media (prefers-reduced-motion:reduce){.f{animation:none}}\n"
    "@media (prefers-color-scheme:light){\n"
    ".t1{fill:#3B2A1A}.t2{fill:#8A7560}.bd{stroke:#E6D6BD}.tl{fill:#E8DAC2}.tm{fill:#F2C3B0}"
    ".g0{stop-color:#FFF8EC}.g1{stop-color:#F3E6CF}.pole{stroke:#6B4A2E}\n}\n"
)


def _p(w, d, h=0.0):
    return (w * WX + d * DX, w * WY + d * DY - h)


def _pts(points):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def _defs():
    a, b = GAP, GAP + SIDE
    quad = _pts([_p(a, a), _p(b, a), _p(b, b), _p(a, b)])
    burger, h0 = [], 0.0
    for frac, front, side in SLICES:
        h1 = h0 + frac * LAYER
        burger.append(f'<polygon fill="{front}" points="{_pts([_p(a, b, h0), _p(b, b, h0), _p(b, b, h1), _p(a, b, h1)])}"/>')
        burger.append(f'<polygon fill="{side}" points="{_pts([_p(b, a, h0), _p(b, b, h0), _p(b, b, h1), _p(b, a, h1)])}"/>')
        h0 = h1
    cx, cy = _p(GAP + SIDE / 2, GAP + SIDE / 2)
    sesame = "".join(f'<ellipse cx="{cx + dx:.1f}" cy="{cy + dy:.1f}" rx="1.1" ry="0.7" fill="#FFF6E0"/>'
                     for dx, dy in ((-3.5, 0.5), (2.5, -1.2), (0.5, 2.2), (4.5, 1.8)))
    return ('<defs><radialGradient id="g" cx="0.55" cy="0.62" r="0.65"><stop offset="0" class="g0"/>'
            f'<stop offset="1" class="g1"/></radialGradient><polygon id="tile" points="{quad}"/>'
            f'<g id="b">{"".join(burger)}</g><g id="c"><polygon fill="#F7C873" points="{quad}"/>{sesame}</g>'
            '<g id="p"><circle r="6" fill="#E8473C" stroke="#FFF6E0" stroke-width="1"/>'
            '<path d="M-1,-3.5h2v2.5h2.5v2h-2.5v2.5h-2v-2.5h-2.5v-2h2.5z" fill="#FFF6E0"/></g>'
            '<g id="fl"><line class="pole" x1="0" y1="0" x2="0" y2="-42" stroke-width="1.5"/>'
            '<path d="M0,-42h44l-6,7.5l6,7.5h-44z" fill="#E8473C"/>'
            f'<text x="7" y="-31" font-family="{html.escape(MONO)}" font-size="10" font-weight="700" fill="#FFFFFF">best</text></g></defs>')


def _origin(col, row):
    return OX + col * WX + row * DX, OY + col * WY + row * DY


def _top_center(col, row, layers):
    x, y = _origin(col, row)
    cx, cy = _p(GAP + SIDE / 2, GAP + SIDE / 2)
    return int(round(x + cx)), int(round(y + cy)) - layers * LAYER


def _layout(weeks):
    """scale + centre a short history into the drawing area (upstream bounds() + layout())"""
    a, b = GAP, GAP + SIDE
    corners = [_p(a, a), _p(b, a), _p(b, b), _p(a, b)]
    tile_top = min(cy for _, cy in corners)
    xs, ys = [], []
    for col, column in enumerate(weeks):
        for row, cell in enumerate(column):
            if cell is None:
                continue
            x, y = _origin(col, row)
            xs += [x + cx for cx, _ in corners]
            ys += [y + cy for _, cy in corners]
            layers = min(cell["count"], MAX_LAYERS)
            top = y + tile_top - layers * LAYER
            fx, fy = _top_center(col, row, layers)
            if cell["count"] > MAX_LAYERS:
                fy -= 16
                top = min(top, fy - 1)
            if cell["mark"]:
                top = min(top, fy - FLAG_HEIGHT - 2)
                xs.append(fx + 44)
            ys.append(top)
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    area_w, area_h = WIDTH - 2 * LEFT, AREA_BOTTOM - AREA_TOP
    raw = min(MAX_SCALE, area_w / (x1 - x0), area_h / (y1 - y0))
    s = round((int(raw * 1000) - 1) / 1000, 3)
    return s, round(LEFT + area_w / 2 - s * (x0 + x1) / 2, 1), round(AREA_TOP + area_h / 2 - s * (y0 + y1) / 2, 1)


def _text(x, y, cls, content, anchor=None):
    extra = f' text-anchor="{anchor}"' if anchor else ""
    return f'<text class="{cls}" x="{x}" y="{y}"{extra}>{html.escape(str(content), quote=False)}</text>'


def render_svg(weeks, step=0.04, title="commit skyline", footer="", idle=False):
    days = [c for w in weeks for c in w if c]
    total = sum(c["count"] for c in days)
    cls = ' class="idle"' if idle else ""
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" '
           f'role="img" aria-labelledby="t"{cls}>',
           f'<title id="t">{html.escape(title)}: {total} commits</title>', f"<style>{CSS}</style>", _defs(),
           f'<rect x="0" y="0" width="{WIDTH}" height="{HEIGHT}" rx="18" fill="url(#g)"/>',
           _text(LEFT, 64, "t1 h", title), _text(LEFT, 94, "t2 s mo", "$ commit-burgers  # one burger layer per commit")]
    narrow = len(weeks) < FULL_WEEKS
    if narrow:
        s, tx, ty = _layout(weeks)
        out.append(f'<g transform="translate({tx:.1f},{ty:.1f}) scale({s:.3f})">')
    floor, mark = ['<g class="tl">'], None
    for col, column in enumerate(weeks):
        for row, cell in enumerate(column):
            if cell is None:
                continue
            x, y = _origin(col, row)
            floor.append(f'<use href="#tile" x="{x}" y="{y}"' + (' class="tm"' if cell["mark"] else "") + "/>")
            if cell["mark"]:
                mark = (col, row, min(cell["count"], MAX_LAYERS))
    out += floor + ["</g>"]
    for col, column in enumerate(weeks):  # painter's order: weeks left to right, Monday to Sunday
        stacks = []
        for row, cell in enumerate(column):
            if not cell or not cell["count"]:
                continue
            x, y = _origin(col, row)
            layers = min(cell["count"], MAX_LAYERS)
            stacks += [f'<use href="#b" x="{x}" y="{y - i * LAYER}"/>' for i in range(layers)]
            stacks.append(f'<use href="#c" x="{x}" y="{y - layers * LAYER}"/>')
            if cell["count"] > MAX_LAYERS:
                px, py = _top_center(col, row, layers)
                stacks.append(f'<use class="more" href="#p" x="{px}" y="{py - 10}"/>')
        if stacks:
            out.append(f'<g class="f" style="animation-delay:{col * step:.2f}s">' + "".join(stacks) + "</g>")
    if mark:
        col, row, layers = mark
        fx, fy = _top_center(col, row, layers)
        if layers and weeks[col][row]["count"] > MAX_LAYERS:
            fy -= 16
        out.append(f'<g class="f flag" style="animation-delay:{col * step + FLAG_DELAY:.2f}s"><use href="#fl" x="{fx}" y="{fy}"/></g>')
    if narrow:
        out.append("</g>")
    out.append(f'<line class="bd" x1="{LEFT}" y1="510" x2="{WIDTH - LEFT}" y2="510"/>')
    items = stats(weeks)
    width = (WIDTH - 2 * LEFT) // len(items)
    for i, (label, value) in enumerate(items):
        out += [_text(LEFT + i * width, 540, "t2 k", label), _text(LEFT + i * width, 568, "t1 v", value)]
    out += [_text(LEFT, 606, "t2 m", footer),
            _text(WIDTH - LEFT, 606, "t2 m", "1 burger layer = 1 commit · more than 4 shows a +", anchor="end"), "</svg>"]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- data
def git_counts(repo, since=None, author=None):
    cmd = ["git", "-C", str(repo), "log", "--format=%ad", "--date=short"]
    cmd += [f"--since={since}"] if since else []
    cmd += [f"--author={author}"] if author else []
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        sys.exit(f"commit-burgers: git log failed in {repo}: {r.stderr.strip()}")
    counts = {}
    for line in r.stdout.split():
        d = dt.date.fromisoformat(line)
        counts[d] = counts.get(d, 0) + 1
    return counts


def demo_counts(end):
    """a made-up but plausible year: busy weekdays, quiet weekends, two holidays, a few crunch days"""
    r, counts = random.Random(7), {}
    for i in range(371):
        d = end - dt.timedelta(days=i)
        if 40 <= i < 54 or 200 <= i < 209:
            continue
        n = int(r.random() ** 1.8 * (6 if d.weekday() < 5 else 2.2))
        if r.random() < 0.02:
            n += 6
        if n:
            counts[d] = n
    return counts


def build_weeks(counts, end):
    """53 Monday-first week columns ending with end's week (at least 12 weeks; days after end are None)"""
    last_monday = end - dt.timedelta(days=end.weekday())
    first = min(counts) if counts else end
    start = max(last_monday - dt.timedelta(weeks=FULL_WEEKS - 1),
                min(first - dt.timedelta(days=first.weekday()), last_monday - dt.timedelta(weeks=11)))
    window = {d: n for d, n in counts.items() if start <= d <= end}
    best = max(window.items(), key=lambda kv: (kv[1], kv[0]))[0] if window else None
    weeks = []
    for w in range((last_monday - start).days // 7 + 1):
        col = []
        for d in range(7):
            day = start + dt.timedelta(weeks=w, days=d)
            col.append(None if day > end else {"date": day, "count": window.get(day, 0), "mark": day == best})
        weeks.append(col)
    return weeks


def stats(weeks):
    days = [c for w in weeks for c in w if c]
    total = sum(c["count"] for c in days)
    best = max(days, key=lambda c: (c["count"], c["date"]))
    streak = run = 0
    for c in days:
        run = run + 1 if c["count"] else 0
        streak = max(streak, run)
    by_wd = [sum(c["count"] for c in days if c["date"].weekday() == i) for i in range(7)]
    return [("Commits", f"{total:,}"), ("Busiest day", f"{best['date']:%b %d} · {best['count']}" if best["count"] else "—"),
            ("Longest streak", f"{streak} days"), ("Top weekday", "MonTueWedThuFriSatSun"[3 * by_wd.index(max(by_wd)):][:3]),
            ("Active days", f"{sum(1 for c in days if c['count'])}")]


# ---------------------------------------------------------------- song (from earshot forge/recipes/mallet.py)
SR = 48000
BARS = {"glock": [(1.0, 1.0), (2.756, 0.35), (5.404, 0.12), (8.933, 0.05)],
        "marimba": [(1.0, 1.0), (3.92, 0.3), (9.8, 0.08)]}
MARIMBA = dict(bar="marimba", decay=1.6, slope=0.3, hard=0.45, beat=1.747, onset=0.004282, gate=0.06156,
               gate_tau=0.03, oct=-60.0, oct_ratio=0.5)
GLOCK = dict(bar="glock", decay=0.5027, slope=0.8703, hard=0.6343, beat=4.807, onset=0.00162, gate=0.08478,
             gate_tau=0.0422, oct=-2.483, oct_ratio=0.5)
PENTA = [0, 2, 4, 7, 9, 12, 14, 16, 19, 21]  # two octaves of the major pentatonic, from G3


def _bar(p, r, n, f0):
    """one struck bar (mono): partials decaying with ratio ** -slope, a doublet beat, a soft rise, a damper"""
    t = np.arange(n) / SR
    y = np.zeros(n)
    for q, a in BARS[p["bar"]]:
        f = f0 * q
        if f >= 0.42 * SR:
            continue
        a = a * q ** (1.5 * (p["hard"] - 0.5))
        tau = max(p["decay"] * q ** -p["slope"], 0.003)
        b = p["beat"] * r.uniform(0.6, 1.4)
        am = 1 - 0.3 * (0.5 - 0.5 * np.cos(2 * np.pi * b * t)) if b > 0.01 else 1.0
        y += a * np.exp(-t / tau) * am * np.sin(2 * np.pi * f * t + r.uniform(0, 2 * np.pi))
    y *= np.exp(-np.maximum(t - p["gate"], 0) / max(p["gate_tau"], 1e-4))
    return y * (0.5 - 0.5 * np.cos(np.pi * np.clip(t / max(p["onset"], 1e-4), 0, 1)))


def voice(p, r, n, f0):
    y = _bar(p, r, n, f0)
    return y + 10 ** (p["oct"] / 20) * _bar(p, r, n, f0 * p["oct_ratio"]) if p["oct"] > -59 else y


def note_len(p):
    return min(2.0, p["gate"] + 7.0 * p["gate_tau"] + 0.02, max(p["onset"] + 7.0 * p["decay"], 0.06) + 0.02)


def melody(weeks):
    """one marimba note per active week, pitch by how busy the week was; the busiest week also rings a glockenspiel"""
    totals = [sum(c["count"] for c in w if c) for w in weeks]
    active = sorted(t for t in totals if t)
    notes, top = [], max(totals)
    for col, t in enumerate(totals):
        if not t:
            continue
        rank = active.index(t) / max(1, len(active) - 1)
        f0 = 196.0 * 2 ** (PENTA[round(rank * (len(PENTA) - 1))] / 12)
        notes.append((col, f0, t == top))
    return notes


def render_song(notes, ncols, step=0.2):
    out = np.zeros((int((ncols * step + 1.0) * SR), 2))
    r = np.random.default_rng(1)
    for col, f0, accent in notes:
        layers = [(MARIMBA, f0, 1.0)] + ([(GLOCK, f0 * 4, 0.5)] if accent else [])
        pan = -0.7 + 1.4 * col / max(1, ncols - 1)  # the year walks from left to right
        for p, f, g in layers:
            y = g * voice(p, r, int(note_len(p) * SR), f)
            i0 = int(col * step * SR)
            gains = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
            out[i0:i0 + len(y)] += np.outer(y, gains)[: len(out) - i0]
    return out * (10 ** (-1 / 20) / (np.abs(out).max() + 1e-12))


def write_wav(path, x):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2), w.setsampwidth(2), w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


PAGE = """<!doctype html><meta charset="utf-8"><title>{title}</title>
<style>body{{margin:0;background:#161925;display:grid;place-items:center;min-height:100vh;font:16px system-ui;color:#F4EFE6}}
svg{{max-width:96vw;height:auto}}button{{margin:16px;padding:10px 22px;font:inherit;border-radius:10px;border:0;background:#E8473C;color:#fff;cursor:pointer}}</style>
<div><div id="s">{svg}</div><p style="text-align:center"><button id="go">Play the year</button></p></div>
<audio id="a" src="song.wav" preload="auto"></audio>
<script>go.onclick=()=>{{const v=s.querySelector('svg'),n=v.cloneNode(true);n.classList.remove('idle');v.replaceWith(n);a.currentTime=0;a.play()}}</script>
"""


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--demo", action="store_true", help="use a synthetic year instead of git log")
    ap.add_argument("--author", help="only count commits whose author matches (git log --author)")
    ap.add_argument("--since", help="git log --since (default: 371 days before the last day)")
    ap.add_argument("--title", default="commit skyline")
    ap.add_argument("--step", type=float, default=0.2, help="seconds per week in the song and the page")
    ap.add_argument("-o", "--out", default="commit-burgers-out")
    a = ap.parse_args(argv)
    if a.demo:
        end, counts, name = dt.date(2026, 10, 23), demo_counts(dt.date(2026, 10, 23)), "demo year"
    else:
        end = dt.date.today()
        counts = git_counts(a.repo, a.since or str(end - dt.timedelta(days=371)), a.author)
        name = Path(a.repo).resolve().name
        if not counts:
            sys.exit(f"commit-burgers: no commits found in {a.repo}")
    weeks = build_weeks(counts, end)
    first = next(c["date"] for w in weeks for c in w if c)
    footer = f"{name} · {first:%Y-%m-%d} to {end:%Y-%m-%d}"
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    svg = render_svg(weeks, title=a.title, footer=footer)
    (out / "skyline.svg").write_text(svg, encoding="utf-8")
    song = render_song(melody(weeks), len(weeks), a.step)
    write_wav(out / "song.wav", song)
    page = render_svg(weeks, step=a.step, title=a.title, footer=footer, idle=True)
    (out / "index.html").write_text(PAGE.format(title=html.escape(a.title), svg=page), encoding="utf-8")
    s = dict(stats(weeks))
    print(f"commit-burgers: {s['Commits']} commits over {len(weeks)} weeks in {name}")
    print(f"  busiest day {s['Busiest day']}, longest streak {s['Longest streak']}, top weekday {s['Top weekday']}")
    print(f"  wrote {out / 'skyline.svg'} ({len(svg.encode()) / 1024:.1f} KB), {out / 'song.wav'} "
          f"({len(song) / SR:.1f} s), {out / 'index.html'}")


if __name__ == "__main__":
    main()
