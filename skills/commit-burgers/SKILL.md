---
name: commit-burgers
description: Turn a git repository's last year of commits into a 3D burger skyline SVG, a marimba song WAV and a page that plays both. Use when the user wants a picture or a fun recap of their commit history, a GitHub profile image, or "my year in code".
---

# commit-burgers

Draws one burger layer per commit for every day of the last 53 weeks (isometric 3D, animated SVG), and plays the year
as a song: one marimba note per active week, higher for busier weeks, a glockenspiel on the busiest one.

## Run

From the repository root of this skill (Python 3.8+ and numpy):

```bash
python commit_burgers.py PATH/TO/REPO -o commit-burgers-out
python commit_burgers.py PATH/TO/REPO --author "Their Name" --title "my 2026" -o out
python commit_burgers.py --demo -o out        # synthetic year, no repo needed
```

Output folder:
- `skyline.svg`: the picture. It animates once on load and works in a GitHub README (`![](skyline.svg)`).
- `song.wav`: 48 kHz stereo, `--step` seconds per week (default 0.2, so a full year is about 11.6 s).
- `index.html`: the skyline plus a "Play the year" button that drops the burgers in time with the song.

## How to use it for the user
1. Ask which repo and, if it is shared, whose commits (`--author`). Default is all commits on the current branch.
2. Run the command, then show the printed summary (total, busiest day, longest streak, top weekday).
3. Offer `skyline.svg` for their profile README and `index.html` to open locally.

Notes: it only reads `git log`; nothing is sent anywhere. Days with more than 4 commits show 4 layers and a red "+".
