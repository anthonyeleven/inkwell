# ceph/ceph PRs, checks, and bots

## Branch and commit

```bash
git -C $CEPH_GIT fetch -q upstream
git -C $CEPH_GIT worktree add --no-track -b wip-<topic> $WT upstream/main   # never a stale local branch
git -C $WT -c user.name="$CEPH_GIT_NAME" -c user.email="$CEPH_GIT_EMAIL" commit -F msg.txt
git -C $WT log -1 --format='%an <%ae>%n%cn <%ce>'    # check author AND committer; rebases reset the committer
```

The commit message follows `SubmittingPatches.rst`:

```
doc/radosgw: document lifecycle scheduling and multisite behavior

<what was missing, what this says, and how the code shows it>

Fixes: https://tracker.ceph.com/issues/46992
Signed-off-by: Your Name <login@users.noreply.github.com>
Assisted-by: <model name, if an AI helped>
```

- **Subject prefix:** the highest-level directory that holds the change, then a colon.
- **Subject wording:** imperative, with no trailing period.
- **Commits:** code goes in one commit; docs may get their own.
- **Signed-off-by:** required, because the DCO check (`Signed-off-by`) fails without it.
- **Assisted-by:** this is the kernel's trailer for AI help. `Co-authored-by` implies authorship under the DCO, so don't use it for that.
- **Docs style:** American English, lines of 80 characters or fewer, and `:confval:` and `:ref:` for options and cross-references (see `doc/start/documenting-ceph.rst`).

## PR

```bash
git -C $WT push -q origin wip-<topic>       # needs the gh token's workflow scope if upstream
                                            # changed .github/workflows since your fork synced
gh pr create -R ceph/ceph --draft --base main --head <login>:wip-<topic> \
  --title "<same as the commit subject>" --body-file body.md
```

- **Body:** `Fixes: <tracker URL>` on the first line, then what the PR changes and why, then the repo's `.github/pull_request_template.md` with the boxes ticked. End with the same `Signed-off-by` and `Assisted-by` lines as the commit.
- **Draft:** main-branch PRs open as drafts, and the human marks them ready. Backport PRs open ready.
- **Reviewers:** tag the component lead, who is the maintainer most active in that file's `git log`. Ask one concrete question in the body.
- **Follow-up changes:** amend the commit and force-push with `--force-with-lease`. The repo expects tidy history, not fixup commits.
- **Reopening a closed PR:** reopen it before you force-push its branch. GitHub won't reopen a PR whose head moved after it closed.

## Checks

| Check | Fails when | Fix |
|---|---|---|
| `Signed-off-by` | A commit lacks the DCO trailer | Amend, then force-push |
| `Verify Checklist` | The template checklist has no box ticked in a section | Edit the PR body |
| `docs/readthedocs.org:ceph` | The Sphinx build warns or errors, for example a missing `:ref:` target or a bad heading level | Fix it locally; retrigger with `jenkins test docs` |
| `make check`, `make check (arm64)`, `ceph API tests`, `ceph windows tests` | A Jenkins build or test fails | Read the console link; retrigger with `jenkins test make check` etc. |
| `pull_request` (Check Ceph config changes) | The PR changes `src/common/options/*.yaml.in` | See "Config diff" below |
| `Backport Audit` / `Execution and Routing` | A backport doesn't match its main PR | See "Backport Audit" below |
| `needs-rebase` | The PR conflicts with its base | Rebase onto fresh upstream, then force-push |
| `Check PR Dependencies` | A `Depends on #N` line names an open PR | Wait, or drop the line |
| `check-permissions` | First-time contributor | A maintainer adds `ci-approved` |
| `Check for missing .qa links` | A new `qa/suites` directory has no `.qa` symlink | Add the link |
| `.githubmap check` | A reviewer isn't in `.githubmap` | That reviewer's own PR to `.githubmap`; doesn't block you |

`prs.py status N` lists only the checks that aren't green, using the latest run of each.

Jenkins and RTD trigger phrases go **one per comment**, exactly as the PR template lists them: `prs.py jenkins N "jenkins test docs"`.

## Config diff ("Check Ceph config changes")

Any change to an option's definition, including only its `desc`, makes the bot post `### Config Diff Tool Output` and fail the check. The check is a reminder to update release documentation such as `PendingReleaseNotes`, when a release note applies.

1. Decide whether a release note is needed. For new or changed defaults, usually yes; for description-only edits, usually no.
2. Comment `/config check ok`. Then re-run the failed run: the check reruns only on push, edit, or reopen, not on a comment. `prs.py config-ok N` does both.

## Backport Audit (release branches only)

The audit cherry-picks the main PR itself and compares the result with the backport. Any conflict resolution counts as a deviation, even one that a correct `Conflicts:` block explains, so a resolved backport fails the audit as a rule. Its comment includes a range diff.

| Command (comment) | Who | Effect |
|---|---|---|
| `/audit retest` | Anyone | Runs the audit again: after fixing the PR, or after setting the backport issue's PR ID, which the audit reads |
| `/audit override` | Repo maintain/admin or `@ceph/ceph-release-manager` | Marks it passed: label `releng-audit-override`, status green |
| `/audit test-branch <branch>` | Same as override | Runs the tooling from another branch; no state change |

Override only after you have read the range diff and it shows nothing beyond what the commit's `Conflicts:` block lists. Afterwards the `Execution and Routing` job of the failed run stays red, while `Backport Audit` turns green. Labels: `releng-audit-pass`, `-fail`, `-override`, `-queue`.

## Other bots

| Bot | Does |
|---|---|
| pr-triage (labeler) | Adds component labels from the paths, and the milestone from the base branch |
| stale | Labels a PR `stale` after 60 days of no activity and closes it 30 days later; `pinned` exempts it |
| Upkeep Bot (`redmine-upkeep.yml`) | On merge: sets Merge commit and Fixed In, and moves the issue to Pending Backport, or to Resolved if Backport is empty. It creates the backport issues, resolves a backport issue when its PR merges, and resolves the parent once every backport issue is resolved. It finds the issue by Pull request ID, or by `Fixes:` lines in the merged commits |

Once a code PR is approved, add `needs-qa` (or ask a maintainer to) so that it goes into a QA test batch. Code PRs merge only after QA. Docs-only PRs skip QA.
