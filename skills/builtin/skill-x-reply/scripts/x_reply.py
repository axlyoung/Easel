#!/usr/bin/env python3
"""x_reply.py — X 每日回复任务（养号期最重要的动作）.

新号在 X 上的原创帖几乎没人看，前 30 天涨粉主要靠**在同领域账号下面写有信息量的回复**。
本脚本把这件事做成每天一张任务单，并把容易触发限流的行为挡在发出去之前：

- 目标名单：维护 10–30 个要长期互动的账号（同领域、5k–100k 粉为主）
- 今日任务：按账号阶段给出今天回复几条、去回谁（最久没回的优先，今天回过的跳过）、分几个时段
- 发前检查：去AI自查（X 规则）+ 和近期回复的相似度（防重复回复）+ 同一个人今天回了几次 + 节奏闸门
- 预填链接：生成官方 reply intent 链接，人点开自己发
- 登记：写入 publish-log（type=reply），更新该目标的最后回复时间

子命令:
  targets add    --handle @x [--tier core|normal] [--topic "agents"] [--note "..."]
  targets list
  targets remove --handle @x
  today          [--json]                                   今日任务单
  check          --file reply.md [--to @x] [--json]         发前检查；exit 0 通过 / 1 需改稿 / 3 先等等 / 4 不能发
  link           --url <推文链接> --file reply.md [--open]  生成回复链接
  record         --url <推文链接> --to @x --file reply.md   发完登记
  selftest

数据：outputs/_analytics/x-targets.json；回复记录复用 outputs/_analytics/publish-log.json。
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import urllib.parse
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve()
PROJECT_ROOT = Path(os.environ.get("EASEL_ROOT") or HERE.parents[4])
SHARED = HERE.parents[3] / "shared" / "scripts"
sys.path.insert(0, str(SHARED))

import cadence_gate as cg  # noqa: E402
import deai_check as dc  # noqa: E402

TARGETS_FILE = PROJECT_ROOT / "outputs" / "_analytics" / "x-targets.json"
STATUS_RE = re.compile(r"(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})/status/(\d+)")
SIMILAR_FAIL = 0.6          # 和近期任意一条回复相似度 ≥ 0.6 → 判重复
RECENT_N = 50
NEVER = datetime(1970, 1, 1, tzinfo=timezone.utc)
# 每天建议回复量（下限, 上限）；上限不超过 cadence_gate 的 engage_day
SUGGEST = {"S0": (5, 10), "S1": (10, 20), "S2": (15, 30), "S3": (15, 30)}
# 同一个人一天最多回几次
PER_TARGET_DAY = {"S0": 1, "S1": 1, "S2": 2, "S3": 2}
# 分散到这几个时段（本机时间），避免一口气回完像机器
WINDOWS = ["08:30–10:00", "12:00–13:30", "20:00–22:30"]


def _paths():
    root = Path(os.environ.get("EASEL_ROOT") or PROJECT_ROOT)
    a = root / "outputs" / "_analytics"
    return a / "x-targets.json", a / "intl-accounts.json", a / "publish-log.json"


def _norm(h: str) -> str:
    h = h.strip()
    return "@" + h.lstrip("@").lower()


def load_targets() -> dict:
    tf, _, _ = _paths()
    return cg._load_json(tf, {"targets": {}})


def save_targets(d: dict) -> None:
    tf, _, _ = _paths()
    cg._atomic_write(tf, d)


def _ctx(now: datetime):
    _, af, lf = _paths()
    accounts = cg.load_accounts(af)
    entries = cg.load_entries(lf)
    st, age, notes = cg.stage_for("x", accounts.get("x"), now)
    return st, age, notes, entries


def _replies(entries: list[dict]) -> list[tuple[datetime, dict]]:
    return [(dt, e) for dt, e in cg._platform_entries(entries, "x") if cg._kind(e) == "reply"]


def _target_of(e: dict) -> str:
    for t in e.get("tags") or []:
        if t.lower().startswith("target:"):
            return t.split(":", 1)[1].lower()
    return ""


def _stage_key(st: dict) -> str:
    return st["name"].split()[0]


# --------------------------------------------------------------------------- #
# today
# --------------------------------------------------------------------------- #
def build_today(now: datetime) -> dict:
    st, age, notes, entries = _ctx(now)
    key = _stage_key(st)
    lo, hi = SUGGEST.get(key, (5, 10))
    hi = min(hi, st["engage_day"])
    reps = _replies(entries)
    done_today = [e for dt, e in reps if dt.astimezone(now.tzinfo).date() == now.date()]
    per_target_today: dict[str, int] = {}
    for e in done_today:
        per_target_today[_target_of(e)] = per_target_today.get(_target_of(e), 0) + 1
    last_at: dict[str, datetime] = {}
    for dt, e in reps:
        last_at[_target_of(e)] = dt

    targets = load_targets()["targets"]
    cap = PER_TARGET_DAY.get(key, 1)
    pool = []
    for h, t in targets.items():
        if per_target_today.get(h, 0) >= cap:
            continue
        pool.append((0 if t.get("tier") == "core" else 1, last_at.get(h, NEVER), h, t))
    pool.sort(key=lambda x: (x[1], x[0]))          # 最久没回的优先，同等情况下 core 优先
    remaining = max(0, hi - len(done_today))
    visit = [{"handle": h, "tier": t.get("tier", "normal"), "topic": t.get("topic", ""),
              "profile": f"https://x.com/{h[1:]}",
              "last_replied": last_at[h].isoformat(timespec="minutes") if h in last_at else "从未"}
             for _, _, h, t in pool[: min(len(pool), remaining + 3)]]   # 多给 3 个备选：有的人今天没发帖
    per_window = [remaining // len(WINDOWS) + (1 if i < remaining % len(WINDOWS) else 0) for i in range(len(WINDOWS))]
    tips = []
    if len(targets) < 10:
        tips.append(f"目标名单只有 {len(targets)} 个，建议补到 10–30 个（targets add）")
    if len(done_today) < lo and now.hour >= 20:
        tips.append(f"今天才 {len(done_today)} 条，低于建议下限 {lo}；宁少勿水，别为了凑数发空回复")
    return {"stage": st["name"], "account_age_days": age, "suggest": f"{lo}–{hi} 条",
            "done_today": len(done_today), "remaining_max": remaining,
            "windows": [{"time": w, "replies": n} for w, n in zip(WINDOWS, per_window) if n],
            "per_target_cap": cap, "visit": visit, "tips": tips + notes,
            "rules": ["只回近 24 小时、你真有话说的帖；最好在对方发帖 15–60 分钟内",
                      "每条 1–3 句，补数据/反例/亲测/精确追问，不写 Great point",
                      "S0–S1 回复里不放链接、不 @ 第三人、不提自己的帖",
                      "两条回复间隔 ≥3 分钟；同一时段别连着回同一个人"]}


# --------------------------------------------------------------------------- #
# check
# --------------------------------------------------------------------------- #
def check_reply(text: str, to: str | None, now: datetime) -> dict:
    st, _, notes, entries = _ctx(now)
    problems, waits, blocks = [], [], []

    r = dc.run_checks(text, "x", "auto", "", "publish")
    for it in r["items"]:
        if it["status"] == "fail":
            problems.append(f"去AI：{it['key']} {it['detail']}" + (f"（{', '.join(it['hits'][:3])}）" if it.get("hits") else ""))
    if re.search(r"\b(great|good|nice|awesome) (point|post|thread|take)\b|\bcouldn'?t agree more\b|\bso true\b|\bthis!+\s*$|🔥|💯",
                 text, re.I):
        problems.append("空泛附和（Great point / so true / 🔥）：换成一个数据、反例或你的实测")
    n_words = len(re.findall(r"[A-Za-z0-9']+", text)) + len(dc.CJK_RE.findall(text))
    if n_words < 6:
        problems.append(f"太短（{n_words} 词），像机器人刷存在感")
    if len(re.findall(r"@\w+", text)) > 0:
        problems.append("回复里 @ 了其他人：回复本身已经通知对方，额外 @ 第三人像拉人刷量")

    recent = [e for _, e in _replies(entries)][-RECENT_N:]
    best = (0.0, "")
    for e in recent:
        prev = e.get("notes") or ""
        if prev:
            ratio = difflib.SequenceMatcher(None, text.lower(), prev.lower()).ratio()
            if ratio > best[0]:
                best = (ratio, prev[:60])
    if best[0] >= SIMILAR_FAIL:
        problems.append(f"和之前的回复相似度 {best[0]:.0%}（“{best[1]}…”），重复回复会被折叠，换个具体内容")

    g = cg.evaluate("x", "reply", bool(dc.URL_RE.search(text)), False, None,
                    cg.load_accounts(_paths()[1]), entries, now)
    if g["verdict"] == "block":
        blocks += g["reasons"]
    elif g["verdict"] == "wait":
        waits += g["reasons"]
    if dc.URL_RE.search(text) and _stage_key(st) in ("S0", "S1"):
        blocks.append(f"{st['name']}：回复里不放链接")

    if to:
        h = _norm(to)
        cap = PER_TARGET_DAY.get(_stage_key(st), 1)
        today_to = [e for dt, e in _replies(entries)
                    if dt.astimezone(now.tzinfo).date() == now.date() and _target_of(e) == h]
        if len(today_to) >= cap:
            waits.append(f"今天已经回过 {h} {len(today_to)} 次（上限 {cap}），明天再回，或换个人")

    verdict = "block" if blocks else ("fix" if problems else ("wait" if waits else "ok"))
    return {"verdict": verdict, "stage": st["name"], "problems": problems, "wait": waits, "block": blocks,
            "max_similarity": round(best[0], 2), "deai_summary": r["summary"], "notes": notes,
            "next_allowed_at": g.get("next_allowed_at")}


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def _now() -> datetime:
    return cg._now()


def _read(path: str) -> str:
    p = Path(path)
    if not p.is_file():
        sys.exit(f"错误：找不到 {p}")
    t = p.read_text(encoding="utf-8").strip()
    if not t:
        sys.exit("错误：回复内容为空")
    return t


def cmd_targets(a) -> int:
    d = load_targets()
    t = d.setdefault("targets", {})
    if a.action == "list":
        if not t:
            print("（目标名单为空。先加 10–30 个同领域账号：targets add --handle @xxx --tier core --topic agents）")
        for h, v in sorted(t.items(), key=lambda x: (x[1].get("tier") != "core", x[0])):
            print(f"  {h:<18} {v.get('tier', 'normal'):<7} {v.get('topic', ''):<16} {v.get('note', '')}")
        return 0
    if not a.handle:
        sys.exit("错误：需要 --handle")
    h = _norm(a.handle)
    if a.action == "remove":
        t.pop(h, None)
    else:
        cur = t.get(h, {"added": _now().date().isoformat()})
        for k in ("tier", "topic", "note"):
            if getattr(a, k):
                cur[k] = getattr(a, k)
        cur.setdefault("tier", "normal")
        t[h] = cur
    save_targets(d)
    print(json.dumps({"ok": True, "count": len(t), a.action: h}, ensure_ascii=False))
    return 0


def cmd_today(a) -> int:
    r = build_today(_now())
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0
    print(f"# X 今日回复任务 · {r['stage']}（第 {r['account_age_days']} 天）")
    print(f"建议 {r['suggest']}，今天已回 {r['done_today']} 条，最多还能回 {r['remaining_max']} 条；同一个人今天最多 {r['per_target_cap']} 次\n")
    for w in r["windows"]:
        print(f"  ⏰ {w['time']}  {w['replies']} 条")
    print("\n去这些人的主页看最新帖（最久没回的在前）：")
    for v in r["visit"]:
        print(f"  {v['handle']:<18} [{v['tier']}] {v['topic']:<14} 上次 {v['last_replied']:<17} {v['profile']}")
    print("\n规则：")
    for x in r["rules"]:
        print(f"  • {x}")
    for x in r["tips"]:
        print(f"  ! {x}")
    return 0


def cmd_check(a) -> int:
    r = check_reply(_read(a.file), a.to, _now())
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        label = {"ok": "✓ 可以发", "fix": "✗ 先改稿", "wait": "… 先等等", "block": "✗ 不能发"}[r["verdict"]]
        print(f"{label}（{r['stage']}，与历史回复最高相似度 {r['max_similarity']:.0%}）")
        for k in ("block", "problems", "wait"):
            for x in r[k]:
                print(f"  - {x}")
        if r["next_allowed_at"]:
            print(f"  最早可发：{r['next_allowed_at']}")
        print(r["deai_summary"])
    return {"ok": 0, "fix": 1, "wait": 3, "block": 4}[r["verdict"]]


def _status_id(url: str) -> tuple[str, str]:
    m = STATUS_RE.search(url)
    if not m:
        sys.exit("错误：不是推文链接（形如 https://x.com/<用户>/status/<数字>）")
    return "@" + m.group(1).lower(), m.group(2)


def cmd_link(a) -> int:
    _, sid = _status_id(a.url)
    url = "https://x.com/intent/post?" + urllib.parse.urlencode({"in_reply_to": sid, "text": _read(a.file)})
    print(url)
    if a.open:
        webbrowser.open(url)
    return 0


def cmd_record(a) -> int:
    text = _read(a.file)
    author, _ = _status_id(a.url)
    to = _norm(a.to) if a.to else author
    cmd = [sys.executable, str(SHARED / "cadence_gate.py"), "record", "--platform", "x", "--type", "reply",
           "--title", f"回复 {to}: {text[:40]}", "--url", a.url, "--tags", f"target:{to}", "--notes", text,
           "--skill-source", "skill-x-reply"]
    if dc.URL_RE.search(text):
        cmd.append("--link")
    r = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ, EASEL_ROOT=str(
        Path(os.environ.get("EASEL_ROOT") or PROJECT_ROOT))))
    if r.returncode != 0:
        sys.exit(r.stderr or r.stdout)
    d = load_targets()
    t = d.setdefault("targets", {})
    if to in t:
        t[to]["last_replied"] = _now().isoformat(timespec="minutes")
        t[to]["replies"] = int(t[to].get("replies", 0)) + 1
        save_targets(d)
    print(json.dumps({"ok": True, "to": to, "in_targets": to in t}, ensure_ascii=False))
    return 0


def cmd_selftest(_a) -> int:
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["EASEL_ROOT"] = tmp
        os.environ["EASEL_CADENCE_NOW"] = "2026-10-12T09:00:00+08:00"
        _, af, lf = _paths()
        cg._atomic_write(af, {"x": {"created": "2026-10-10"}})
        save_targets({"targets": {"@alice": {"tier": "core"}, "@bob": {"tier": "normal"}}})
        good = "Ran the same prompt on 3 repos last week. It only broke on the one with a monorepo, took me 20 min to spot why."
        now = _now()

        def case(name, cond):
            nonlocal ok
            print(f"  {'✓' if cond else '✗'} {name}")
            ok &= bool(cond)

        case("好回复通过", check_reply(good, "@alice", now)["verdict"] == "ok")
        case("Great point 判改稿", check_reply("Great point! So true 🔥", "@alice", now)["verdict"] == "fix")
        case("养号期带链接 block", check_reply(good + " https://example.com", "@alice", now)["verdict"] == "block")
        entry = {"id": 1, "platform": "x", "type": "reply", "tags": ["target:@alice"], "notes": good,
                 "published_at": (now - timedelta(minutes=30)).isoformat()}
        cg._atomic_write(lf, {"entries": [entry]})
        case("同一人今天第二次 wait", check_reply("Different angle: the cache key ignored the branch name, so CI reused stale builds.",
                                             "@alice", now)["verdict"] == "wait")
        case("重复回复判改稿", check_reply(good, "@bob", now)["verdict"] == "fix")
        t = build_today(now)
        case("今日任务跳过今天已回的人", [v["handle"] for v in t["visit"]] == ["@bob"])
        case("回复链接带 in_reply_to", _status_id("https://x.com/Alice/status/123")[1] == "123")
    print("selftest", "通过" if ok else "失败")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="X 每日回复任务")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("targets")
    t.add_argument("action", choices=("add", "list", "remove"))
    t.add_argument("--handle")
    t.add_argument("--tier", choices=("core", "normal"))
    t.add_argument("--topic")
    t.add_argument("--note")
    t.set_defaults(func=cmd_targets)
    s = sub.add_parser("today")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_today)
    c = sub.add_parser("check")
    c.add_argument("--file", required=True)
    c.add_argument("--to")
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=cmd_check)
    l = sub.add_parser("link")
    l.add_argument("--url", required=True)
    l.add_argument("--file", required=True)
    l.add_argument("--open", action="store_true")
    l.set_defaults(func=cmd_link)
    r = sub.add_parser("record")
    r.add_argument("--url", required=True)
    r.add_argument("--to")
    r.add_argument("--file", required=True)
    r.set_defaults(func=cmd_record)
    sub.add_parser("selftest").set_defaults(func=cmd_selftest)
    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
