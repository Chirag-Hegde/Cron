#!/usr/bin/env python3
"""Prepare the day's work in this week's rotation repo.

Splits the job into the part a script can do and the part it cannot:

  * resolving the target, syncing it, and *finding* real defects -- automated
  * deciding what to change and whether the diff is good -- a human

So this never commits on its own. `--report` surfaces candidates, `--commit`
lands work you have already staged and reviewed. Nothing in between.

Every detector below flags something genuinely worth fixing -- tracked build
output, absent .gitignore, committed secrets. None of them invent busywork.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rotate  # noqa: E402


class GitError(RuntimeError):
    """A git subprocess exited non-zero; message carries stdout+stderr."""


def git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise GitError("`git -C {} {}` failed ({})\n  stderr: {}".format(
            repo, " ".join(args), proc.returncode,
            proc.stderr.strip() or "(empty)"))
    return proc.stdout.strip()


def default_branch(repo: Path) -> str:
    """The remote's default branch. Never assume -- these repos are `master`
    while Cron is `main`, and pushing to the wrong one counts for nothing."""
    ref = git(repo, "symbolic-ref", "--quiet", "--short",
              "refs/remotes/origin/HEAD", check=False)
    if ref:
        return ref.split("/", 1)[-1]
    git(repo, "remote", "set-head", "origin", "-a", check=False)
    ref = git(repo, "symbolic-ref", "--quiet", "--short",
              "refs/remotes/origin/HEAD", check=False)
    return ref.split("/", 1)[-1] if ref else "master"


# -- detectors ---------------------------------------------------------------
# Each returns a list of human-readable findings. Deliberately conservative:
# a false positive wastes review time, which is the scarce resource here.

BUILD_ARTIFACT_SUFFIXES = {
    ".o", ".obj", ".pyc", ".pyo", ".class", ".exe", ".dll", ".so", ".dylib",
    ".a", ".lib", ".jar", ".war", ".apk", ".aab",
}
BUILD_ARTIFACT_DIRS = {
    "obj", "build", "dist", "out", "node_modules", "__pycache__", "target",
    ".gradle", ".next", "venv", ".venv", "bin",
}
OS_NOISE = {".DS_Store", "Thumbs.db", "desktop.ini"}
SECRET_NAMES = {".env", ".env.local", ".env.production", "credentials.json",
                "serviceAccountKey.json", "secrets.yaml"}


def find_tracked_artifacts(files: list[str]) -> list[str]:
    hits = []
    for f in files:
        p = Path(f)
        if p.suffix.lower() in BUILD_ARTIFACT_SUFFIXES:
            hits.append(f)
        elif any(part in BUILD_ARTIFACT_DIRS for part in p.parts[:-1]):
            hits.append(f)
    return hits


def find_os_noise(files: list[str]) -> list[str]:
    return [f for f in files if Path(f).name in OS_NOISE]


def find_secrets(files: list[str]) -> list[str]:
    return [f for f in files if Path(f).name in SECRET_NAMES]


def find_whitespace_issues(repo: Path, files: list[str]) -> list[str]:
    """Source files with trailing whitespace or a missing final newline."""
    source = {".py", ".c", ".h", ".cpp", ".hpp", ".js", ".jsx", ".ts", ".tsx",
              ".kt", ".java", ".css", ".scss", ".html", ".md", ".yml", ".yaml"}
    hits = []
    for f in files:
        p = repo / f
        if p.suffix.lower() not in source or not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        problems = []
        if any(line.rstrip("\n").endswith((" ", "\t")) for line in text.splitlines(True)):
            problems.append("trailing whitespace")
        if text and not text.endswith("\n"):
            problems.append("no final newline")
        if problems:
            hits.append("{} ({})".format(f, ", ".join(problems)))
    return hits


def report(repo: Path, name: str) -> int:
    files = [f for f in git(repo, "ls-files").splitlines() if f]
    branch = default_branch(repo)

    print("repo     {}".format(name))
    print("path     {}".format(repo))
    print("branch   {} (remote default)".format(branch))
    print("tracked  {} files, {} commits".format(
        len(files), git(repo, "rev-list", "--count", "HEAD")))
    print()

    findings: list[tuple[str, list[str]]] = []

    artifacts = find_tracked_artifacts(files)
    if artifacts:
        findings.append((
            "Build artifacts are committed -- they bloat the repo and conflict "
            "on every checkout", artifacts))

    if ".gitignore" not in files:
        findings.append(("No .gitignore -- nothing stops artifacts coming back",
                         ["(repo root)"]))

    noise = find_os_noise(files)
    if noise:
        findings.append(("OS metadata committed", noise))

    secrets = find_secrets(files)
    if secrets:
        findings.append((
            "!! Possible committed secrets -- review before touching anything, "
            "and rotate the credentials if real", secrets))

    ws = find_whitespace_issues(repo, files)
    if ws:
        findings.append(("Whitespace hygiene", ws))

    if not findings:
        print("No automated findings. Anything worth doing here needs a human "
              "reading the code.")
        return 0

    total = 0
    for title, items in findings:
        print("{}".format(title))
        for it in items[:15]:
            print("    {}".format(it))
        if len(items) > 15:
            print("    ... and {} more".format(len(items) - 15))
        print()
        total += len(items)
    print("{} candidate(s). Nothing has been changed.".format(total))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="override the rotation's pick")
    parser.add_argument("--no-pull", action="store_true",
                        help="skip syncing with origin")
    parser.add_argument("--commit", metavar="MSG",
                        help="commit ALREADY-STAGED changes with MSG and push")
    parser.add_argument("--queue", metavar="MSG",
                        help="commit ALREADY-STAGED changes locally WITHOUT "
                             "pushing -- adds to the release queue")
    parser.add_argument("--release", action="store_true",
                        help="push exactly one queued commit (the oldest)")
    parser.add_argument("--queue-status", action="store_true",
                        help="list commits waiting to be released")
    args = parser.parse_args(argv)

    name = args.repo or rotate.pick(__import__("datetime").date.today())
    repo = rotate.CLONE_ROOT / name

    if not (repo / ".git").is_dir():
        print("ERROR: {} is not a clone. Run the clone step first.".format(repo),
              file=sys.stderr)
        return 1

    if not args.no_pull:
        git(repo, "pull", "--rebase", "--autostash")

    if args.queue_status or args.release:
        branch = default_branch(repo)
        git(repo, "fetch", "--quiet", "origin", check=False)
        pending = [c for c in git(
            repo, "rev-list", "--reverse",
            "origin/{}..HEAD".format(branch)).splitlines() if c]

        if args.queue_status:
            print("{}: {} commit(s) queued for release".format(name, len(pending)))
            for sha in pending:
                print("  {}".format(git(repo, "log", "-1", "--oneline", sha)))
            return 0

        if not pending:
            print("Queue empty for {}. Nothing to release.".format(name))
            return 0

        # Push only the oldest. `sha:branch` advances the remote to exactly
        # that commit, leaving the rest queued for subsequent days.
        oldest = pending[0]
        git(repo, "push", "origin", "{}:{}".format(oldest, branch))
        print("released: {}".format(git(repo, "log", "-1", "--oneline", oldest)))
        print("{} commit(s) still queued".format(len(pending) - 1))
        return 0

    if args.queue:
        staged = git(repo, "diff", "--cached", "--name-only")
        if not staged:
            print("Nothing staged in {}.".format(repo), file=sys.stderr)
            return 1
        git(repo, "commit", "-m", args.queue)
        print("queued (not pushed): {}".format(
            git(repo, "log", "-1", "--oneline")))
        return 0

    if args.commit:
        staged = git(repo, "diff", "--cached", "--name-only")
        if not staged:
            print("Nothing staged in {}. Stage the reviewed changes first."
                  .format(repo), file=sys.stderr)
            return 1
        branch = default_branch(repo)
        print("staged:\n  " + "\n  ".join(staged.splitlines()))
        git(repo, "commit", "-m", args.commit)
        print("committed: {}".format(git(repo, "log", "-1", "--oneline")))
        git(repo, "push", "origin", "HEAD:{}".format(branch))
        print("pushed to origin/{}".format(branch))
        return 0

    return report(repo, name)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GitError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        raise SystemExit(1)
