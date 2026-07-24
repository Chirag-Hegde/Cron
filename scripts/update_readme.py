#!/usr/bin/env python3
"""Maintain a single dated line in README.md, then commit and push it.

Designed to be run unattended by a scheduler (launchd / systemd), so:
  * every path is derived from __file__, never the cwd
  * an unchanged tree is a success (exit 0), not an error -- otherwise the
    scheduler mails a failure every single day
  * git failures raise with stderr attached, so the log gets a readable line
    instead of a bare traceback
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import subprocess
import sys
from pathlib import Path

MARKER = "<!-- updated -->"

# Absolute, cwd-independent. scripts/update_readme.py -> repo root is parent.parent.
REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"


class GitError(RuntimeError):
    """A git subprocess exited non-zero; message carries stdout+stderr."""


def git(*args: str, check: bool = True, verbose: bool = False) -> str:
    """Run git inside the repo and return stdout, raising GitError on failure."""
    cmd = ["git", "-C", str(REPO_ROOT), *args]
    if verbose:
        print("$ " + " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise GitError(
            "`{}` failed with exit {}\n  stdout: {}\n  stderr: {}".format(
                " ".join(cmd),
                proc.returncode,
                proc.stdout.strip() or "(empty)",
                proc.stderr.strip() or "(empty)",
            )
        )
    return proc.stdout.strip()


def has_origin(verbose: bool = False) -> bool:
    remotes = git("remote", check=False, verbose=verbose)
    return "origin" in remotes.split()


def current_branch(verbose: bool = False) -> str:
    return git("rev-parse", "--abbrev-ref", "HEAD", verbose=verbose)


def default_branch(verbose: bool = False) -> str | None:
    """Remote HEAD's branch name, or None if it was never resolved."""
    ref = git("symbolic-ref", "--quiet", "refs/remotes/origin/HEAD",
              check=False, verbose=verbose)
    return ref.rsplit("/", 1)[-1] if ref else None


def desired_line(today: dt.date) -> str:
    return "{} Last updated: {}".format(MARKER, today.isoformat())


def render(old: str, line: str) -> str:
    """Return README content with exactly one MARKER line, rewritten in place.

    Rewrites the existing marker line rather than appending, so a second run on
    the same day is a genuine no-op.
    """
    lines = old.splitlines()
    for i, existing in enumerate(lines):
        if existing.lstrip().startswith(MARKER):
            lines[i] = line
            break
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(line)
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="print the diff that would be made; change nothing")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="echo every git command as it runs")
    args = parser.parse_args(argv)

    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("[{}] update_readme starting in {}".format(stamp, REPO_ROOT), flush=True)

    if not (REPO_ROOT / ".git").exists():
        print("ERROR: {} is not a git repository.".format(REPO_ROOT), file=sys.stderr)
        return 1

    origin = has_origin(verbose=args.verbose)

    # 1. Sync before editing, so the commit lands on top of remote history.
    if args.dry_run:
        print("dry-run: skipping `git pull --rebase --autostash`")
    elif not origin:
        print("WARNING: no `origin` remote configured -- skipping pull.",
              file=sys.stderr)
    else:
        git("pull", "--rebase", "--autostash", verbose=args.verbose)

    # 2. Compute the new README content.
    old = README.read_text(encoding="utf-8") if README.exists() else ""
    new = render(old, desired_line(dt.date.today()))

    if old == new:
        print("No changes: README.md already carries today's date. Nothing to do.")
        return 0

    if args.dry_run:
        diff = difflib.unified_diff(
            old.splitlines(keepends=True), new.splitlines(keepends=True),
            fromfile="a/README.md", tofile="b/README.md",
        )
        sys.stdout.writelines(diff)
        print("\ndry-run: no files written, no commit, no push.")
        return 0

    README.write_text(new, encoding="utf-8")

    # 3. Stage only the target file, so unrelated dirty files are never swept in.
    git("add", "--", "README.md", verbose=args.verbose)

    if not git("status", "--porcelain", "--", "README.md", verbose=args.verbose):
        print("No changes staged for README.md. Nothing to commit.")
        return 0

    branch = current_branch(verbose=args.verbose)
    expected = default_branch(verbose=args.verbose) if origin else None
    if expected and branch != expected:
        print(
            "WARNING: on branch '{}' but origin's default is '{}'. "
            "Commits outside the default branch do not count as "
            "contributions.".format(branch, expected),
            file=sys.stderr,
        )

    git("commit", "-m", "chore: update README timestamp ({})".format(
        dt.date.today().isoformat()), verbose=args.verbose)
    print("Committed: {}".format(git("log", "-1", "--oneline", verbose=args.verbose)))

    if not origin:
        print("WARNING: no `origin` remote -- commit is local only, NOT pushed. "
              "Contributions will not appear on GitHub until a remote is added.",
              file=sys.stderr)
        return 0

    git("push", "origin", branch, verbose=args.verbose)
    print("Pushed {} to origin.".format(branch))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except GitError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        sys.exit(1)
