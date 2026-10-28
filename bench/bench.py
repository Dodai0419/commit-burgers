"""Time the two core operations against upstream, on the same input.

    python bench/bench.py                                   # this repo only
    python bench/bench.py path/to/mcd-git path/to/earshot   # plus upstream (pip install numpy scipy rich qrcode)
"""
import datetime as dt
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import commit_burgers as cb  # noqa: E402

END = dt.date(2026, 10, 23)
WEEKS = cb.build_weeks(cb.demo_counts(END), END)
NOTES = cb.melody(WEEKS)


def ms(fn, n=30, other=None):
    """median ms of fn; with `other`, the two are run alternately so both see the same machine state"""
    runs, alt = [], []
    for _ in range(n):
        for f, acc in ((fn, runs), (other, alt)) if other else ((fn, runs),):
            t = time.perf_counter()
            f()
            acc.append((time.perf_counter() - t) * 1000)
    return (statistics.median(runs), statistics.median(alt)) if other else statistics.median(runs)


def import_ms(code, path):
    runs = []
    for _ in range(5):
        r = subprocess.run([sys.executable, "-c", f"import sys,time;sys.path[:0]={path!r};t=time.perf_counter();{code};"
                            "print((time.perf_counter()-t)*1000)"], capture_output=True, text=True, check=True)
        runs.append(float(r.stdout))
    return statistics.median(runs)


def notes_ours():
    r = cb.np.random.default_rng(1)
    for _, f0, _ in NOTES:
        cb.voice(cb.MARIMBA, r, int(cb.note_len(cb.MARIMBA) * cb.SR), f0)


rows = [("skyline SVG, 53 weeks", ms(lambda: cb.render_svg(WEEKS))),
        (f"{len(NOTES)} marimba notes", ms(notes_ours, 10)),
        ("import", import_ms("import commit_burgers", [str(ROOT)]))]
up = {}
if len(sys.argv) == 3:
    mcd, ear = map(Path, sys.argv[1:3])
    sys.path[:0] = [str(mcd / "src"), str(ear)]
    from earshot.forge.recipes import mallet
    from mcd_git import card_skyline
    w = [[None if c is None else {"count": c["count"], "mark": c["mark"]} for c in col] for col in WEEKS]
    model = {"span": {"label": "x"}, "total": 0, "topItem": None, "topSlot": None, "savings": None,
             "savingsKnownOrders": None, "desc": "", "mark_date": None, "weeks": w, "footer": ""}
    p = {**mallet.DEFAULTS, **mallet.FAMILY["mallet"][3], "strike": -60.0}

    def notes_up():
        r = mallet.dsp.rng(1)
        for _, f0, _ in NOTES:
            mallet._voice(p, r, int(mallet._len(p) * cb.SR), f0)

    rows[0] = rows[0][0], *ms(lambda: cb.render_svg(WEEKS), 30, lambda: card_skyline.render_svg(model))
    rows[1] = rows[1][0], *ms(notes_ours, 10, notes_up)
    up = {rows[0][0]: rows[0][2], rows[1][0]: rows[1][2],
          "import": import_ms("import mcd_git.card_skyline, earshot.forge.recipes.mallet", [str(mcd / "src"), str(ear)])}
print(f"{'operation':28} {'upstream ms':>12} {'this repo ms':>13}")
for name, ours, *_ in rows:
    print(f"{name:28} {up.get(name, float('nan')):12.2f} {ours:13.2f}")
