# Triaging tracker issues

This covers a backlog of open issues, for example all 200-odd open Documentation issues. Each one gets closed, fixed, or left for its owner.

## 1. Scrape

```bash
python3 -I scripts/tracker.py scrape --out $D            # Documentation, all projects
git -C $CEPH_GIT fetch -q upstream
git -C $CEPH_GIT worktree add --detach $D/ceph-main upstream/main   # read-only reference tree
```

`$D/txt/<id>.txt` holds the fields, the description, and every note. `$D/index.tsv` has one line per issue.

## 2. Verdicts

Split the ids into batches of 25-55 issues and give each batch to a read-only agent. Have each agent write lines in this exact format: `id | VERDICT | subject | evidence | change or owner`.

| Verdict | Meaning | Evidence it needs |
|---|---|---|
| MOOT-DONE | Already in the docs on main, or fixed by a merged PR or commit | `path:line`, or the PR or commit |
| MOOT-REMOVED | About something gone: ceph-deploy, ceph-disk, FileStore, removed modules, commands, or options, or an EOL-only release | A grep showing it's gone |
| MOOT-DUP | A duplicate | The other issue |
| MOOT-OTHER | Moot for another concrete reason: behavior changed, or the question was answered | Why |
| KNOCK-S | Still valid and writable from code and docs alone; one file, under about 40 lines | The change and the target file |
| KNOCK-M | The same, but a section or a page | The same |
| OWNED | Someone is on it: an open PR, or an assignee active in the last 6 months | Who, and which PR |
| NEEDS-DEV | Needs design input or behavior that can't be read from the code | What's missing |
| UNCLEAR | Can't tell | What would settle it |

Brief the agents:

- Read-only: no tracker or GitHub writes, and no checkout or reset in shared trees.
- Grep `src/` and `doc/` before calling anything MOOT.
- Before calling anything KNOCK, check the assignee, status, Pull request ID, notes, and open PRs. An assignee idle for over a year doesn't block KNOCK; record "assigned to <name>, idle since <date>".
- Ration `gh search`: GitHub's search API allows 30 calls a minute, shared by every agent.

Merge the results into one file sorted by verdict, and keep a ledger with one line per decided issue, such as `46992 pr-73323 fix-under-review backport-umbrella-tentacle-squid`. The tally is then a join of the two files.

## 3. Decide one issue at a time

For each issue, in verdict order (MOOT first, then KNOCK, OWNED, NEEDS-DEV, and UNCLEAR):

1. Re-check it live: `tracker.py show N`. The scrape may be days old, so look for new notes, a new assignee, or a new PR.
2. Re-verify the evidence on fresh `upstream/main`.
3. For a fix, run `prs.py overlap <file> --grep <topic>` to find open PRs already changing the same text.
4. Ask the human about this one issue, and nothing else in the same prompt. Give the title, status, assignee, the evidence, and each option with its exact note text. If someone owns the issue, include "leave it for <owner>".
5. Act on the answer, read the result back, and record it in the ledger before you ask about the next issue.

## Status by outcome

| Outcome | Status |
|---|---|
| Already done on main | Resolved, with a note that cites it |
| Duplicate | Duplicate, plus a `duplicates` relation |
| Obsolete, or answered | Rejected, or Won't Fix for a stale request nobody will do |
| EOL-only | Won't Fix - EOL |
| Fixed by our PR | Fix Under Review, with the PR ID and Backport set |
| Waiting on another PR | Leave the status; add a note and a `relates` relation |

## Closing notes

- Lead with the fact, then the evidence: "Documented on main in `doc/x.rst`: ...", or "Fixed by https://github.com/ceph/ceph/pull/N (merged YYYY-MM-DD)".
- Link the rendered docs page at `https://docs.ceph.com/en/latest/...` when one exists.
- For a release-specific answer, link that release's docs (`/en/<release>/`) and name the first point release that has the fix.
- When closing a support transcript or a vague report, say what a new issue would need.
- No @mentions unless the human asks for them. Redmine notes render as Textile.
