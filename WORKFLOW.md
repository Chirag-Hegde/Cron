# Daily commit workflow

Everything needed to run, debug, or hand off this system. Written so it is
usable with no prior context.

## What this is

Two scheduled jobs plus a weekly human session. The goal is daily commits on
GitHub that are backed by real changes, without a human doing something every
morning.

| Job | Time | What it does | Needs you? |
|---|---|---|---|
| `com.chirag.update-readme` | 09:30 | Rewrites the dated line in this repo's README, commits, pushes | No |
| `com.chirag.daily-prep` | 09:35 | Releases **one** queued commit in this week's rotation repo | No |

Neither job can invent a change. The 09:35 job only pushes commits a human
already wrote and reviewed.

## The weekly rhythm

**Monday** — one session, ~10 minutes:

1. See which repo is up: `python3 scripts/rotate.py`
2. See what it needs: `python3 scripts/daily.py`
3. Work through the findings with Claude, or by hand. For each change:
   ```bash
   cd ~/repos/<repo>
   # make the edit, then:
   git add <files>
   python3 ~/Cron/scripts/daily.py --queue "type: short summary

   Why this change matters."
   ```
4. Confirm the queue: `python3 scripts/daily.py --queue-status`

**Tuesday–Sunday** — nothing. 09:35 releases one queued commit per day.

If the queue empties mid-week the job prints `Queue empty` and exits 0. No
error, no mail, just no commit that day.

## How the queue works

There is no queue file. Git *is* the queue: `--queue` commits locally without
pushing, so queued work is simply the set of local commits ahead of
`origin/<default branch>`. `--release` pushes exactly the oldest one with
`git push origin <sha>:<branch>`, which advances the remote to that commit and
leaves the rest waiting.

Inspect it any time with `git log origin/master..HEAD` inside the repo.

## Commands

```bash
python3 scripts/rotate.py                  # this week's repo
python3 scripts/rotate.py --list 14        # the schedule ahead
python3 scripts/rotate.py --path           # its clone location

python3 scripts/daily.py                   # sync + report findings
python3 scripts/daily.py --repo Portfolio  # target a specific repo
python3 scripts/daily.py --queue "msg"     # commit staged work, do NOT push
python3 scripts/daily.py --queue-status    # what is waiting
python3 scripts/daily.py --release         # push one (what 09:35 runs)
python3 scripts/daily.py --commit "msg"    # commit AND push immediately

python3 scripts/update_readme.py --dry-run # preview the README job
```

## Layout

```
~/Cron/                       this repo: scripts, launchd plists, docs
~/repos/<14 clones>/          the repos being worked on
~/logs/update-readme.log      09:30 job output
~/logs/daily-prep.log         09:35 job output
~/.ssh/github_chirag          auth key (never leaves the machine)
```

## Things that will bite you

**The 14 repos are on `master`. This repo is on `main`.** Never hardcode a
branch name. Both scripts resolve it from `origin/HEAD`; anything new must too,
or it pushes to a branch that does not count as a contribution.

**Do not move the clones into `~/Desktop` or `~/Documents`.** macOS TCC blocks
launchd agents from reading those without Full Disk Access, and the job fails
silently. This is why the repos live in `~/repos` and this one in `~/Cron`.

**Commits only count if the author email is verified on GitHub.** This is set
per-repo to `hegdechirag321@gmail.com`. Verify attribution with:
```bash
gh api repos/Chirag-Hegde/<repo>/commits/<sha> --jq '.author.login'
```
A `null` means the email is not linked and the commit will never turn green.
Attribution resolves at push time and is not retroactive.

**Forks do not count.** `rotate.py` excludes the five forked repos deliberately.

**A missed 09:30/09:35 slot fires on wake.** `StartCalendarInterval` catches up
after sleep or shutdown. Plain cron does not, which is why this uses launchd.

## Triggering a job manually

```bash
launchctl kickstart -k gui/501/com.chirag.update-readme
launchctl kickstart -k gui/501/com.chirag.daily-prep
tail -20 ~/logs/daily-prep.log
```

This runs it under launchd's own near-empty environment, so it catches a broken
PATH or an unreadable key — failures that never show up when you run the script
from a normal shell.

## Reinstalling the jobs

```bash
cp launchd/*.plist ~/Library/LaunchAgents/
launchctl bootout gui/501/com.chirag.daily-prep 2>/dev/null
launchctl bootstrap gui/501 ~/Library/LaunchAgents/com.chirag.daily-prep.plist
launchctl list | grep chirag
```

## Honest limits

The supply of genuinely fixable problems in these repos is finite. Measured on
2026-07-24: roughly 13 substantive fixes remain (tracked build artifacts,
missing `.gitignore` files) plus ~119 whitespace issues. At one commit per day
the substantive work is about two weeks; the whitespace stretches it further
but is cosmetic.

When it runs out, the honest options are to stop, or to do actual feature work.
Padding the graph with commits whose messages oversell their diffs is visible
to anyone who clicks one, and is worse than a sparse graph.
