#!/usr/bin/env python3
"""SkillAudit single-script baseline.

The same three checks as the layered tool, written the "obvious" way: one file,
no layers, no plug-in interface, checks hard-coded in one loop. It must produce
byte-identical findings.csv and summary.csv to the layered version
(tests/test_baseline_parity.py), so the Q1 comparison is about structure, not
behaviour.

Do not refactor this file to share code with src/skillaudit: the duplication is
the point of the baseline.

    python baseline/skillaudit_single.py --data agent_skills_sample.db --out DIR
"""

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

STALE_DAYS = 180
ACTIVE_DAYS = 90
COPY_SIMILARITY = 0.5
EXEC_EXTS = {".sh", ".bash", ".zsh", ".fish", ".py", ".js", ".mjs", ".cjs", ".ts",
             ".rb", ".pl", ".php", ".lua", ".ps1", ".psm1", ".bat", ".cmd",
             ".exe", ".bin", ".jar", ".appimage"}
RISKY = {
    "curl": r"\bcurl\s",
    "wget": r"\bwget\s",
    "pipe_to_shell": r"\|\s*(?:sudo\s+)?(?:ba|z)?sh\b",
    "eval": r"\beval\s*[\(\s\"'`$]",
    "exec": r"\bexec\s*\(",
    "pip_install": r"\bpip3?\s+install\b",
    "npm_install": r"\bnpm\s+(?:install|i)\b|\bnpx\s",
    "sudo": r"\bsudo\s",
    "rm_rf": r"\brm\s+-(?:[a-zA-Z]*r[a-zA-Z]*f|[a-zA-Z]*f[a-zA-Z]*r)\b",
    "chmod_exec": r"\bchmod\s+(?:[ugoa]*\+x|0?7[0-7]{2})\b",
    "base64_decode": r"\bbase64\s+(?:-d|--decode|-D)\b",
    "powershell_download":
        r"(?i)\binvoke-webrequest\b|\biwr\s|\bdownloadstring\b|\binvoke-expression\b|\biex\s",
}


def to_time(v):
    if v is None or v == "":
        return None
    s = str(v).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def flag(v):
    return v is not None and str(v).strip().lower() in ("1", "true")


def folder_of(path):
    p = (path or "").rstrip("/")
    head, _, tail = p.rpartition("/")
    return head if tail.lower() == "skill.md" else p


def read_table(db, table):
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    cur = con.execute(f'SELECT * FROM "{table}"')
    cols = [d[0] for d in cur.description]
    while True:
        batch = cur.fetchmany(50000)
        if not batch:
            break
        for r in batch:
            yield dict(zip(cols, r))


def words(t):
    return set(re.findall(r"[a-z0-9_]+", t.lower()))


def features(t):
    found = {k for k, pat in RISKY.items() if re.search(pat, t)}
    found |= {"url_host:" + h.lower().rstrip(".") for h in re.findall(r"https?://([A-Za-z0-9.-]+)", t)}
    return found


def ev(d):
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--as-of")
    args = ap.parse_args()
    db, out_dir = Path(args.data), Path(args.out)
    if db.is_dir():
        db = next(f for f in sorted(db.iterdir()) if f.suffix in (".db", ".sqlite", ".sqlite3"))
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    arts = list(read_table(db, "artifacts"))
    pushed = {r["full_name"]: to_time(r.get("pushed_at"))
              for r in read_table(db, "repos") if r.get("full_name")}
    sibs = defaultdict(list)
    for r in read_table(db, "artifact_siblings"):
        if r.get("repo_full_name") and r.get("artifact_path") is not None and r.get("entry_name"):
            sibs[(r["repo_full_name"], folder_of(str(r["artifact_path"])))].append(
                (str(r["entry_name"]), str(r.get("entry_type") or "file")))

    # de-duplicate occurrences, collect content and groups
    skills, seen = [], set()
    latest = None
    for r in arts:
        if not r.get("repo_full_name") or not r.get("path") or not r.get("file_sha"):
            continue
        sid = f'{r["repo_full_name"]}:{r["path"]}'
        if sid in seen:
            continue
        seen.add(sid)
        d = to_time(r.get("discovered_at"))
        if d and (latest is None or d > latest):
            latest = d
        r = dict(r)
        r["sid"] = sid
        r["file_sha"] = str(r["file_sha"])
        nm = r.get("name")
        nm = " ".join(str(nm).strip().lower().split()) if nm is not None else None
        r["nname"] = nm or None
        r["hist"] = flag(r.get("history_fetched"))
        r["first"] = to_time(r.get("first_commit_at")) if r["hist"] else None
        r["last"] = to_time(r.get("last_commit_at")) if r["hist"] else None
        skills.append(r)
    skills.sort(key=lambda r: r["sid"])
    # front matter is only parsed on the representative; copies share its name
    sha_name = {r["file_sha"]: r["nname"] for r in skills if r["nname"]}
    for r in skills:
        if r["nname"] is None:
            r["nname"] = sha_name.get(r["file_sha"])
    as_of = to_time(args.as_of) if args.as_of else latest

    content, by_sha, by_name = {}, defaultdict(list), defaultdict(list)
    for r in skills:
        by_sha[r["file_sha"]].append(r)
        if r["nname"]:
            by_name[r["nname"]].append(r)
        if r.get("content") is not None and r["file_sha"] not in content:
            content[r["file_sha"]] = r["content"]

    def fkey(r):
        return (1, "", r["sid"]) if r["first"] is None else (0, r["first"].isoformat(), r["sid"])

    origin = {}
    for nm in sorted(by_name):
        occ = by_name[nm]
        if len(occ) < 2:
            continue
        shas = defaultdict(list)
        for r in occ:
            shas[r["file_sha"]].append(r)
        osha = min(shas, key=lambda s: (min(fkey(r) for r in shas[s]), -len(shas[s]), s))
        origin[nm] = (osha, min(shas[osha], key=fkey)["sid"])

    rows = []  # (check, sid, sha, flagged, reason, evidence)
    for r in skills:
        sid, sha = r["sid"], r["file_sha"]
        # --- staleness
        p = pushed.get(r["repo_full_name"])
        if r["hist"] and r["last"] is not None and p is not None:
            sa, ra = (as_of - r["last"]).days, (as_of - p).days
            stale, active = sa >= STALE_DAYS, ra <= ACTIVE_DAYS
            reason = "stale" if stale and active else ("repo_inactive" if stale else "recently_updated")
            cc = r.get("commit_count")
            rows.append(("staleness", sid, sha, stale and active, reason,
                         {"skill_age_days": sa, "repo_push_age_days": ra,
                          "commit_count": int(cc) if cc not in (None, "") else None}))
        # --- risky copy
        nm = r["nname"]
        if nm and nm in origin and sid != origin[nm][1]:
            osha, oid = origin[nm]
            if sha == osha:
                rows.append(("risky_copy", sid, sha, False, "exact_copy",
                             {"original_skill_id": oid, "added": []}))
            elif content.get(sha) is not None and content.get(osha) is not None:
                a, b = words(content[sha]), words(content[osha])
                sim = 1.0 if not a and not b else len(a & b) / len(a | b)
                if sim >= COPY_SIMILARITY:
                    added = sorted(features(content[sha]) - features(content[osha]))
                    rows.append(("risky_copy", sid, sha, bool(added),
                                 "adds_risky_features" if added else "modified_no_new_risk",
                                 {"original_skill_id": oid, "similarity": round(sim, 4),
                                  "added": added}))
        # --- bundled executables
        if flag(r.get("dedup_primary")) and flag(r.get("composition_fetched")):
            files = sibs.get((r["repo_full_name"], folder_of(str(r["path"]))), [])
            exe = []
            for name, typ in files:
                base = name.rsplit("/", 1)[-1]
                ext = "" if "." not in base.lstrip(".") else "." + base.rsplit(".", 1)[-1].lower()
                if typ == "file" and ext in EXEC_EXTS:
                    exe.append(name)
            exe.sort()
            exts = Counter(f.rsplit(".", 1)[-1].lower() for f in exe)
            rows.append(("bundled_executables", sid, sha, bool(exe),
                         "has_executables" if exe else "no_executables",
                         {"executable_count": len(exe), "executables": exe[:20],
                          "extensions": dict(sorted(exts.items())),
                          "copy_count": len(by_sha[sha])}))

    rows.sort(key=lambda x: (x[0], x[1], x[4]))
    with open(out_dir / "findings.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["check", "skill_id", "file_sha", "flagged", "reason", "evidence"])
        for c, sid, sha, fl, reason, e in rows:
            w.writerow([c, sid, sha, int(fl), reason, ev(e)])

    checks = ["bundled_executables", "risky_copy", "staleness"]
    n, k, reasons = Counter(), Counter(), defaultdict(Counter)
    for c, _, _, fl, reason, _ in rows:
        n[c] += 1
        k[c] += int(fl)
        reasons[c][reason] += 1
    with open(out_dir / "summary.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["check", "evaluated", "flagged", "pct_flagged", "reasons"])
        for c in checks:
            w.writerow([c, n[c], k[c], f"{100.0 * k[c] / n[c]:.2f}" if n[c] else "",
                        json.dumps(dict(sorted(reasons[c].items())), separators=(",", ":"))])

    hashes = {name: hashlib.sha256((out_dir / name).read_bytes()).hexdigest()
              for name in ("findings.csv", "summary.csv")}
    (out_dir / "manifest.json").write_text(json.dumps({
        "implementation": "baseline", "as_of": as_of.isoformat(), "outputs": hashes,
        "timings_seconds": {"total": round(time.perf_counter() - t0, 3)},
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(rows)} findings -> {out_dir}")


if __name__ == "__main__":
    main()
