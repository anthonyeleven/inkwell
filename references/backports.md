# Backports

The rules come from `SubmittingPatches-backports.rst` on main. `backport.py` does what `src/script/ceph-backport.sh` does, adds the checks below, and pushes nothing until `open`.

## Policy

- **Which branches:** the parent issue's Backport field, newest first. The stable branches today are `umbrella`, `tentacle` and `squid`. A target EOL date is no reason to skip a branch, because EOL dates slip.
- **When:** after the main PR merges. Before that, run only `backport.py check`.
- **Shape:** one backport PR per main PR per release. Don't combine main PRs, even ones that must land together; say so in each PR instead.
- **Clean picks:** prefer them. If a branch conflicts, first consider making the main commit add-only, before it merges, so it picks cleanly.
- **Skipping a branch:** do it when the pick needs real rework, or when the docs build would break there, for example a `:ref:` target that the branch lacks. Clear that branch from the Backport field, with a note.
- **Whose job:** the Upkeep Bot assigns backport issues to the main PR's author. Don't open a backport of someone else's PR without asking them on the backport issue first.

## Check (before and after the merge)

```bash
python3 -I scripts/backport.py check 73213 umbrella tentacle squid
#   umbrella: clean, same line counts
#   tentacle: clean, same line counts
#   squid: CONFLICT at bd449702833 ...: doc/rados/configuration/network-config-ref.rst
```

The check chains `git merge-tree` picks without a worktree. Then it does two more checks:

- It compares `git diff --numstat` against main. A difference means a "clean" pick changed different lines: the usual victim is `PendingReleaseNotes`, where a reworded line lands as an addition or drags in a main-only block.
- It confirms that every `:ref:`, `:confval:` and `:doc:` target in the added doc lines exists on that branch, after the pick. MISSING breaks the docs build; "check" means the target is defined somewhere other than the options YAML, so look by hand.

## Prep, then open

```bash
python3 -I scripts/backport.py prep 73213            # every backport issue on the parent
python3 -I scripts/backport.py prep 73213 --releases tentacle
# review $BACKPORT_WORKDIR/pr-bp-<issue>-body.md, then, with the human's go:
python3 -I scripts/backport.py open 82401
```

`prep`, for each backport issue (from `copied_to` relations, release from custom field 16):

- worktree `$BACKPORT_WORKDIR/bp-<issue>-<release>` on `upstream/<release>`, branch `wip-<issue>-<release>`;
- `git cherry-pick -x` of the main PR's commits, with you as committer and the original author kept;
- the body file:

```
backport tracker: https://tracker.ceph.com/issues/<backport issue>

---

backport of https://github.com/ceph/ceph/pull/<main PR>
parent tracker: https://tracker.ceph.com/issues/<parent>

<the main PR's description, minus Fixes: lines and @mention paragraphs>

Clean cherry-pick of N commits, with the same line changes as on main.

<the main PR's template section and trailers>
```

`open` checks that the worktree is clean and that every new commit's committer is you. Then it pushes, opens the PR (ready, base and milestone = release, title `<release>: <main PR title>`), and sets the backport issue to Fix Under Review with the PR ID, assigned to you. The audit reads that PR ID; if the audit ran before it was set, comment `/audit retest`.

## Conflicts

`prep` stops on that release and leaves the worktree mid-pick. Resolve it, then:

```bash
git -c user.name="$CEPH_GIT_NAME" -c user.email="$CEPH_GIT_EMAIL" cherry-pick --continue
git commit --amend    # add the Conflicts block below the "(cherry picked from commit ...)" line
```

```
(cherry picked from commit 0123456789abcdef...)

Conflicts:
	src/common/options/mds.yaml.in
	- main has newer options after this one; kept only the new option
```

List every file you changed by hand, not just the ones git flagged. Rerun `prep` to write the body, and replace its "LINE COUNTS DIFFER" sentence with a summary of the Conflicts block. Expect the Backport Audit to fail. Compare its range diff with the Conflicts block, and when they match, a maintainer or release manager comments `/audit override`.

## After the merge: the Upkeep Bot

| Event | Bot action |
|---|---|
| Main PR merges, Backport set | Parent to Pending Backport; one backport issue per release, `copied_to` the parent |
| Main PR merges, Backport empty | Parent to Resolved |
| Backport PR merges | That backport issue to Resolved |
| All backport issues resolved | Parent to Resolved |

The bot runs on every merge and every 5 minutes for Pending Backport issues, plus a full pass every 12 hours. It usually takes minutes. If no backport issues appear:

```bash
GH_HOST=github.com gh run list -R ceph/ceph --workflow redmine-upkeep.yml --limit 10
GH_HOST=github.com gh run view <id> -R ceph/ceph --log-failed | grep -i -m5 'error\|422'
```

One bad issue can fail every scheduled run. Report it on that issue or to the release team. If the human wants to go ahead anyway, create the backport issues by hand (see tracker.md), and the bot will skip those releases.
