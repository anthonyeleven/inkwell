# tracker.ceph.com (Redmine)

Anonymous reads work for public issues. Writes need the `X-Redmine-API-Key` header. `scripts/tracker.py` wraps both.

## IDs

| Status | id | | Custom field | id |
|---|---|---|---|---|
| New | 1 | | Backport | 2 |
| In Progress | 2 | | Ceph Release (on backport issues) | 16 |
| Resolved | 3 | | Pull request ID | 21 |
| Closed | 5 | | Merge commit (set by the Upkeep Bot) | 33 |
| Rejected | 6 | | Fixed In (set by the Upkeep Bot) | 34 |
| Won't Fix | 8 | | Released In (set by the Upkeep Bot) | 35 |
| Can't reproduce | 9 | | | |
| Duplicate | 10 | | **Tracker** | **id** |
| Need More Info | 11 | | Bug | 1 |
| Fix Under Review | 13 | | Documentation | 6 |
| Pending Backport | 14 | | Backport | 9 |
| Triaged | 18 | | | |
| Won't Fix - EOL | 19 | | **Project** | **id** |
| Backporting | 40 | | Ceph | 1 |

List the rest with `GET /trackers.json`, `/projects.json?limit=100` and `/issue_statuses.json`.

## Reading

```bash
T=scripts/tracker.py
python3 -I $T show 46992                 # everything, including allowed statuses
python3 -I $T show 46992 --notes 2       # only the last two notes
python3 -I $T find --pr 73323            # which issue names this PR
python3 -I $T scrape --out /tmp/docs     # all open Documentation issues
python3 -I $T scrape --out /tmp/cfs --tracker 1 --project cephfs --status open
```

Raw queries: `GET /issues.json?tracker_id=6&status_id=open&limit=100&offset=0&sort=id`. `status_id` takes `open`, `closed`, `*` or an id. `cf_21=<PR>` filters by PR ID. `subject=~<text>` matches a substring. `GET /issues/N.json?include=journals,relations,allowed_statuses` returns one issue with its notes.

## Writing

```bash
python3 -I $T update N --note-file note.txt --status resolved --dry-run   # show the payload
python3 -I $T update N --note-file note.txt --status resolved
python3 -I $T update N --status fix-under-review --pr 73323 --backport umbrella,tentacle,squid
python3 -I $T relate N M                       # relates
python3 -I $T relate N M --type duplicates     # N duplicates M
```

| Gotcha | What to do |
|---|---|
| A refused status returns 204, applies the other fields, and keeps the old status | Check `allowed_statuses` first; `update` refuses an unlisted status, and a read-back catches the rest |
| The Backport field is a comma list | Newest release first, no spaces, e.g. `umbrella,tentacle,squid` (the bot also accepts spaces) |
| A Backport issue's PR ID can stay locked while its status is New | Set In Progress or Fix Under Review in the same update |
| Notes render as Textile, not Markdown | `@code@`, `<pre>...</pre>`, `"text":URL`; a bare `<word>` shows literally |
| Your role may not allow Resolved on a parent issue | Leave it for the Upkeep Bot, which resolves the parent once every `copied_to` backport issue is resolved |

## Backport issues by hand

The Upkeep Bot creates them, so do this only when its runs are failing (see backports.md). Mirror what the bot does:

- the same project as the parent;
- tracker 9 (Backport) and priority 4 (Normal);
- subject `<release>: <parent subject>`;
- custom field 16 set to the release;
- then `POST /issues/<parent>/relations.json` with `{"relation":{"issue_to_id":<new>,"relation_type":"copied_to"}}`.

The bot skips any release that already has one.
