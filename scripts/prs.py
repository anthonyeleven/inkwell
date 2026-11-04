#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Anthony D'Atri
"""ceph/ceph pull requests: status, overlap scan, and the bot commands.

  prs.py status N...                 draft, labels, failing checks, config and audit bot state
  prs.py overlap PATH... [--grep RE] [--refresh]
                                     open PRs that touch PATH (a file or a directory prefix);
                                     --grep keeps PRs whose patch to PATH matches RE
  prs.py config-ok N                 post "/config check ok", then re-run the failed config check
  prs.py audit N --retest|--override post "/audit retest" or "/audit override"
  prs.py jenkins N "jenkins test docs"
                                     post one Jenkins/RTD trigger phrase

Everything that posts a comment is public and carries your name: run it only
after the human has said go for that PR.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

R = "ceph/ceph"
ENV = dict(os.environ, GH_HOST="github.com")
CACHE = os.path.expanduser("~/.cache/inkwell/open-prs.json")
CONFIG_WF = "Check Ceph config changes"
# The trigger phrases listed in ceph's PR template, plus the RTD retrigger workflow's.
JENKINS = {
    "jenkins test classic perf", "jenkins test crimson perf", "jenkins test signed",
    "jenkins test make check", "jenkins test make check arm64", "jenkins test submodules",
    "jenkins test dashboard", "jenkins test dashboard cephadm", "jenkins test api",
    "jenkins test docs", "jenkins rebuild docs", "jenkins retrigger docs",
    "jenkins test ceph-volume all", "jenkins test windows", "jenkins test rook e2e",
}


def gh(*a, check=True):
    r = subprocess.run(["gh", *a], env=ENV, text=True, capture_output=True)
    if check and r.returncode:
        sys.exit(f"$ gh {' '.join(a)}\n{r.stderr.strip()}")
    return r.stdout


def ghj(*a):
    return json.loads(gh(*a) or "null")


def pages(path):
    return [x for page in ghj("api", path, "--paginate", "--slurp") for x in page]


def comments(n):
    return [{"user": c["user"]["login"], "at": c["created_at"], "body": c["body"]}
            for c in pages(f"repos/{R}/issues/{n}/comments?per_page=100")]


def comment(n, body):
    url = gh("api", f"repos/{R}/issues/{n}/comments", "-f", f"body={body}", "--jq", ".html_url").strip()
    print(f"#{n}: posted {body!r} {url}")


def cmd_status(a):
    for n in a.n:
        d = ghj("pr", "view", str(n), "-R", R, "--json",
                "number,title,state,isDraft,baseRefName,headRefName,headRefOid,milestone,"
                "labels,reviewDecision,mergeable,statusCheckRollup,author")
        labels = sorted(l["name"] for l in d["labels"])
        print(f"#{n} {d['title']}\n  {d['state']}{' DRAFT' if d['isDraft'] else ''} | "
              f"{d['author']['login']}:{d['headRefName']} -> {d['baseRefName']} | "
              f"milestone={(d['milestone'] or {}).get('title', '-')} | review={d['reviewDecision'] or '-'} | "
              f"mergeable={d['mergeable']}\n  labels: {', '.join(labels) or '-'}")
        latest = {}
        for c in d["statusCheckRollup"]:
            name = c.get("name") or c.get("context")
            state = c.get("conclusion") or c.get("state") or c.get("status")
            wf = c.get("workflowName") or ""
            key = f"{name} ({wf})" if wf and wf != name else name
            latest.setdefault(key, []).append((c.get("completedAt") or c.get("startedAt") or "", state))
        rows = {k: sorted(v)[-1][1] for k, v in latest.items()}
        bad = {k: v for k, v in rows.items() if v not in ("SUCCESS", "NEUTRAL", "SKIPPED")}
        print(f"  checks: {len(rows) - len(bad)} ok" + "".join(f"\n    {v}: {k}" for k, v in sorted(bad.items())))
        cs = comments(n)
        cfg = [c for c in cs if "### Config Diff Tool Output" in c["body"]]
        ok = [c for c in cs if "/config check ok" in c["body"] and "### Config Diff Tool Output" not in c["body"]]
        if cfg:
            print(f"  config diff: posted {cfg[-1]['at'][:16]}Z; /config check ok: "
                  + (f"{ok[-1]['user']} {ok[-1]['at'][:16]}Z" if ok else "NOT POSTED"))
        if d["baseRefName"] != "main":
            audit = [c for c in cs if c["user"] == "github-actions[bot]" and
                     re.search(r"Audit|audit", c["body"])]
            for c in audit[-2:]:
                first = c["body"].strip().splitlines()[0][:110]
                print(f"  audit bot {c['at'][:16]}Z: {first}")
        print()


def open_prs(refresh):
    if not refresh and os.path.exists(CACHE) and time.time() - os.path.getmtime(CACHE) < 3600:
        return json.load(open(CACHE))
    print("listing open PRs with their files (about 90 s)...", file=sys.stderr)
    d = ghj("pr", "list", "-R", R, "--state", "open", "--limit", "5000", "--json",
            "number,title,author,updatedAt,isDraft,files")
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(d, open(CACHE, "w"))
    return d


def cmd_overlap(a):
    hits = []
    for p in open_prs(a.refresh):
        files = [f["path"] for f in p.get("files") or []]
        m = [f for f in files if any(f == x or f.startswith(x.rstrip("/") + "/") for x in a.path)]
        if m:
            hits.append((p, m))
    for p, m in sorted(hits, key=lambda h: h[0]["number"]):
        if a.grep:
            patches = pages(f"repos/{R}/pulls/{p['number']}/files?per_page=100")
            if not any(re.search(a.grep, x.get("patch") or "", re.I) for x in patches if x["filename"] in m):
                continue
        print(f"#{p['number']} | {p['author']['login']} | {p['updatedAt'][:10]}"
              f"{' | draft' if p['isDraft'] else ''} | {p['title']} | {', '.join(m)}")


def cmd_config_ok(a):
    if not any("### Config Diff Tool Output" in c["body"] for c in comments(a.n)):
        sys.exit(f"#{a.n}: no Config Diff Tool Output comment; nothing to acknowledge")
    comment(a.n, "/config check ok")
    sha = ghj("pr", "view", str(a.n), "-R", R, "--json", "headRefOid")["headRefOid"]
    runs = ghj("api", f"repos/{R}/actions/runs?head_sha={sha}&per_page=50",
               "--jq", f"[.workflow_runs[]|select(.name==\"{CONFIG_WF}\")|{{id, conclusion, status}}]")
    failed = [r for r in runs if r["conclusion"] == "failure"]
    if not failed:
        print(f"  no failed {CONFIG_WF!r} run on {sha[:11]} to re-run: {runs}")
        return
    gh("run", "rerun", str(failed[0]["id"]), "-R", R, "--failed")
    print(f"  re-running https://github.com/{R}/actions/runs/{failed[0]['id']}")


def cmd_audit(a):
    base = ghj("pr", "view", str(a.n), "-R", R, "--json", "baseRefName")["baseRefName"]
    if base == "main":
        sys.exit(f"#{a.n} targets main; the Backport Audit only runs on release branches")
    comment(a.n, "/audit override" if a.override else "/audit retest")


def cmd_jenkins(a):
    if a.phrase not in JENKINS:
        sys.exit("not a known trigger phrase; one of:\n  " + "\n  ".join(sorted(JENKINS)))
    comment(a.n, a.phrase)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)
    x = s.add_parser("status"); x.add_argument("n", type=int, nargs="+"); x.set_defaults(f=cmd_status)
    x = s.add_parser("overlap"); x.add_argument("path", nargs="+"); x.add_argument("--grep")
    x.add_argument("--refresh", action="store_true"); x.set_defaults(f=cmd_overlap)
    x = s.add_parser("config-ok"); x.add_argument("n", type=int); x.set_defaults(f=cmd_config_ok)
    x = s.add_parser("audit"); x.add_argument("n", type=int)
    g = x.add_mutually_exclusive_group(required=True)
    g.add_argument("--retest", action="store_true"); g.add_argument("--override", action="store_true")
    x.set_defaults(f=cmd_audit)
    x = s.add_parser("jenkins"); x.add_argument("n", type=int); x.add_argument("phrase")
    x.set_defaults(f=cmd_jenkins)
    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
