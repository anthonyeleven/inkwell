---
name: inkwell
description: Inkwell works the upstream Ceph contribution loop on tracker.ceph.com and github.com/ceph/ceph. Covers scraping and triaging tracker issues (Redmine API, a verdict taxonomy, closing notes, statuses a project refuses), fixing them as ceph/ceph PRs (commit and PR conventions, draft vs ready), the CI checks and the bots that drive them (Check Ceph config changes and "/config check ok", Backport Audit and "/audit retest|override", Read the Docs and Jenkins trigger phrases, the Redmine Upkeep Bot), and backports to the stable branches (clean-pick checks, wip-ISSUE-RELEASE branches, backport PRs and backport tracker issues). Use for "triage these tracker issues", "open a PR for this tracker", "why is this check red", "backport this to tentacle", or any tracker.ceph.com write.
compatibility: Needs python3, git, a ceph/ceph clone with your fork as origin, gh authenticated to github.com, and a tracker.ceph.com API key for tracker writes.
license: Apache-2.0. Copyright 2026 Anthony D'Atri. Full terms in LICENSE.txt.
---

# Inkwell: the Ceph upstream tracker, PRs, bots, and backports

Every write here is public and carries the human's name: tracker notes and statuses, pushes, PRs, PR comments, and bot commands. **Get the human's explicit go for each one**, show the exact text first, and read every write back. A goal like "close the moot ones" sets direction; it is not a go for a specific issue.

## Setup

| Need | How |
|---|---|
| `gh` on github.com | `gh auth login -h github.com`, scopes `repo` and `workflow`; the scripts set `GH_HOST=github.com` |
| A ceph clone | `$CEPH_GIT` (default `~/git/ceph`): `origin` = your fork, `upstream` = `ceph/ceph` |
| Redmine API key | tracker.ceph.com → My account → API access key; export `REDMINE_API_KEY`, or on macOS keep it in the keychain as service `tracker.ceph.com`, account `$USER` |
| Commit identity | your public GitHub name and `<login>@users.noreply.github.com`, or set `CEPH_GIT_NAME` / `CEPH_GIT_EMAIL` |

The scripts need only Python 3 and its standard library. Run them with `python3 -I`.

## Scripts

| Script | Does |
|---|---|
| `scripts/tracker.py show N` | An issue with fields, relations, allowed statuses, and notes |
| `scripts/tracker.py scrape --out DIR` | Every open issue of a tracker type (default 6, Documentation) into `DIR/txt/<id>.txt` plus `index.tsv` |
| `scripts/tracker.py find --pr N` | Issues whose Pull request ID is N |
| `scripts/tracker.py backports N` | A parent's backport issues: release, status, assignee, PR |
| `scripts/tracker.py update N ...` | Status, note, PR ID, Backport, assignee; refuses a status the workflow won't take, reads back, exits 1 on any field that didn't stick |
| `scripts/tracker.py relate A B` | Add a relation (default `relates`) |
| `scripts/prs.py status N...` | Draft state, labels, failing checks, config-diff and audit bot state |
| `scripts/prs.py overlap PATH... [--grep RE]` | Open PRs that touch a file or directory (cached for an hour) |
| `scripts/prs.py config-ok N` | Post `/config check ok`, re-run the failed config check |
| `scripts/prs.py audit N --retest\|--override` | Backport Audit commands |
| `scripts/prs.py jenkins N "<phrase>"` | One CI trigger phrase from the PR template |
| `scripts/backport.py check PR BRANCH...` | Simulated cherry-pick per branch: conflicts, line counts, doc link targets |
| `scripts/backport.py prep PR` | Worktree, `wip-<issue>-<release>` branch, `cherry-pick -x`, PR body, per backport issue |
| `scripts/backport.py open ISSUE` | Push, open the backport PR, update the backport issue |

## The loop

1. **Triage**: scrape, give each issue a verdict, then decide one issue at a time: close, fix, or leave for its owner. See [references/triage.md](references/triage.md).
2. **Fix**: use a fresh worktree off `upstream/main` with one commit for the code. Docs can go in a separate commit. Put `Fixes: <tracker URL>` in the commit and at the top of the PR body. Open the PR as a draft, then post a `Draft: <PR URL>` note on the issue. When the human says so, set the issue to Fix Under Review with the PR ID and the Backport branches. See [references/prs-and-bots.md](references/prs-and-bots.md).
3. **Checks and bots**: get every check green, and answer the config-diff and audit bots. See [references/prs-and-bots.md](references/prs-and-bots.md).
4. **Merge**: the Upkeep Bot sets the issue to Pending Backport, or to Resolved when Backport is empty, and creates one backport issue per release.
5. **Backports**: open one ready PR per release for each main PR, and set each backport issue to Fix Under Review with its PR ID. When they all merge, the bot resolves everything. See [references/backports.md](references/backports.md).

Redmine IDs and API recipes are in [references/tracker.md](references/tracker.md).

## Rules that save rework

- **Check for toe-stepping before you write anything.** Look at the assignee, the status, the Pull request ID, the latest notes, and any open PR that names the issue or touches the same lines (`prs.py overlap`). If the issue is someone else's, ask them on the tracker before you take it.
- **Verify on main, not from memory.** Before calling an issue done or moot, grep `doc/` and `src/` on a freshly fetched `upstream/main`, and cite `path:line`, the merged PR, or the docs URL.
- **Before offering a status, check `?include=allowed_statuses`.** Redmine answers 204 to a status the issue's workflow refuses and silently keeps the old one. For example, CephFS Documentation issues in In Progress can't move to Fix Under Review.
- **Open main PRs as drafts. Open backport PRs ready.** After a PR is open, its draft state belongs to the human, so change it only when they ask.
- **A clean cherry-pick means the same line counts as main.** A pick with no conflicts can still drag in unrelated hunks, most often in `PendingReleaseNotes`. `backport.py check` compares the `--numstat` output.
- **Name releases so the text reads right on every branch.** For a release that hasn't been branched yet, write "Beginning with the <Name> release", never "Since <Name>". A doc backport may mention later releases, because readers often land on an older branch's docs from a search. So judge a doc backport only on a clean pick and a clean docs build.
