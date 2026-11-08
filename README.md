# inkwell

An agent skill for the upstream Ceph contribution loop: triaging
tracker.ceph.com issues, fixing them as ceph/ceph PRs, getting the CI
checks and bots green, and backporting to the stable branches.

The background is in the ceph.io post
[Many Arms Make Light Work](https://ceph.io/en/news/blog/2026/inkwell/).

## What's here

* `SKILL.md`: the procedures the agent follows, and the rules that save rework.
* `references/`: triage verdicts, PR and commit conventions, the checks and
  bots, backport policy, and Redmine IDs and recipes.
* `scripts/`: three Python scripts that need only the standard library.
  * `tracker.py` works tracker.ceph.com through the Redmine API.
  * `prs.py` reports a PR's draft state, labels, and failing checks, and posts
    the bot commands and Jenkins trigger phrases.
  * `backport.py` simulates each cherry-pick, then preps and opens backport PRs.

## Install

For Claude Code:

```bash
git clone https://github.com/anthonyeleven/inkwell ~/.claude/skills/inkwell
```

Other agents that read `SKILL.md` skills take the same folder.

It needs Python 3, Git, a `ceph/ceph` clone with your fork as `origin`, the
GitHub CLI authenticated to github.com, and a tracker.ceph.com API key for
tracker writes. The setup table in `SKILL.md` has the details.

## See also

[inkling](https://github.com/anthonyeleven/claude-inkling) is a Claude Code
status line. It shows what a session has cost so far, how full its context is,
and your spend for the month, plus where the month will end at the current
pace. A long triage or backport run can get big, and inkling shows when it's
time for `/compact` or `/clear`.

## License

Apache 2.0. See `LICENSE.txt`.

Fixes and reports are welcome.
