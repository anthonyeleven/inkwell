#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Anthony D'Atri
"""Backports of a ceph/ceph main PR: check, prep, open.

  backport.py check PR|COMMIT[..COMMIT] BRANCH...
      Simulate the cherry-pick onto each branch (no worktree, nothing pushed).
      Reports conflicts, compares line counts with the original, and checks
      that every :ref:, :confval: and :doc: target in added doc lines exists.
  backport.py prep PR [--releases umbrella,tentacle] [--workdir DIR]
      PR must be merged and its parent tracker must have backport issues.
      Per backport issue: worktree on upstream/<release>, branch
      wip-<issue>-<release>, cherry-pick -x, PR body file. Pushes nothing.
  backport.py open ISSUE [--workdir DIR]
      Push the prepped branch, open the PR ready with the release milestone,
      then set the backport issue Fix Under Review + PR ID + assigned to you.

Env: CEPH_GIT (default ~/git/ceph; remotes origin = your fork, upstream =
ceph/ceph), CEPH_GIT_NAME / CEPH_GIT_EMAIL (default: your GitHub profile name
and <login>@users.noreply.github.com), BACKPORT_WORKDIR (default ~/ceph-backports).
"""
import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tracker  # noqa: E402

G = os.path.expanduser(os.environ.get("CEPH_GIT", "~/git/ceph"))
ENV = dict(os.environ, GH_HOST="github.com")
TEMPLATE_MARK = "<!--"


def run(*cmd, cwd=None, check=True):
    r = subprocess.run(cmd, cwd=cwd or G, env=ENV, text=True, capture_output=True)
    if check and r.returncode:
        sys.exit(f"$ {' '.join(cmd)}\n{r.stderr.strip()}")
    return r


def git(*a, cwd=None, check=True):
    return run("git", *a, cwd=cwd, check=check).stdout.strip()


def gh_json(*a):
    return json.loads(run("gh", *a).stdout)


def identity():
    """GitHub login, plus the name and email for commits you make: your public
    GitHub name and noreply address unless CEPH_GIT_NAME / CEPH_GIT_EMAIL say otherwise."""
    u = gh_json("api", "user")
    name = os.environ.get("CEPH_GIT_NAME") or u.get("name") or git("config", "user.name", check=False)
    email = os.environ.get("CEPH_GIT_EMAIL") or f"{u['login']}@users.noreply.github.com"
    return u["login"], name, email


def pr_commits(pr):
    d = gh_json("pr", "view", str(pr), "-R", "ceph/ceph", "--json",
                "commits,state,mergedAt,title,body,mergeCommit,number")
    git("fetch", "-q", "upstream", f"pull/{pr}/head")
    return d, [c["oid"] for c in d["commits"]]


def numstat(a, b, cwd=None):
    out = git("diff", "--numstat", a, b, cwd=cwd)
    return sorted(l.split("\t") for l in out.splitlines() if l)


def fmt_numstat(rows):
    return ", ".join(f"{p} +{a}/-{d}" for a, d, p in rows)


def doc_targets(base, tip):
    """(kind, target, file) for :ref:/:confval:/:doc: in lines the pick adds."""
    out, cur = [], None
    for line in git("diff", "-U0", base, tip, "--", "doc").splitlines():
        if line.startswith("+++ "):
            cur = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("+") and cur:
            for kind, body in re.findall(r":(ref|confval|doc):`([^`]+)`", line):
                m = re.search(r"<([^>]+)>$", body)
                out.append((kind, (m.group(1) if m else body).strip(), cur))
    return sorted(set(out))


def target_ok(kind, t, f, tip):
    def grep(opts, *paths):
        return subprocess.run(["git", "grep", "-q", *opts, tip, "--", *paths], cwd=G,
                              capture_output=True).returncode == 0
    if kind == "ref":
        return grep(["-e", f"^\\.\\. _{re.escape(t)}:"], "doc")
    if kind == "confval":
        if grep(["-E", "-e", f"^ *- name: {re.escape(t)}$"], "src/common/options"):
            return True
        return None if grep(["-F", "-e", t], "src/pybind/mgr", "doc") else False
    path = t[1:] if t.startswith("/") else os.path.normpath(os.path.join(os.path.dirname(f)[4:], t))
    r = subprocess.run(["git", "cat-file", "-e", f"{tip}:doc/{path}.rst"], cwd=G, capture_output=True)
    return r.returncode == 0


def simulate(commits, branch):
    """Chain merge-tree picks onto upstream/<branch>. Returns (base, tip|None, msg)."""
    base = tip = git("rev-parse", f"upstream/{branch}")
    for c in commits:
        r = run("git", "merge-tree", "--write-tree", "--name-only",
                "--merge-base", f"{c}^", tip, c, check=False)
        if r.returncode:
            files = r.stdout.split("\n\n")[0].splitlines()[1:]
            return base, None, f"CONFLICT at {git('log', '-1', '--format=%h %s', c)}: {', '.join(files)}"
        tip = git("commit-tree", r.stdout.splitlines()[0], "-p", tip, "-m", f"bp-check {c}")
    return base, tip, "clean"


def cmd_check(a):
    src = a.source
    if re.fullmatch(r"\d{1,6}", src):
        d, commits = pr_commits(src)
        print(f"#{d['number']} {d['title']} | {d['state']} | {len(commits)} commit(s)")
    else:
        git("fetch", "-q", "upstream")
        commits = (git("rev-list", "--reverse", src).split() if ".." in src
                   else [git("rev-parse", src)])
    git("fetch", "-q", "upstream", *a.branches)
    orig = numstat(f"{commits[0]}^", commits[-1])
    print(f"original: {fmt_numstat(orig)}")
    bad = False
    for b in a.branches:
        base, tip, msg = simulate(commits, b)
        if not tip:
            print(f"{b}: {msg}")
            bad = True
            continue
        got = numstat(base, tip)
        same = got == orig
        print(f"{b}: {msg}, " + ("same line counts" if same else f"LINE COUNTS DIFFER: {fmt_numstat(got)}"))
        bad |= not same
        for kind, t, f in doc_targets(base, tip):
            ok = target_ok(kind, t, f, tip)
            if ok is not True:
                print(f"   {'MISSING' if ok is False else 'check'} :{kind}:`{t}` ({f})")
                bad |= ok is False
    sys.exit(1 if bad else 0)


def summary_from_body(body):
    """Main PR prose without Fixes: lines or paragraphs that @mention reviewers."""
    prose = body.split(TEMPLATE_MARK, 1)[0]
    prose = "\n".join(l for l in prose.splitlines() if not l.startswith("Fixes:"))
    paras = [p for p in re.split(r"\n\s*\n", prose)
             if p.strip() and not re.search(r"(^|\s)@[A-Za-z0-9-]+", p)]
    return "\n\n".join(p.strip() for p in paras)


def picking(wt):
    return run("git", "rev-parse", "-q", "--verify", "CHERRY_PICK_HEAD", cwd=wt, check=False).returncode == 0


def tail_from_body(body):
    return TEMPLATE_MARK + body.split(TEMPLATE_MARK, 1)[1] if TEMPLATE_MARK in body else ""


def parent_issue(d):
    found = [l.split("/issues/")[1].split()[0] for l in d["body"].splitlines()
             if l.startswith("Fixes:") and "/issues/" in l]
    if found:
        return int(found[0])
    st, r = tracker.call(f"/issues.json?cf_21={d['number']}&status_id=*&project_id=1")
    ids = [i["id"] for i in (r or {}).get("issues", []) if i["tracker"]["id"] != 9]
    if not ids:
        sys.exit(f"#{d['number']}: no Fixes: line and no tracker with this PR ID")
    return ids[0]


def cmd_prep(a):
    d, commits = pr_commits(a.pr)
    if d["state"] != "MERGED" and not a.unmerged:
        sys.exit(f"#{a.pr} is {d['state']}; backports open after the merge (--unmerged to stage anyway)")
    parent = parent_issue(d)
    p = tracker.issue(parent, "relations")
    kids = [r["issue_to_id"] for r in p.get("relations", [])
            if r["relation_type"] == "copied_to" and r["issue_id"] == parent]
    want = a.releases.split(",") if a.releases else None
    login, name, email = identity()
    os.makedirs(a.workdir, exist_ok=True)
    orig = numstat(f"{commits[0]}^", commits[-1])
    have, bad = set(), False
    for k in kids:
        bi = tracker.issue(k, "")
        rel = tracker.cfs(bi).get(16)
        if not rel or (want and rel not in want):
            continue
        have.add(rel)
        br, wt = f"wip-{k}-{rel}", os.path.join(a.workdir, f"bp-{k}-{rel}")
        git("fetch", "-q", "upstream", rel)
        if not os.path.exists(wt):
            git("worktree", "add", "-q", "--no-track", "-b", br, wt, f"upstream/{rel}")
            run("git", "-c", f"user.name={name}", "-c", f"user.email={email}",
                "cherry-pick", "-x", *commits, cwd=wt, check=False)
        if picking(wt):
            print(f"{rel}: CONFLICT in {wt}\n{git('status', '--short', cwd=wt)}\n"
                  "   resolve, add a Conflicts: block after the (cherry picked from ...) line,"
                  f" then git -c user.name=\"{name}\" -c user.email={email} cherry-pick --continue;"
                  " rerun prep for the body")
            bad = True
            continue
        got = numstat(f"upstream/{rel}", "HEAD", cwd=wt)
        note = (f"Clean cherry-pick of {len(commits)} commit{'s' if len(commits) > 1 else ''}, "
                f"with the same line changes as on main." if got == orig else
                f"LINE COUNTS DIFFER from main: {fmt_numstat(got)} vs {fmt_numstat(orig)}. Explain here.")
        body = (f"backport tracker: https://tracker.ceph.com/issues/{k}\n\n---\n\n"
                f"backport of https://github.com/ceph/ceph/pull/{a.pr}\n"
                f"parent tracker: https://tracker.ceph.com/issues/{parent}\n\n"
                f"{summary_from_body(d['body'])}\n\n{note}\n\n{tail_from_body(d['body'])}")
        open(os.path.join(a.workdir, f"pr-bp-{k}-body.md"), "w").write(body)
        json.dump({"issue": k, "release": rel, "branch": br, "worktree": wt, "main_pr": a.pr,
                   "title": f"{rel}: {d['title']}", "login": login, "email": email},
                  open(os.path.join(a.workdir, f"bp-{k}.json"), "w"))
        print(f"{rel}: {br} in {wt} | {'clean' if got == orig else 'LINE COUNTS DIFFER'} | "
              f"body {a.workdir}/pr-bp-{k}-body.md")
    for rel in sorted(set(want or []) - have):
        print(f"{rel}: no backport issue on #{parent} yet (the Upkeep Bot makes them at Pending Backport)")
    sys.exit(1 if bad else 0)


def cmd_open(a):
    m = json.load(open(os.path.join(a.workdir, f"bp-{a.issue}.json")))
    wt = m["worktree"]
    if git("status", "--porcelain", cwd=wt) or picking(wt):
        sys.exit(f"{wt} is not clean")
    leaks = [l for l in git("log", "--format=%ae %ce", f"upstream/{m['release']}..HEAD", cwd=wt).splitlines()
             if m["email"] not in l.split()[1:]]
    if leaks:
        sys.exit(f"committer is not {m['email']} on: {leaks}")
    run("git", "push", "-q", "origin", m["branch"], cwd=wt)
    url = run("gh", "pr", "create", "-R", "ceph/ceph", "--base", m["release"],
              "--head", f"{m['login']}:{m['branch']}", "--milestone", m["release"],
              "--title", m["title"], "--body-file",
              os.path.join(a.workdir, f"pr-bp-{a.issue}-body.md")).stdout.strip()
    n = url.rstrip("/").split("/")[-1]
    print(f"{m['release']}: {url}")
    sys.argv = ["tracker.py", "update", str(a.issue), "--status", "13", "--pr", n, "--assign-me"]
    tracker.main()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)
    wd = os.environ.get("BACKPORT_WORKDIR", os.path.expanduser("~/ceph-backports"))
    x = s.add_parser("check"); x.add_argument("source"); x.add_argument("branches", nargs="+")
    x.set_defaults(f=cmd_check)
    x = s.add_parser("prep"); x.add_argument("pr", type=int); x.add_argument("--releases")
    x.add_argument("--workdir", default=wd); x.add_argument("--unmerged", action="store_true")
    x.set_defaults(f=cmd_prep)
    x = s.add_parser("open"); x.add_argument("issue", type=int); x.add_argument("--workdir", default=wd)
    x.set_defaults(f=cmd_open)
    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
