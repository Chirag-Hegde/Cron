#!/usr/bin/env python3
"""Pick which repository this week's work targets.

Deterministic: the same date always resolves to the same repo, on any machine,
with no state file to drift or lose. The schedule is therefore predictable
weeks ahead -- run `--list` to see it.

Forks are deliberately excluded. Commits inside a fork do not count toward the
GitHub contribution graph, so rotating through them would produce nothing.
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

OWNER = "Chirag-Hegde"

# Where clones live. NOT ~/Desktop or ~/Documents: macOS TCC blocks launchd
# agents from reading those without Full Disk Access, and the job fails silently.
CLONE_ROOT = Path.home() / "repos"

# The 14 non-fork public repos, in a fixed order. Appending to this list shifts
# the schedule for future weeks but never retroactively changes past picks.
REPOS = [
    "SUMMA-based-Dense-Matrix-Matrix-Mutiplication",
    "Travel_Agent",
    "Portfolio",
    "PersonalDoctor_Ai-LLM-based-Healthcare",
    "Student-Attentiveness-checker",
    "Plan-Your-Travel",
    "Good-Habits",
    "Job-Tracker",
    "Ecommerce-using-Next.js-Prisma-Tailwind-CSS-TypeScript",
    "Parallel-Sudoku-Solver",
    "Sign-Language-Detection-using-Deep-Learning",
    "News-Classification-using-Transformers",
    "QuizApp",
    "MedXpert",
]

# A Monday. Week indices count from here, so the rotation does not reset or
# double-pick at a year boundary the way ISO week numbers would.
ANCHOR = dt.date(2026, 1, 5)


def week_start(day: dt.date) -> dt.date:
    """The Monday of the week containing `day`."""
    return day - dt.timedelta(days=day.weekday())


def week_index(day: dt.date) -> int:
    return (week_start(day) - ANCHOR).days // 7


def pick(day: dt.date) -> str:
    return REPOS[week_index(day) % len(REPOS)]


def clone_url(name: str) -> str:
    return "git@github.com:{}/{}.git".format(OWNER, name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="ISO date to resolve instead of today")
    parser.add_argument("--list", type=int, metavar="N", nargs="?", const=14,
                        help="print the next N weeks of the schedule")
    parser.add_argument("--path", action="store_true",
                        help="print the clone path instead of the repo name")
    args = parser.parse_args(argv)

    day = dt.date.fromisoformat(args.date) if args.date else dt.date.today()

    if args.list is not None:
        start = week_start(day)
        for i in range(args.list):
            monday = start + dt.timedelta(weeks=i)
            marker = " <- current" if i == 0 else ""
            print("week of {}  {}{}".format(monday, pick(monday), marker))
        return 0

    name = pick(day)
    print(CLONE_ROOT / name if args.path else name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
