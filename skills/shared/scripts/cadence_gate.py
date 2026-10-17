#!/usr/bin/env python3
"""cadence_gate.py — 海外平台新号发帖节奏闸门（防 ban / 防限流）.

X / LinkedIn / Blogger / Reddit 的新号最怕的不是内容差，是**节奏像机器**：注册第一天连发十条、
同一个链接刷五个版、一小时加五十个好友。本脚本把“新号起步爬坡表”固化成代码，发之前问一句
“现在能不能发”，由它查账号阶段 + 发布记录给出 allow / wait / block，不靠模型记忆。

阶段按账号年龄（Reddit 另看 karma，取两者里更低的阶段）自动计算；限额见 STAGES。
发布记录复用 skill-publish-log 的 outputs/_analytics/publish-log.json（同一份数据，不另起账本）。

子命令:
  account  --platform P --created YYYY-MM-DD [--handle H] [--karma N] [--followers N]   登记/更新账号
  account  --show                                                                      查看已登记账号
  check    --platform P [--type post|thread|article|comment|reply|invite|follow]
           [--link] [--promo] [--sub r/xxx]                                            能不能发；exit 0 allow / 3 wait / 4 block
  record   --platform P --title T [--type ...] [--link] [--promo] [--sub r/xxx] [--url U] [--profile X]
                                                                                       发完登记（写入 publish-log）
  plan     [--platform P]                                                              本周配额、已用、下一次最早时间
  stages   [--platform P]                                                              打印爬坡表
  selftest

时间一律用本机时区。纯标准库。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("EASEL_ROOT") or Path(__file__).resolve().parents[3])
ANALYTICS = PROJECT_ROOT / "outputs" / "_analytics"
ACCOUNTS_FILE = ANALYTICS / "intl-accounts.json"
LOG_FILE = ANALYTICS / "publish-log.json"

EXIT_ALLOW, EXIT_WAIT, EXIT_BLOCK = 0, 3, 4
POST_TYPES = ("post", "thread", "article")          # 计入“发帖”配额
ENGAGE_TYPES = ("comment", "reply")                 # 计入互动配额
NETWORK_TYPES = ("invite", "follow")                # 加好友 / 关注

# --------------------------------------------------------------------------- #
# 爬坡表：min_age 天数 / min_karma（仅 reddit）→ 限额
#   day/week     每天/每周最多发帖数（thread、article 各算 1 条）
#   gap_h        两条发帖之间的最小间隔（小时）
#   links        发帖正文带外链：no=禁止 / reply=只能放评论或回复 / yes=可以（仍受 link_day 限）
#   link_day     每天最多带链接的帖子
#   promo_ratio  自推内容占近 30 天全部活动（帖+评论）的上限；None = 不限
#   engage_day   每天评论/回复上限（防刷屏，同时也是建议量的上沿）
#   network_day  每天加好友/关注上限
#   sub_gap_h    同一个 subreddit 两帖间隔（仅 reddit）
# --------------------------------------------------------------------------- #
STAGES: dict[str, list[dict]] = {
    "x": [
        dict(name="S0 养号期", min_age=0, day=1, week=5, gap_h=4, links="no", link_day=0,
             promo_ratio=0.0, engage_day=15, network_day=15,
             tip="补全头像/横幅/简介/置顶；每天 5–10 条认真回复同领域中等号（5k–100k 粉），不发外链"),
        dict(name="S1 起步期", min_age=7, day=2, week=12, gap_h=3, links="reply", link_day=1,
             promo_ratio=0.1, engage_day=30, network_day=25,
             tip="每天 1–2 条原创 + 10–20 条回复；外链只放回复里；每周试 1 条串推"),
        dict(name="S2 成长期", min_age=30, day=3, week=20, gap_h=2, links="yes", link_day=1,
             promo_ratio=0.2, engage_day=50, network_day=40,
             tip="每天 2–3 条 + 每周 2 条串推；固定 2 个时段发，形成节奏"),
        dict(name="S3 稳定期", min_age=90, day=5, week=30, gap_h=1.5, links="yes", link_day=2,
             promo_ratio=0.2, engage_day=80, network_day=60,
             tip="按数据调整；长文/Articles 每周 1 篇"),
    ],
    "linkedin": [
        dict(name="S0 养号期", min_age=0, day=1, week=2, gap_h=48, links="reply", link_day=0,
             promo_ratio=0.0, engage_day=10, network_day=10,
             tip="资料补全（头像/Headline 含关键词/About/Featured）；邀请必须附个性化留言；每天 3–5 条有观点的评论"),
        dict(name="S1 起步期", min_age=14, day=1, week=3, gap_h=24, links="reply", link_day=1,
             promo_ratio=0.1, engage_day=20, network_day=15,
             tip="每周 3 帖（周二到周四上午），发完 60 分钟内守着回评论；外链放第一条评论"),
        dict(name="S2 成长期", min_age=60, day=1, week=5, gap_h=20, links="reply", link_day=1,
             promo_ratio=0.2, engage_day=30, network_day=20,
             tip="每周 4–5 帖，加入 PDF 文档帖/图片帖；每周邀请总数 < 100，待通过邀请别积压超过 200"),
    ],
    "blogger": [
        dict(name="S0 新站期", min_age=0, day=1, week=2, gap_h=48, links="yes", link_day=1,
             promo_ratio=None, engage_day=20, network_day=0,
             tip="每周 1–2 篇 1200+ 字原创长文；接 Search Console；别一天灌 20 篇（规模化内容滥用）"),
        dict(name="S1 稳定期", min_age=30, day=1, week=3, gap_h=24, links="yes", link_day=1,
             promo_ratio=None, engage_day=30, network_day=0,
             tip="每周 2–3 篇；每篇有自己的截图/实验/数据；联盟链接带 rel=sponsored 且克制"),
    ],
    "reddit": [
        dict(name="S0 潜水期", min_age=0, min_karma=0, day=0, week=0, gap_h=24, links="no", link_day=0,
             promo_ratio=0.0, engage_day=8, network_day=0, sub_gap_h=0,
             tip="只评论不发帖：每天 3–8 条真评论，分散在 3–5 个版；验证邮箱；不放任何链接"),
        dict(name="S1 试水期", min_age=7, min_karma=20, day=1, week=3, gap_h=24, links="no", link_day=0,
             promo_ratio=0.0, engage_day=12, network_day=0, sub_gap_h=72,
             tip="开始发文字帖（讨论/提问/心得），每帖前读版规和 flair；同一版 3 天最多 1 帖"),
        dict(name="S2 成长期", min_age=30, min_karma=100, day=1, week=5, gap_h=12, links="yes", link_day=1,
             promo_ratio=0.1, engage_day=20, network_day=0, sub_gap_h=48,
             tip="9:1 规则：自推 ≤10%；只在允许自推的版或专用帖（如 Screenshot Saturday）里推"),
        dict(name="S3 稳定期", min_age=90, min_karma=500, day=2, week=7, gap_h=8, links="yes", link_day=1,
             promo_ratio=0.1, engage_day=30, network_day=0, sub_gap_h=48,
             tip="同一内容跨版间隔 ≥24h 且改写，不用短链，不求赞"),
    ],
}
PLATFORMS = tuple(STAGES)


# --------------------------------------------------------------------------- #
# I/O
# --------------------------------------------------------------------------- #
def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        sys.exit(f"错误：无法读取 {path}：{e}")


def _atomic_write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _now() -> datetime:
    fixed = os.environ.get("EASEL_CADENCE_NOW")          # 测试用：固定“现在”
    return datetime.fromisoformat(fixed).astimezone() if fixed else datetime.now().astimezone()


def _parse_dt(s: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.astimezone()


def load_accounts(path: Path = None) -> dict:
    return _load_json(path or ACCOUNTS_FILE, {})


def load_entries(path: Path = None) -> list[dict]:
    data = _load_json(path or LOG_FILE, {"entries": []})
    return data.get("entries", [])


# --------------------------------------------------------------------------- #
# core
# --------------------------------------------------------------------------- #
def stage_for(platform: str, account: dict | None, now: datetime) -> tuple[dict, int, list[str]]:
    notes = []
    if not account or not account.get("created"):
        notes.append(f"未登记 {platform} 账号注册日期，按最严的 S0 处理；先跑 account --platform {platform} --created YYYY-MM-DD")
        return STAGES[platform][0], 0, notes
    created = date.fromisoformat(account["created"])
    age = (now.date() - created).days
    floor = 0
    # 老号沉睡后重新起用（active_since）：阶段按“开始活跃”算，而不是按注册时长——
    # 沉睡号突然高频活跃同样会被风控盯上；注册已满 90 天的号可以跳过养号期，从 S1 起步。
    if account.get("active_since"):
        active = date.fromisoformat(account["active_since"])
        if (active - created).days >= 90:
            floor = 1
        age = (now.date() - active).days
        notes.append(f"按开始活跃日 {active.isoformat()} 计阶段（注册于 {created.isoformat()}）")
    karma = int(account.get("karma") or 0)
    chosen = STAGES[platform][min(floor, len(STAGES[platform]) - 1)]
    for st in STAGES[platform]:
        if age >= st["min_age"] and karma >= st.get("min_karma", 0) and \
                STAGES[platform].index(st) >= floor:
            chosen = st
    if account.get("followers") is not None and int(account["followers"]) < 50 and platform in ("x", "linkedin"):
        notes.append(f"粉丝 {account['followers']} 个：前期主要靠回复同领域账号涨粉，原创帖别指望有曝光")
    if platform == "reddit" and "karma" not in account:
        notes.append("未登记 karma，Reddit 阶段按 karma=0 计；更新：account --platform reddit --karma N")
    return chosen, age, notes


def _platform_entries(entries: list[dict], platform: str) -> list[tuple[datetime, dict]]:
    out = []
    for e in entries:
        if (e.get("platform") or "").lower() != platform:
            continue
        dt = _parse_dt(e.get("published_at") or "")
        if dt:
            out.append((dt, e))
    out.sort(key=lambda x: x[0])
    return out


def _kind(e: dict) -> str:
    t = (e.get("type") or "post").lower()
    return t if t in POST_TYPES + ENGAGE_TYPES + NETWORK_TYPES else "post"


def _tags(e: dict) -> set[str]:
    return {t.lower() for t in (e.get("tags") or [])}


def evaluate(platform: str, kind: str, has_link: bool, promo: bool, sub: str | None,
             accounts: dict, entries: list[dict], now: datetime) -> dict:
    st, age, notes = stage_for(platform, accounts.get(platform), now)
    hist = _platform_entries(entries, platform)
    today = [e for dt, e in hist if dt.astimezone(now.tzinfo).date() == now.date()]
    week = [e for dt, e in hist if now - dt < timedelta(days=7)]
    month = [e for dt, e in hist if now - dt < timedelta(days=30)]
    posts_today = [e for e in today if _kind(e) in POST_TYPES]
    posts_week = [e for e in week if _kind(e) in POST_TYPES]
    reasons_block, reasons_wait = [], []
    next_at = None

    def wait_until(t: datetime, why: str):
        nonlocal next_at
        reasons_wait.append(why)
        next_at = max(next_at, t) if next_at else t

    if kind in POST_TYPES:
        if st["week"] == 0:
            reasons_block.append(f"{st['name']}：还不能发帖，只评论（{st['tip']}）")
        if st["day"] and len(posts_today) >= st["day"]:
            tomorrow = datetime.combine(now.date() + timedelta(days=1), datetime.min.time()).astimezone()
            wait_until(tomorrow + timedelta(hours=8), f"今天已发 {len(posts_today)}/{st['day']} 帖")
        if st["week"] and len(posts_week) >= st["week"]:
            oldest = min(dt for dt, e in hist if now - dt < timedelta(days=7) and _kind(e) in POST_TYPES)
            wait_until(oldest + timedelta(days=7), f"近 7 天已发 {len(posts_week)}/{st['week']} 帖")
        last_post = [dt for dt, e in hist if _kind(e) in POST_TYPES]
        if last_post and now - last_post[-1] < timedelta(hours=st["gap_h"]):
            wait_until(last_post[-1] + timedelta(hours=st["gap_h"]), f"距上一帖不足 {st['gap_h']} 小时")
        if has_link:
            if st["links"] == "no":
                reasons_block.append(f"{st['name']}：正文不能带外链")
            elif st["links"] == "reply":
                reasons_block.append(f"{st['name']}：外链只能放第一条评论/回复，正文去掉链接")
            else:
                linked_today = [e for e in posts_today if "link" in _tags(e)]
                if len(linked_today) >= st["link_day"]:
                    wait_until(datetime.combine(now.date() + timedelta(days=1), datetime.min.time()).astimezone()
                               + timedelta(hours=8), f"今天带链接的帖已达 {st['link_day']} 条")
        if platform == "reddit" and sub:
            same = [dt for dt, e in hist if f"sub:{sub.lower()}" in _tags(e) and _kind(e) in POST_TYPES]
            if same and st.get("sub_gap_h") and now - same[-1] < timedelta(hours=st["sub_gap_h"]):
                wait_until(same[-1] + timedelta(hours=st["sub_gap_h"]), f"{sub} 距上次发帖不足 {st['sub_gap_h']} 小时")
    elif kind in ENGAGE_TYPES:
        n = len([e for e in today if _kind(e) in ENGAGE_TYPES])
        if n >= st["engage_day"]:
            wait_until(datetime.combine(now.date() + timedelta(days=1), datetime.min.time()).astimezone()
                       + timedelta(hours=8), f"今天评论/回复已 {n}/{st['engage_day']}，再多像刷屏")
        if has_link and st["links"] == "no":
            reasons_block.append(f"{st['name']}：评论里也不要放链接")
        recent = [dt for dt, e in hist if _kind(e) in ENGAGE_TYPES]
        if recent and now - recent[-1] < timedelta(minutes=3):
            wait_until(recent[-1] + timedelta(minutes=3), "两条评论间隔不足 3 分钟")
    elif kind in NETWORK_TYPES:
        n = len([e for e in today if _kind(e) in NETWORK_TYPES])
        if st["network_day"] == 0:
            reasons_block.append(f"{platform} 不需要批量加好友/关注")
        elif n >= st["network_day"]:
            wait_until(datetime.combine(now.date() + timedelta(days=1), datetime.min.time()).astimezone()
                       + timedelta(hours=8), f"今天加好友/关注已 {n}/{st['network_day']}")

    if promo and st["promo_ratio"] is not None:
        acts = [e for e in month if _kind(e) in POST_TYPES + ENGAGE_TYPES]
        promos = [e for e in acts if "promo" in _tags(e)]
        ratio_after = (len(promos) + 1) / (len(acts) + 1)
        if st["promo_ratio"] == 0:
            reasons_block.append(f"{st['name']}：还不能发自推内容")
        elif ratio_after > st["promo_ratio"]:
            need = int((len(promos) + 1) / st["promo_ratio"]) - len(acts) - 1
            reasons_block.append(f"自推占比会到 {ratio_after:.0%}（上限 {st['promo_ratio']:.0%}），"
                                 f"先做约 {max(need, 1)} 条非自推的帖子/评论")

    verdict = "block" if reasons_block else ("wait" if reasons_wait else "allow")
    return {
        "platform": platform, "type": kind, "verdict": verdict, "stage": st["name"], "account_age_days": age,
        "reasons": reasons_block + reasons_wait, "next_allowed_at": next_at.isoformat(timespec="minutes") if next_at else None,
        "posts_today": len(posts_today), "posts_week": len(posts_week),
        "limits": {k: st[k] for k in ("day", "week", "gap_h", "links", "promo_ratio", "engage_day", "network_day")},
        "tip": st["tip"], "notes": notes,
    }


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def cmd_account(a) -> int:
    accounts = load_accounts()
    if a.show or not a.platform:
        print(json.dumps(accounts, ensure_ascii=False, indent=2) if accounts else "（未登记任何海外账号）")
        return 0
    acc = accounts.get(a.platform, {})
    for k in ("created", "active_since", "handle", "karma", "followers"):
        v = getattr(a, k)
        if v is not None:
            acc[k] = v
    for k in ("created", "active_since"):
        if k in acc:
            date.fromisoformat(acc[k])              # 校验格式
    acc["updated_at"] = _now().isoformat(timespec="minutes")
    accounts[a.platform] = acc
    _atomic_write(ACCOUNTS_FILE, accounts)
    st, age, notes = stage_for(a.platform, acc, _now())
    print(json.dumps({"ok": True, "platform": a.platform, "account": acc, "stage": st["name"],
                      "age_days": age, "tip": st["tip"], "notes": notes}, ensure_ascii=False, indent=2))
    return 0


def cmd_check(a) -> int:
    r = evaluate(a.platform, a.type, a.link, a.promo, a.sub, load_accounts(), load_entries(), _now())
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return {"allow": EXIT_ALLOW, "wait": EXIT_WAIT, "block": EXIT_BLOCK}[r["verdict"]]


def cmd_record(a) -> int:
    data = _load_json(LOG_FILE, {"version": "1.0", "entries": []})
    data.setdefault("entries", [])
    tags = [t.strip() for t in (a.tags or "").split(",") if t.strip()]
    if a.link:
        tags.append("link")
    if a.promo:
        tags.append("promo")
    if a.sub:
        tags.append(f"sub:{a.sub.lower()}")
    now_iso = _now().isoformat(timespec="seconds")
    entry = {
        "id": max((e.get("id", 0) for e in data["entries"]), default=0) + 1,
        "platform": a.platform, "title": a.title, "url": a.url or "", "type": a.type,
        "published_at": a.published_at or now_iso, "logged_at": now_iso,
        "initial_metrics": {"views": None, "likes": None, "comments": None, "shares": None},
        "skill_source": a.skill_source or "cadence_gate", "profile": a.profile or "",
        "persona_check": {"score": None, "verdict": ""}, "tags": tags, "notes": a.notes or "",
    }
    data["entries"].append(entry)
    _atomic_write(LOG_FILE, data)
    print(json.dumps({"ok": True, "entry": entry}, ensure_ascii=False, indent=2))
    return 0


def cmd_plan(a) -> int:
    accounts, entries, now = load_accounts(), load_entries(), _now()
    rows = []
    for p in ([a.platform] if a.platform else PLATFORMS):
        r = evaluate(p, "post", False, False, None, accounts, entries, now)
        rows.append({"platform": p, "stage": r["stage"], "age_days": r["account_age_days"],
                     "today": f"{r['posts_today']}/{r['limits']['day']}", "week": f"{r['posts_week']}/{r['limits']['week']}",
                     "can_post_now": r["verdict"], "next_allowed_at": r["next_allowed_at"],
                     "reasons": r["reasons"], "tip": r["tip"], "notes": r["notes"]})
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


def cmd_stages(a) -> int:
    for p in ([a.platform] if a.platform else PLATFORMS):
        print(f"\n## {p}")
        for st in STAGES[p]:
            karma = f" & karma≥{st['min_karma']}" if "min_karma" in st else ""
            print(f"  {st['name']}（第 {st['min_age']} 天起{karma}）: 帖 {st['day']}/天 {st['week']}/周 间隔≥{st['gap_h']}h "
                  f"外链={st['links']} 自推≤{st['promo_ratio']} 评论≤{st['engage_day']}/天 加人≤{st['network_day']}/天")
            print(f"     {st['tip']}")
    return 0


def cmd_selftest(_a) -> int:
    now = datetime(2026, 10, 12, 15, 0).astimezone()
    acc = {"x": {"created": "2026-10-10"}, "reddit": {"created": "2026-10-01", "karma": 5},
           "linkedin": {"created": "2026-08-01"}}

    def ent(p, hours_ago, t="post", tags=()):
        return {"platform": p, "type": t, "tags": list(tags),
                "published_at": (now - timedelta(hours=hours_ago)).isoformat()}

    cases = [
        ("X 新号首帖允许", evaluate("x", "post", False, False, None, acc, [], now)["verdict"] == "allow"),
        ("X 养号期带链接 block", evaluate("x", "post", True, False, None, acc, [], now)["verdict"] == "block"),
        ("X 养号期今天已发 1 帖 wait",
         evaluate("x", "post", False, False, None, acc, [ent("x", 5)], now)["verdict"] == "wait"),
        ("Reddit karma 低于 20 不能发帖",
         evaluate("reddit", "post", False, False, "r/pcgaming", acc, [], now)["verdict"] == "block"),
        ("Reddit 潜水期可以评论", evaluate("reddit", "comment", False, False, None, acc, [], now)["verdict"] == "allow"),
        ("Reddit 同版 72h 冷却",
         evaluate("reddit", "post", False, False, "r/pcgaming",
                  {"reddit": {"created": "2026-09-20", "karma": 50}},
                  [ent("reddit", 30, tags=["sub:r/pcgaming"])], now)["verdict"] == "wait"),
        ("Reddit 自推超 10% block",
         evaluate("reddit", "post", True, True, "r/indiegaming",
                  {"reddit": {"created": "2026-08-01", "karma": 300}},
                  [ent("reddit", 50, "comment"), ent("reddit", 60, tags=["promo"])], now)["verdict"] == "block"),
        ("LinkedIn 24h 内第二帖 wait",
         evaluate("linkedin", "post", False, False, None, acc, [ent("linkedin", 10)], now)["verdict"] == "wait"),
        ("LinkedIn 正文外链 block（放评论）",
         evaluate("linkedin", "post", True, False, None, acc, [], now)["verdict"] == "block"),
        ("未登记账号按 S0 并提示", bool(evaluate("blogger", "post", False, False, None, {}, [], now)["notes"])),
        ("老号刚起用：按起用日从 S1 起步，不按注册时长给 S3",
         stage_for("x", {"created": "2025-07-01", "active_since": "2026-10-12"}, now)[0]["name"].startswith("S1")),
        ("老号起用满 30 天进 S2",
         stage_for("x", {"created": "2025-07-01", "active_since": "2026-09-01"}, now)[0]["name"].startswith("S2")),
        ("新号起用不跳养号期",
         stage_for("x", {"created": "2026-10-01", "active_since": "2026-10-10"}, now)[0]["name"].startswith("S0")),
    ]
    ok = True
    for name, passed in cases:
        print(f"  {'✓' if passed else '✗'} {name}")
        ok &= passed
    print("selftest", "通过" if ok else "失败")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="海外平台新号发帖节奏闸门（防 ban）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("account")
    s.add_argument("--platform", choices=PLATFORMS)
    s.add_argument("--created", help="注册日期 YYYY-MM-DD")
    s.add_argument("--active-since", dest="active_since",
                   help="老号重新起用的日期 YYYY-MM-DD：阶段从这天算（注册满 90 天的号从 S1 起步）")
    s.add_argument("--handle")
    s.add_argument("--karma", type=int)
    s.add_argument("--followers", type=int)
    s.add_argument("--show", action="store_true")
    s.set_defaults(func=cmd_account)

    for name, fn in (("check", cmd_check), ("record", cmd_record)):
        s = sub.add_parser(name)
        s.add_argument("--platform", choices=PLATFORMS, required=True)
        s.add_argument("--type", choices=POST_TYPES + ENGAGE_TYPES + NETWORK_TYPES, default="post")
        s.add_argument("--link", action="store_true", help="正文含外链")
        s.add_argument("--promo", action="store_true", help="自推内容（推自己的博客/产品/频道）")
        s.add_argument("--sub", help="Reddit 版名，如 r/pcgaming")
        if name == "record":
            s.add_argument("--title", required=True)
            s.add_argument("--url")
            s.add_argument("--profile")
            s.add_argument("--tags")
            s.add_argument("--notes")
            s.add_argument("--published-at", dest="published_at")
            s.add_argument("--skill-source", dest="skill_source")
        s.set_defaults(func=fn)

    s = sub.add_parser("plan")
    s.add_argument("--platform", choices=PLATFORMS)
    s.set_defaults(func=cmd_plan)
    s = sub.add_parser("stages")
    s.add_argument("--platform", choices=PLATFORMS)
    s.set_defaults(func=cmd_stages)
    s = sub.add_parser("selftest")
    s.set_defaults(func=cmd_selftest)

    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
