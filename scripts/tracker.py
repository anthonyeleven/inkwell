#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Anthony D'Atri
"""tracker.ceph.com (Redmine) helper: read, scrape, update, relate.

Reads work without a key. Writes need one: $REDMINE_API_KEY, else the macOS
keychain item service "tracker.ceph.com", account $TRACKER_KEY_ACCOUNT
(default: $USER).

  tracker.py show N [--notes K] [--json]
  tracker.py find --pr N
  tracker.py backports N
  tracker.py scrape --out DIR [--tracker 6] [--status open] [--project ID]
  tracker.py update N [--status S] [--note-file F] [--pr N|none]
                      [--backport umbrella,tentacle,squid|none] [--assign-me]
                      [--dry-run]
  tracker.py relate A B [--type relates]

Every update is read back. A status the issue's workflow refuses is reported
as NOT APPLIED: Redmine answers 204 and silently keeps the old status.
"""
import argparse
import concurrent.futures
import functools
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://tracker.ceph.com"

STATUS = {
    "new": 1, "in-progress": 2, "resolved": 3, "closed": 5, "rejected": 6,
    "wont-fix": 8, "cant-reproduce": 9, "duplicate": 10, "need-more-info": 11,
    "fix-under-review": 13, "pending-backport": 14, "triaged": 18,
    "wont-fix-eol": 19, "backporting": 40, "needs-review": 43,
}
CF = {2: "Backport", 16: "Release", 21: "Pull request ID", 33: "Merge commit",
      34: "Fixed In", 35: "Released In"}


@functools.lru_cache(maxsize=None)
def _lookup_key():
    """The API key from the environment or the macOS keychain, read once per run."""
    k = os.environ.get("REDMINE_API_KEY")
    if k:
        return k
    acct = os.environ.get("TRACKER_KEY_ACCOUNT", os.environ.get("USER", ""))
    try:
        return subprocess.check_output(
            ["security", "find-generic-password", "-s", "tracker.ceph.com",
             "-a", acct, "-w"], text=True, stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def key(required=True):
    k = _lookup_key()
    if k is None and required:
        sys.exit("no API key: set REDMINE_API_KEY or add the keychain item")
    return k


def call(path, method="GET", body=None, auth=False):
    headers = {"Content-Type": "application/json"}
    k = key(required=auth or method != "GET")
    if k:
        headers["X-Redmine-API-Key"] = k
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:500]


def issue(n, include="journals,relations,allowed_statuses"):
    st, d = call(f"/issues/{n}.json?include={include}")
    if st != 200:
        sys.exit(f"#{n}: HTTP {st} {d}")
    return d["issue"]


def cfs(i):
    return {c["id"]: c.get("value") for c in i.get("custom_fields", [])
            if c.get("value") not in (None, "", [])}


def summary(i, notes=None):
    cf = cfs(i)
    out = [f"#{i['id']} [{i['project']['name']} / {i['tracker']['name']}] {i['subject']}",
           f"status={i['status']['name']}  assignee={i.get('assigned_to', {}).get('name', '-')}"
           f"  author={i['author']['name']}  created={i['created_on'][:10]}"
           f"  updated={i['updated_on'][:10]}  category={i.get('category', {}).get('name', '-')}"]
    if i.get("parent"):
        out.append(f"parent=#{i['parent']['id']}")
    for cid, name in CF.items():
        if cid in cf:
            out.append(f"{name}: {cf[cid]}")
    rel = [f"{r['relation_type']} #{r['issue_id']}->#{r['issue_to_id']}" for r in i.get("relations", [])]
    if rel:
        out.append("relations: " + ", ".join(rel))
    if "allowed_statuses" in i:
        out.append("allowed statuses: " + ", ".join(
            f"{s['name']}({s['id']})" for s in i["allowed_statuses"]))
    out += ["--- description ---", (i.get("description") or "").strip()]
    js = [j for j in i.get("journals", []) if (j.get("notes") or "").strip()]
    if notes is not None:
        js = js[-notes:] if notes else []
    for j in js:
        out.append(f"--- note {j['user']['name']} {j['created_on'][:16]} (journal {j['id']}) ---")
        out.append(j["notes"].strip())
    return "\n".join(out)


def cmd_show(a):
    i = issue(a.id)
    print(json.dumps(i, indent=1) if a.json else summary(i, a.notes))


def cmd_find(a):
    st, d = call(f"/issues.json?cf_21={a.pr}&status_id=*&limit=50")
    for i in (d or {}).get("issues", []):
        print(f"#{i['id']} | {i['project']['name']} | {i['tracker']['name']} | {i['status']['name']} | {i['subject']}")


def cmd_backports(a):
    i = issue(a.id, "relations")
    kids = [r["issue_to_id"] for r in i.get("relations", [])
            if r["relation_type"] == "copied_to" and r["issue_id"] == i["id"]]
    print(f"#{i['id']} {i['status']['name']} | Backport={cfs(i).get(2, '-')} | PR={cfs(i).get(21, '-')} | {i['subject']}")
    for k in kids:
        b = issue(k, "")
        c = cfs(b)
        print(f"  #{b['id']} | release={c.get(16, '-')} | {b['status']['name']} | "
              f"assignee={b.get('assigned_to', {}).get('name', '-')} | PR={c.get(21, '-')} | {b['subject']}")
    if not kids:
        print("  no copied_to backport issues yet")


def cmd_scrape(a):
    os.makedirs(f"{a.out}/raw", exist_ok=True)
    os.makedirs(f"{a.out}/txt", exist_ok=True)
    q = {"tracker_id": a.tracker, "status_id": a.status, "limit": 100, "sort": "id"}
    if a.project:
        q["project_id"] = a.project
    ids, off = [], 0
    while True:
        q["offset"] = off
        st, d = call("/issues.json?" + urllib.parse.urlencode(q))
        if st != 200:
            sys.exit(f"list: HTTP {st} {d}")
        ids += [i["id"] for i in d["issues"]]
        off += 100
        if off >= d["total_count"]:
            break

    def one(n):
        i = issue(n, "journals,relations")
        json.dump({"issue": i}, open(f"{a.out}/raw/{n}.json", "w"))
        open(f"{a.out}/txt/{n}.txt", "w").write(summary(i))
        c = cfs(i)
        return "\t".join(str(x) for x in (
            n, i["project"]["name"], i["status"]["name"],
            i.get("assigned_to", {}).get("name", "-"), i["updated_on"][:10],
            c.get(21, "-"), i["subject"]))

    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        rows = list(ex.map(one, ids))
    with open(f"{a.out}/index.tsv", "w") as f:
        f.write("id\tproject\tstatus\tassignee\tupdated\tpr\tsubject\n")
        f.write("\n".join(rows) + "\n")
    print(f"{len(ids)} issues -> {a.out}/txt/<id>.txt, {a.out}/index.tsv")


def status_id(s):
    if s.isdigit():
        return int(s)
    k = s.lower().replace(" ", "-").replace("'", "")
    if k not in STATUS:
        sys.exit(f"unknown status {s!r}; use an id or one of {', '.join(STATUS)}")
    return STATUS[k]


def cmd_update(a):
    before = issue(a.id, "allowed_statuses")
    body = {}
    if a.status:
        sid = status_id(a.status)
        allowed = {s["id"]: s["name"] for s in before.get("allowed_statuses", [])}
        if sid != before["status"]["id"] and sid not in allowed:
            sys.exit(f"#{a.id}: status {sid} not allowed from {before['status']['name']}; "
                     f"allowed: {', '.join(f'{v}({k})' for k, v in allowed.items())}")
        body["status_id"] = sid
    if a.note_file:
        body["notes"] = open(a.note_file).read().strip()
    fields = []
    if a.pr:
        fields.append({"id": 21, "value": "" if a.pr == "none" else a.pr})
    if a.backport:
        fields.append({"id": 2, "value": "" if a.backport == "none" else a.backport})
    if fields:
        body["custom_fields"] = fields
    if a.assign_me:
        st, me = call("/users/current.json", auth=True)
        body["assigned_to_id"] = me["user"]["id"]
    if not body:
        sys.exit("nothing to change")
    if a.dry_run:
        print(json.dumps({"issue": body}, indent=1))
        return
    st, d = call(f"/issues/{a.id}.json", "PUT", {"issue": body})
    print(f"#{a.id}: PUT {st}" + ("" if st in (200, 204) else f" {d}"))
    after = issue(a.id, "journals")
    ok = True
    if "status_id" in body and after["status"]["id"] != body["status_id"]:
        ok = False
        print(f"  STATUS NOT APPLIED: still {after['status']['name']}, wanted {body['status_id']}")
    c = cfs(after)
    for f in fields:
        got = c.get(f["id"], "")
        if str(got) != str(f["value"]):
            ok = False
            print(f"  {CF[f['id']]} NOT APPLIED: {got!r}, wanted {f['value']!r}")
    if a.note_file:
        last = [j for j in after.get("journals", []) if (j.get("notes") or "").strip()]
        if not last or last[-1]["notes"].strip() != body["notes"]:
            ok = False
            print("  NOTE NOT FOUND as the newest journal")
        else:
            print(f"  note = journal {last[-1]['id']}")
    print(f"  now: {after['status']['name']} | assignee={after.get('assigned_to', {}).get('name', '-')}"
          f" | Backport={c.get(2, '-')} | PR={c.get(21, '-')}" + ("" if ok else "  ** CHECK ABOVE **"))
    sys.exit(0 if ok else 1)


def cmd_relate(a):
    st, d = call(f"/issues/{a.a}/relations.json", "POST",
                 {"relation": {"issue_to_id": a.b, "relation_type": a.type}})
    print(f"#{a.a} {a.type} #{a.b}: HTTP {st}" + ("" if st in (200, 201) else f" {d}"))
    rel = [f"{r['relation_type']} #{r['issue_id']}->#{r['issue_to_id']}"
           for r in issue(a.a, "relations").get("relations", [])]
    print("  relations: " + ", ".join(rel))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)
    x = s.add_parser("show"); x.add_argument("id", type=int)
    x.add_argument("--notes", type=int, help="show only the last K notes (0 = none)")
    x.add_argument("--json", action="store_true"); x.set_defaults(f=cmd_show)
    x = s.add_parser("find"); x.add_argument("--pr", type=int, required=True); x.set_defaults(f=cmd_find)
    x = s.add_parser("backports"); x.add_argument("id", type=int); x.set_defaults(f=cmd_backports)
    x = s.add_parser("scrape"); x.add_argument("--out", required=True)
    x.add_argument("--tracker", default="6", help="tracker id; 6 = Documentation, 1 = Bug")
    x.add_argument("--status", default="open", help="open, closed, * or a status id")
    x.add_argument("--project", help="project id or identifier, e.g. 1 or cephfs")
    x.set_defaults(f=cmd_scrape)
    x = s.add_parser("update"); x.add_argument("id", type=int)
    x.add_argument("--status"); x.add_argument("--note-file")
    x.add_argument("--pr", help="Pull request ID, or none to clear")
    x.add_argument("--backport", help="newest first, no spaces, or none to clear")
    x.add_argument("--assign-me", action="store_true")
    x.add_argument("--dry-run", action="store_true"); x.set_defaults(f=cmd_update)
    x = s.add_parser("relate"); x.add_argument("a", type=int); x.add_argument("b", type=int)
    x.add_argument("--type", default="relates",
                   choices=["relates", "duplicates", "duplicated", "blocks", "blocked",
                            "precedes", "follows", "copied_to", "copied_from"])
    x.set_defaults(f=cmd_relate)
    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
