"""Regenerate tests/fixtures from the upstream code (not needed to use or test this repo).

    pip install numpy scipy rich==14.3.0 qrcode==8.2
    git clone https://github.com/zhutoumeme/mcd-git && git clone https://github.com/Leonxlnx/earshot
    python bench/make_fixtures.py path/to/mcd-git path/to/earshot
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
mcd, ear = map(Path, sys.argv[1:3])
sys.path[:0] = [str(mcd / "src"), str(ear)]
import commit_burgers as cb  # noqa: E402
from earshot.forge.recipes import mallet  # noqa: E402
from mcd_git import card_skyline  # noqa: E402

END = dt.date(2026, 10, 23)
FIX = ROOT / "tests" / "fixtures"


def upstream_svg(weeks):
    w = [[None if c is None else {"count": c["count"], "mark": c["mark"]} for c in col] for col in weeks]
    total = sum(c["count"] for col in w for c in col if c)
    model = {"span": {"label": "x"}, "total": total, "topItem": None, "topSlot": None, "savings": None,
             "savingsKnownOrders": None, "desc": "", "mark_date": None, "weeks": w, "footer": ""}
    return card_skyline.render_svg(model)


def geometry(svg):
    g = {ref: sorted([int(x), int(y)] for x, y in re.findall(rf'<use (?:class="\w+" )?href="#{ref}" x="(-?\d+)" y="(-?\d+)"', svg))
         for ref in ("tile", "b", "c", "p", "fl")}
    g["layout"] = re.findall(r'<g transform="[^"]+">', svg)
    return g


cases = {"demo": cb.demo_counts(END), "sparse": {END - dt.timedelta(days=d): (d % 6) + 1 for d in range(0, 90, 4)}}
for name, counts in cases.items():
    (FIX / f"skyline_{name}.json").write_text(json.dumps(geometry(upstream_svg(cb.build_weeks(counts, END)))))

notes = []
for name, fam, f0, seed in [("marimba G4", 3, 392.0, 1), ("marimba D3", 3, 146.8, 2), ("glock doubled", 0, 1568.0, 3)]:
    p = {**mallet.DEFAULTS, **mallet.FAMILY["mallet"][fam], "strike": -60.0}  # contact noise off (needs scipy)
    n = int(mallet._len(p) * cb.SR)
    y = mallet._voice(p, mallet.dsp.rng(seed), n, f0)
    notes.append({"name": name, "seed": seed, "f0": f0, "n": n, "stride": 7,
                  "params": {k: p[k] for k in cb.MARIMBA}, "samples": [round(float(v), 6) for v in y[::7]]})
(FIX / "earshot_notes.json").write_text(json.dumps(notes))
print("fixtures written:", sorted(f.name for f in FIX.iterdir()))
