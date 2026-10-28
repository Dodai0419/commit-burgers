import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import commit_burgers as cb  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
END = dt.date(2026, 10, 23)


def uses(svg, ref):
    return sorted((int(x), int(y)) for x, y in re.findall(rf'<use (?:class="\w+" )?href="#{ref}" x="(-?\d+)" y="(-?\d+)"', svg))


class GitLog(unittest.TestCase):
    def test_counts_commits_per_day_from_a_real_repo(self):
        with tempfile.TemporaryDirectory() as d:
            env = {**os.environ, "GIT_AUTHOR_NAME": "a", "GIT_AUTHOR_EMAIL": "a@b", "GIT_COMMITTER_NAME": "a",
                   "GIT_COMMITTER_EMAIL": "a@b"}
            subprocess.run(["git", "init", "-q", d], check=True)
            for day in ["2026-10-20", "2026-10-20", "2026-10-22"]:
                e = {**env, "GIT_AUTHOR_DATE": f"{day}T12:00:00", "GIT_COMMITTER_DATE": f"{day}T12:00:00"}
                subprocess.run(["git", "-C", d, "commit", "-q", "--allow-empty", "-m", "x"], check=True, env=e)
            counts = cb.git_counts(d, since="2026-01-01")
        self.assertEqual(counts, {dt.date(2026, 10, 20): 2, dt.date(2026, 10, 22): 1})


class Grid(unittest.TestCase):
    def test_full_year_is_53_weeks_and_future_days_are_empty(self):
        weeks = cb.build_weeks(cb.demo_counts(END), END)
        self.assertEqual(len(weeks), 53)
        self.assertTrue(all(len(w) == 7 for w in weeks))
        self.assertIsNone(weeks[-1][6])  # Sunday 2026-10-25 is after END (a Friday)
        self.assertIsNotNone(weeks[-1][4])

    def test_short_history_keeps_at_least_12_weeks(self):
        weeks = cb.build_weeks({END: 3}, END)
        self.assertEqual(len(weeks), 12)

    def test_busiest_day_gets_the_flag(self):
        counts = {END - dt.timedelta(days=3): 9, END: 2}
        weeks = cb.build_weeks(counts, END)
        flagged = [c for w in weeks for c in w if c and c["mark"]]
        self.assertEqual([c["count"] for c in flagged], [9])


class Skyline(unittest.TestCase):
    """Same geometry as zhutoumeme/mcd-git card_skyline.render_svg (fixture made by bench/make_fixtures.py)."""

    def check(self, name, counts):
        want = json.loads((FIX / f"skyline_{name}.json").read_text())
        svg = cb.render_svg(cb.build_weeks(counts, END))
        for ref in ("tile", "b", "c", "p", "fl"):
            self.assertEqual([list(u) for u in uses(svg, ref)], want[ref], ref)
        self.assertEqual(re.findall(r'<g transform="[^"]+">', svg), want["layout"])

    def test_full_year_matches_upstream(self):
        self.check("demo", cb.demo_counts(END))

    def test_sparse_short_history_matches_upstream_scaling(self):
        self.check("sparse", {END - dt.timedelta(days=d): (d % 6) + 1 for d in range(0, 90, 4)})


class Song(unittest.TestCase):
    def test_marimba_note_matches_earshot(self):
        want = json.loads((FIX / "earshot_notes.json").read_text())
        for case in want:
            y = cb.voice(case["params"], cb.np.random.default_rng(case["seed"]), case["n"], case["f0"])
            got = [round(float(v), 6) for v in y[::case["stride"]]]
            self.assertEqual(len(got), len(case["samples"]))
            self.assertLess(max(abs(a - b) for a, b in zip(got, case["samples"])), 2e-6, case["name"])

    def test_song_has_one_note_per_active_week_and_is_not_clipped(self):
        weeks = cb.build_weeks(cb.demo_counts(END), END)
        notes = cb.melody(weeks)
        active = sum(1 for w in weeks if any(c and c["count"] for c in w))
        self.assertEqual(len(notes), active)
        x = cb.render_song(notes, len(weeks), step=0.2)
        self.assertEqual(x.shape[1], 2)
        self.assertAlmostEqual(abs(x).max(), 10 ** (-1 / 20), places=3)


class Cli(unittest.TestCase):
    def test_demo_writes_svg_wav_and_page(self):
        with tempfile.TemporaryDirectory() as d:
            env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
            r = subprocess.run([sys.executable, str(ROOT / "commit_burgers.py"), "--demo", "-o", d],
                               capture_output=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
            out = r.stdout.decode("utf-8")
            self.assertIn("commits", out)
            svg = Path(d, "skyline.svg").read_text(encoding="utf-8")
            self.assertTrue(svg.startswith("<svg") and svg.rstrip().endswith("</svg>"))
            with wave.open(str(Path(d, "song.wav"))) as w:
                self.assertEqual((w.getnchannels(), w.getframerate(), w.getsampwidth()), (2, 48000, 2))
                self.assertGreater(w.getnframes(), 48000 * 5)
            page = Path(d, "index.html").read_text(encoding="utf-8")
            self.assertIn("song.wav", page)
            self.assertIn("<svg", page)


if __name__ == "__main__":
    unittest.main()
