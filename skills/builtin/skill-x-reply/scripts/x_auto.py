#!/usr/bin/env python3
"""x_auto.py — X 回复任务的自动运行：定时找帖 → DeepSeek 起草 → 自动检查 → 进待发队列 → 人逐条点发.

为什么不做“全自动发出去”：X 自动化规则不允许程序基于搜索/关注列表自动给别人发回复，新号更是一抓一个准。
所以自动化到“点发送”之前为止：找帖、起草、去AI自查、查重、配额都由程序做，人每天花几分钟逐条确认。

帖子从哪来（任选，可叠加）：
  1. X 官方 API（配置 X_BEARER_TOKEN，读权限收费）：自动拉目标名单的新帖，以及别人对你的回复（@提及）
  2. 收件箱 outputs/x-replies/inbox.md：随手丢推文链接（一行一个，可在下面附原文）；
     没附原文时用官方 oEmbed 接口取正文（免费，不用登录）

子命令:
  check                                   配置自检（脱敏）
  watchlist import [--file 路径]           从 outputs/x-replies/watchlist.md 导入目标名单（★ = core）
  inbox add <推文链接>... [--text 原文] [--no-draft]   丢进收件箱并立刻起草
  run     [--slot auto|0|1|2] [--force] [--dry-run] [--max N] [--profile 名]   找帖 + 起草一轮，写入当日队列
  queue   [--date YYYY-MM-DD]             看当日队列
  review  [--date YYYY-MM-DD]             逐条确认：选稿 → 发前检查 → 打开回复链接 → 你发完按 y 登记
  install [--python 路径] / uninstall / status     macOS launchd 定时（三个时段各跑一次 run）
  selftest

起草模型：DeepSeek（OpenAI 兼容），读项目根 .env 的 DEEPSEEK_API_KEY / DEEPSEEK_API_BASE / DEEPSEEK_MODEL。
"""
from __future__ import annotations

import argparse
import difflib
import html
import json
import math
import os
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))

import x_reply as xr  # noqa: E402

cg, dc = xr.cg, xr.dc

LABEL = "com.easel.x-autoreply"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
# 每个时段开始后 5 分钟跑一次；时段本身见 x_reply.WINDOWS
RUN_TIMES = [(8, 35), (12, 5), (20, 5)]
MAX_AGE_H = 12              # 自动找帖只要 12 小时内的（回得越早越有用；超过 24 小时基本没人看）
API = "https://api.x.com/2"
# 字数档（X 加权字数）：回复越短越像真人；按概率抽，避免每条都一样长
LENGTHS = [("tiny", 30, 70, 0.35), ("short", 70, 130, 0.5), ("medium", 130, 190, 0.15)]
# 没有 my-notes.md 素材时，这些说法等于编经历
FIRST_PERSON = re.compile(r"\b(i(?:'ve| have)? (?:seen|tried|tested|ran|run|built|used|shipped|measured|found|hit)|"
                          r"in my (?:experience|tests?|team|setup)|we (?:cut|saw|ran|tried|built|found|shipped)|"
                          r"my (?:team|tests?|setup|experience)|for me)\b|我(?:试过|测过|用过|跑过|发现)", re.I)
STYLES = ["add_data", "own_counterexample", "precise_question", "tool_or_step", "disagree_with_reason"]


def _root() -> Path:
    return Path(os.environ.get("EASEL_ROOT") or xr.PROJECT_ROOT)


def _dir() -> Path:
    return _root() / "outputs" / "x-replies"


def _now() -> datetime:
    return cg._now()


# --------------------------------------------------------------------------- #
# env
# --------------------------------------------------------------------------- #
def load_env() -> None:
    f = _root() / ".env"
    if not f.is_file():
        return
    for raw in f.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _mask(v: str) -> str:
    return "未配置" if not v else f"已配置（{len(v)} 位，…{v[-4:]}）"


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def _http(url: str, data: dict | None = None, headers: dict | None = None, timeout: int = 60) -> dict:
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers={"User-Agent": "easel-x-reply/0.2", **(headers or {})})
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def deepseek(messages: list[dict], temperature: float = 1.0) -> dict:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise RuntimeError("缺 DEEPSEEK_API_KEY（写在项目根 .env）")
    base = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1").rstrip("/")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    payload = {"model": model, "messages": messages, "temperature": temperature,
               "response_format": {"type": "json_object"}, "max_tokens": 800}
    last = None
    for attempt in range(3):
        try:
            r = _http(f"{base}/chat/completions", payload, {"Authorization": f"Bearer {key}"}, timeout=90)
            return json.loads(r["choices"][0]["message"]["content"])
        except urllib.error.HTTPError as e:
            last = f"DeepSeek HTTP {e.code}"
            if e.code in (401, 402, 403):
                break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as e:
            last = f"DeepSeek 调用失败：{type(e).__name__}"
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(last or "DeepSeek 调用失败")


# --------------------------------------------------------------------------- #
# 找帖
# --------------------------------------------------------------------------- #
def _x_get(path: str, params: dict) -> dict:
    tok = os.environ.get("X_BEARER_TOKEN", "")
    return _http(f"{API}{path}?{urllib.parse.urlencode(params)}", headers={"Authorization": f"Bearer {tok}"}, timeout=30)


def _parse_time(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def fetch_api(visit: list[dict], me: str, now: datetime, log: list[str]) -> list[dict]:
    """官方 API：目标名单的新帖 + 别人对我的回复。没有 X_BEARER_TOKEN 就跳过。"""
    if not os.environ.get("X_BEARER_TOKEN"):
        return []
    out: list[dict] = []
    d = xr.load_targets()
    targets = d.setdefault("targets", {})
    since = (now - timedelta(hours=MAX_AGE_H)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fields = {"tweet.fields": "created_at,lang,public_metrics,conversation_id", "start_time": since}
    try:
        if me:
            mid = _x_get(f"/users/by/username/{me.lstrip('@')}", {})["data"]["id"]
            r = _x_get(f"/users/{mid}/mentions", {**fields, "max_results": 10, "expansions": "author_id",
                                                   "user.fields": "username"})
            names = {u["id"]: u["username"] for u in r.get("includes", {}).get("users", [])}
            for t in r.get("data", []):
                h = names.get(t.get("author_id"), "")
                if h:
                    out.append({"url": f"https://x.com/{h}/status/{t['id']}", "to": xr._norm(h), "text": t["text"],
                                "created_at": t["created_at"], "source": "mention"})
        for v in visit:
            h = v["handle"]
            t = targets.get(h, {})
            if not t.get("user_id"):
                t["user_id"] = _x_get(f"/users/by/username/{h[1:]}", {})["data"]["id"]
            r = _x_get(f"/users/{t['user_id']}/tweets", {**fields, "max_results": 5, "exclude": "retweets,replies"})
            for tw in r.get("data", []):
                out.append({"url": f"https://x.com/{h[1:]}/status/{tw['id']}", "to": h, "text": tw["text"],
                            "created_at": tw["created_at"], "source": "target", "tier": v["tier"],
                            "likes": (tw.get("public_metrics") or {}).get("like_count", 0)})
        xr.save_targets(d)
    except urllib.error.HTTPError as e:
        log.append(f"X API 返回 {e.code}（402/403 多半是没开读权限或额度用完），本轮只用收件箱")
    except (urllib.error.URLError, TimeoutError, KeyError) as e:
        log.append(f"X API 不可用（{type(e).__name__}），本轮只用收件箱")
    return out


def oembed_text(url: str) -> str:
    """官方 oEmbed 接口拿推文正文（公开推文、免登录）。"""
    try:
        r = _http("https://publish.twitter.com/oembed?" + urllib.parse.urlencode(
            {"url": url, "omit_script": 1, "dnt": "true"}), timeout=20)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return ""
    m = re.search(r"<p[^>]*>(.*?)</p>", r.get("html", ""), re.S)
    if not m:
        return ""
    t = re.sub(r"<br\s*/?>", "\n", m.group(1))
    return html.unescape(re.sub(r"<[^>]+>", "", t)).strip()


def read_inbox(log: list[str]) -> list[dict]:
    f = _dir() / "inbox.md"
    if not f.is_file():
        return []
    items, cur = [], None
    for line in f.read_text(encoding="utf-8").splitlines():
        m = xr.STATUS_RE.search(line)
        if m and line.strip().startswith("http"):
            cur = {"url": line.strip().split()[0], "to": "@" + m.group(1).lower(), "text": "", "source": "inbox"}
            items.append(cur)
        elif cur is not None and line.strip() != "---" and not line.startswith("#"):
            cur["text"] += line + "\n"
    for it in items:
        it["text"] = it["text"].strip() or oembed_text(it["url"])
        if not it["text"]:
            log.append(f"拿不到正文，跳过：{it['url']}（在收件箱链接下一行贴上原文即可）")
    return [it for it in items if it["text"]]


def clear_inbox(processed: list[str]) -> None:
    """处理过的链接从收件箱挪到 inbox.done.md。"""
    f = _dir() / "inbox.md"
    if not f.is_file() or not processed:
        return
    keep, done, cur_done = [], [], False
    for line in f.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("http") and xr.STATUS_RE.search(line):
            cur_done = line.strip().split()[0] in processed
        (done if cur_done else keep).append(line)
    f.write_text("\n".join(keep).strip() + "\n", encoding="utf-8")
    with (_dir() / "inbox.done.md").open("a", encoding="utf-8") as fh:
        fh.write("\n".join(done) + "\n")


# --------------------------------------------------------------------------- #
# 状态 / 队列
# --------------------------------------------------------------------------- #
def _state() -> dict:
    return cg._load_json(_dir() / "_state.json", {"seen": {}})


def _queue_path(day: str) -> Path:
    return _dir() / day / "queue.json"


def load_queue(day: str) -> dict:
    return cg._load_json(_queue_path(day), {"date": day, "items": []})


def _replied_urls() -> set[str]:
    _, _, lf = xr._paths()
    return {(e.get("url") or "").split("?")[0] for _, e in xr._replies(cg.load_entries(lf))}


def _sid(url: str) -> str:
    m = xr.STATUS_RE.search(url)
    return m.group(2) if m else ""


def slot_quota(now: datetime, slot: str, force: bool) -> tuple[int, int, dict]:
    """返回 (本轮最多起草几条, 时段序号, 今日任务单)。"""
    today = xr.build_today(now)
    remaining = today["remaining_max"]
    windows = []
    for w in xr.WINDOWS:
        a, b = w.split("–")
        mk = lambda s: now.replace(hour=int(s[:2]), minute=int(s[3:]), second=0, microsecond=0)  # noqa: E731
        windows.append((mk(a), mk(b)))
    if slot == "auto":
        idx = next((i for i, (_, end) in enumerate(windows) if now < end), len(windows))
    else:
        idx = int(slot)
    pending = sum(1 for it in load_queue(now.date().isoformat())["items"] if it["status"] == "pending")
    if force:      # 人亲手挑的帖（inbox add）：不按时段摊，只要今天总量没满就起草
        return max(0, remaining - pending), idx, today
    if idx >= len(windows):
        return 0, idx, today
    left = len(windows) - idx
    return max(0, math.ceil(remaining / left) - pending), idx, today


# --------------------------------------------------------------------------- #
# 起草
# --------------------------------------------------------------------------- #
def _profile_text(name: str | None) -> str:
    if not name:
        name = os.environ.get("X_REPLY_PROFILE", "")
    if not name:
        return ""
    for base in (_root() / "easel-profiles", _root() / "profiles"):
        d = base / name
        if d.is_dir():
            parts = []
            for f in ("identity.md", "style.md", "preferences.md"):
                p = d / f
                if p.is_file():
                    parts.append(p.read_text(encoding="utf-8")[:1500])
            return "\n\n".join(parts)
    return ""


def _notes() -> str:
    f = _dir() / "my-notes.md"
    if not f.is_file():
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("# 我的真实经历和数据（自动回复只能引用这里写过的事，不会编）\n\n"
                     "- 例：用 Claude Code 重构过一个 4 万行的 Django 项目，34 处改动错了 3 处，都在 migrations\n", encoding="utf-8")
    t = f.read_text(encoding="utf-8")
    return "" if "例：用 Claude Code 重构过" in t and t.count("\n- ") <= 1 else t[:3000]


SYSTEM = """You draft replies on X (Twitter) for one real person. The person reviews and posts every reply by hand.

Who they are:
{persona}

Things they have actually done or measured (the ONLY first-person facts you may use; never invent others):
{notes}

Write replies that a busy practitioner would type on their phone:
- Reply in the same language as the tweet.
- The first words carry information. Never open with praise or agreement.
- One sentence is best, two at most. Say one thing. Contractions, plain words, normal capitalization.
  No hashtags, no emoji, no links, no @mentions, no images.
- Sound like a quick reply typed on a phone, not a mini essay: no setup, no summary, no sign-off.
- Banned: em dashes (—), "Great point", "So true", "This!", "Couldn't agree more", "Thanks for sharing",
  "game-changer", "delve", "crucial", "leverage", "landscape", "navigate", "unlock", "in today's", "it's not X, it's Y",
  lists of three adjectives, a closing question aimed at everyone ("What do you think?"), any self-promotion.
- Styles: add_data (a concrete number or fact), own_counterexample (where it broke for them), precise_question
  (one specific question that shows they read it), tool_or_step (one concrete step or setting), disagree_with_reason
  (one concrete reason, then stop). Use own_counterexample / add_data / tool_or_step ONLY if the notes above support it;
  otherwise use precise_question or disagree_with_reason, or a well-known public fact you are sure of.
- No arguing, no politics, no drama. If the tweet is a giveaway, engagement bait, an ad, politics, tragedy, or there is
  nothing useful to add, set "skip": true.

Return JSON: {{"skip": bool, "reason": "short", "options": [{{"style": "...", "text": "..."}}, {{"style": "...", "text": "..."}}]}}
The two options must use different styles and start differently."""


def _target_len(stage_key: str, rnd: random.Random) -> tuple[str, int, int]:
    choices = LENGTHS if stage_key not in ("S0",) else LENGTHS[:2]
    total = sum(c[3] for c in choices)
    x, acc = rnd.random() * total, 0.0
    for name, lo, hi, p in choices:
        acc += p
        if x <= acc:
            return name, lo, hi
    return choices[-1][:3]


def _content_problems(text: str, to: str, now: datetime, lo: int, hi: int, batch: list[str],
                      has_notes: bool = True) -> list[str]:
    r = xr.check_reply(text, to, now)
    probs = list(r["problems"]) + [b for b in r["block"] if "链接" in b]
    n = dc.x_weighted_len(text)
    if n > 280:
        probs.append(f"超过 280 加权字（{n}）")
    elif n > hi * 1.3 or n < lo * 0.6:
        probs.append(f"长度 {n}，目标 {lo}–{hi}")
    if not has_notes and FIRST_PERSON.search(text):
        probs.append(f"没有素材却写了亲身经历（“{FIRST_PERSON.search(text).group(0)}”），改成追问或公开事实")
    if "—" in text:
        probs.append("有破折号")
    for prev in batch:
        if difflib.SequenceMatcher(None, text.lower(), prev.lower()).ratio() >= xr.SIMILAR_FAIL:
            probs.append("和本轮另一条回复太像")
            break
    return probs


def draft_one(tw: dict, persona: str, notes: str, stage_key: str, now: datetime, batch: list[str],
              rnd: random.Random) -> dict:
    name, lo, hi = _target_len(stage_key, rnd)
    sys_msg = SYSTEM.format(persona=persona or "An engineer who uses AI tools daily in real work; dry, specific, no hype.",
                            notes=notes or "(none provided; so no first-person claims at all)")
    user = (f"Tweet by {tw['to']}:\n\"\"\"\n{tw['text'][:1200]}\n\"\"\"\n\n"
            f"Target length for each option: {lo}-{hi} characters ({name}).")
    msgs = [{"role": "system", "content": sys_msg}, {"role": "user", "content": user}]
    out = deepseek(msgs)
    for attempt in range(2):
        if out.get("skip"):
            return {"skip": True, "reason": out.get("reason", "")}
        opts = [o for o in out.get("options", []) if isinstance(o, dict) and o.get("text", "").strip()][:2]
        checked = []
        for o in opts:
            text = o["text"].strip().strip('"')
            checked.append({"style": o.get("style", ""), "text": text,
                            "problems": _content_problems(text, tw["to"], now, lo, hi, batch, bool(notes))})
        good = [c for c in checked if not c["problems"]]
        if len(good) == len(checked) == 2:
            return {"skip": False, "length": name, "options": checked}
        if attempt == 1:   # 重写一次还不行：只留过检的；一条都没有就不发这条
            return {"skip": False, "length": name, "options": good} if good else \
                {"skip": True, "reason": "两次都没写出过检的稿：" + "; ".join(checked[0]["problems"][:2]) if checked else "空稿"}
        fb = "; ".join(f"option {i + 1}: {', '.join(c['problems'])}" for i, c in enumerate(checked) if c["problems"])
        msgs += [{"role": "assistant", "content": json.dumps(out, ensure_ascii=False)},
                 {"role": "user", "content": f"Fix these and return the same JSON: {fb}"}]
        out = deepseek(msgs, temperature=0.9)
    return {"skip": True, "reason": "没生成出可用稿"}


def _notify(msg: str) -> None:
    if sys.platform == "darwin" and not os.environ.get("EASEL_NO_NOTIFY"):
        safe = msg.replace("\\", "").replace('"', "'")
        subprocess.run(["osascript", "-e", f'display notification "{safe}" with title "X 回复任务"'],
                       capture_output=True)


def cmd_run(a) -> int:
    load_env()
    now = _now()
    day = now.date().isoformat()
    log: list[str] = []
    quota, idx, today = slot_quota(now, a.slot, a.force)
    if a.max is not None:
        quota = min(quota, a.max)
    st_key = today["stage"].split()[0]
    print(f"[{now:%H:%M}] {today['stage']}，今天已回 {today['done_today']} 条，本轮最多起草 {quota} 条")
    if quota <= 0:
        print("本轮不用起草（配额已满、还有待发的稿，或已过最后一个时段）")
        return 0

    _, af, _ = xr._paths()
    me = (cg.load_accounts(af).get("x") or {}).get("handle", "")
    st = _state()
    seen, replied = st["seen"], _replied_urls()
    q = load_queue(day)
    queued = {it["url"] for it in q["items"]}
    inbox = read_inbox(log)
    cands = inbox + fetch_api(today["visit"], me, now, log)
    fresh = []
    cap = today["per_target_cap"]
    per_to: dict[str, int] = {}
    for it in q["items"]:
        per_to[it["to"]] = per_to.get(it["to"], 0) + 1
    for c in cands:
        sid = _sid(c["url"])
        if not sid or sid in seen or c["url"].split("?")[0] in replied or c["url"] in queued:
            continue
        if me and c["to"] == xr._norm(me):
            continue
        if c.get("created_at") and now - _parse_time(c["created_at"]) > timedelta(hours=MAX_AGE_H):
            continue
        fresh.append(c)
    # 优先级：别人回我的 > 收件箱（人挑过的）> core 目标 > 其他；同级里越新越好
    rank = {"mention": 0, "inbox": 1}
    fresh.sort(key=lambda c: (rank.get(c["source"], 2 if c.get("tier") == "core" else 3),
                              -(_parse_time(c["created_at"]).timestamp() if c.get("created_at") else now.timestamp())))
    persona, notes = _profile_text(a.profile), _notes()
    rnd = random.Random(f"{day}-{idx}")
    batch = [o["text"] for it in q["items"] for o in it["options"]]
    made, processed = 0, []
    for c in fresh:
        if made >= quota:
            break
        if c["source"] != "mention" and per_to.get(c["to"], 0) >= cap:
            continue
        sid = _sid(c["url"])
        processed.append(c["url"])
        if a.dry_run:
            print(f"  · 会起草：{c['to']} {c['url']}")
            made += 1
            continue
        try:
            d = draft_one(c, persona, notes, st_key, now, batch, rnd)
        except RuntimeError as e:
            log.append(str(e))
            break
        seen[sid] = day
        if d.get("skip"):
            print(f"  - 跳过 {c['to']}：{d.get('reason', '')}")
            continue
        folder = _dir() / day
        folder.mkdir(parents=True, exist_ok=True)
        opts = []
        for i, o in enumerate(d["options"], 1):
            f = folder / f"{c['to'][1:]}-{sid}.{i}.md"
            f.write_text(o["text"] + "\n", encoding="utf-8")
            opts.append({**o, "file": str(f.relative_to(_root()))})
            batch.append(o["text"])
        q["items"].append({"url": c["url"], "to": c["to"], "tweet": c["text"][:500], "source": c["source"],
                           "slot": idx, "length": d["length"], "options": opts, "status": "pending",
                           "drafted_at": now.isoformat(timespec="minutes")})
        per_to[c["to"]] = per_to.get(c["to"], 0) + 1
        made += 1
        print(f"  + {c['to']}（{c['source']}，{d['length']}）{opts[0]['text'][:70]}")
    if not a.dry_run:
        st["seen"] = {k: v for k, v in seen.items() if v >= (now - timedelta(days=7)).date().isoformat()}
        cg._atomic_write(_dir() / "_state.json", st)
        cg._atomic_write(_queue_path(day), q)
        clear_inbox([u for u in processed if any(u == c["url"] and c["source"] == "inbox" for c in fresh)])
    for x in log:
        print(f"  ! {x}")
    if not cands:
        print("  ! 没有候选帖：没配 X_BEARER_TOKEN 时，往 outputs/x-replies/inbox.md 丢推文链接")
        if not os.environ.get("X_BEARER_TOKEN") and not a.dry_run and not getattr(a, "quiet", False):
            # 没有 API：到点提醒人去列表里挑帖，挑好用 inbox add 丢进来就会马上起草
            _notify(f"该回复了：本时段可回 {quota} 条。打开 X 列表挑几条，把链接发给 Easel")
            lst = os.environ.get("X_REPLY_LIST_URL", "")
            if lst.startswith("https://x.com/") and sys.platform == "darwin" and not os.environ.get("EASEL_NO_NOTIFY"):
                subprocess.run(["open", lst], capture_output=True)
    pending = sum(1 for it in q["items"] if it["status"] == "pending")
    if made and not a.dry_run:
        _notify(f"新起草 {made} 条回复，待发 {pending} 条。运行 x_auto.py review 逐条确认")
    return 0


# --------------------------------------------------------------------------- #
# watchlist / inbox
# --------------------------------------------------------------------------- #
WATCH_ROW = re.compile(r"^\|\s*(★?)\s*\|(.*?)\[@([A-Za-z0-9_]{1,15})\]\(https://x\.com/[^)]*\)\s*\|\s*(.*?)\s*\|\s*$")


def parse_watchlist(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        m = WATCH_ROW.match(line.strip())
        if m:
            name = re.sub(r"[*·]", "", m.group(2)).strip()
            out.append({"handle": xr._norm(m.group(3)), "tier": "core" if m.group(1) else "normal",
                        "topic": m.group(4), "note": name})
    return out


def cmd_watchlist(a) -> int:
    f = Path(a.file) if a.file else _dir() / "watchlist.md"
    if not f.is_file():
        sys.exit(f"错误：找不到 {f}")
    rows = parse_watchlist(f.read_text(encoding="utf-8"))
    if not rows:
        sys.exit("错误：表里没解析出账号（每行要有 [@handle](https://x.com/handle)）")
    d = xr.load_targets()
    t = d.setdefault("targets", {})
    added = 0
    for r in rows:
        cur = t.get(r["handle"])
        if cur is None:
            cur, added = {"added": _now().date().isoformat()}, added + 1
        cur.update(tier=r["tier"], topic=r["topic"], note=r["note"])
        t[r["handle"]] = cur
    xr.save_targets(d)
    core = sum(1 for r in rows if r["tier"] == "core")
    print(f"导入 {len(rows)} 个（新增 {added}，core {core}），名单共 {len(t)} 个")
    return 0


def cmd_inbox(a) -> int:
    urls = [u for u in a.urls if xr.STATUS_RE.search(u)]
    if not urls:
        sys.exit("错误：需要推文链接（https://x.com/<用户>/status/<数字>）")
    f = _dir() / "inbox.md"
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        for u in urls:
            fh.write(u.split("?")[0] + "\n" + ((a.text.strip() + "\n") if a.text and len(urls) == 1 else "") + "\n")
    print(f"收件箱 +{len(urls)}")
    if a.no_draft:
        return 0
    # 人挑过的帖要趁热回：不等下一个定时，马上起草（配额按当前时段算，至少给这几条留位）
    ns = argparse.Namespace(slot="auto", force=True, max=None, dry_run=False, profile=None, quiet=True)
    return cmd_run(ns)


# --------------------------------------------------------------------------- #
# queue / review
# --------------------------------------------------------------------------- #
def cmd_queue(a) -> int:
    day = a.date or _now().date().isoformat()
    q = load_queue(day)
    if not q["items"]:
        print(f"{day} 队列为空")
        return 0
    for n, it in enumerate(q["items"], 1):
        print(f"[{n}] {it['status']:<8} {it['to']}  {it['url']}")
        print(f"     原帖：{it['tweet'][:100]!r}")
        for i, o in enumerate(it["options"], 1):
            flag = "" if not o.get("problems") else f"  ⚠ {'; '.join(o['problems'])}"
            print(f"     {i}. ({o['style']}, {dc.x_weighted_len(o['text'])}字) {o['text']}{flag}")
    return 0


def _record(url: str, to: str, file: str) -> bool:
    r = subprocess.run([sys.executable, str(HERE.parent / "x_reply.py"), "record", "--url", url, "--to", to,
                        "--file", str(_root() / file)], capture_output=True, text=True,
                       env=dict(os.environ, EASEL_ROOT=str(_root())))
    if r.returncode != 0:
        print(r.stderr or r.stdout)
    return r.returncode == 0


def cmd_review(a) -> int:
    day = a.date or _now().date().isoformat()
    q = load_queue(day)
    pend = [it for it in q["items"] if it["status"] == "pending"]
    if not pend:
        print("没有待发的回复")
        return 0
    print(f"{len(pend)} 条待发。每条：1/2 选稿，e 选 1 并先改文件，s 跳过，q 退出\n")
    for it in pend:
        print(f"── {it['to']}  {it['url']}\n原帖：{it['tweet'][:300]}\n")
        for i, o in enumerate(it["options"], 1):
            print(f"  {i}. [{o['style']}] {o['text']}")
        ch = input("> ").strip().lower()
        if ch == "q":
            break
        if ch == "s":
            it["status"] = "skipped"
            continue
        o = it["options"][1 if ch == "2" and len(it["options"]) > 1 else 0]
        path = _root() / o["file"]
        if ch == "e":
            subprocess.run([os.environ.get("EDITOR", "nano"), str(path)])
        while True:
            r = xr.check_reply(path.read_text(encoding="utf-8").strip(), it["to"], _now())
            if r["verdict"] != "wait" or not r.get("next_allowed_at"):
                break
            wait_s = (_parse_time(r["next_allowed_at"]) - _now()).total_seconds()
            if wait_s > 600:
                break
            print(f"  … {r['wait'][0]}，{int(wait_s)} 秒后继续")
            time.sleep(max(1, wait_s) + 5)
        if r["verdict"] != "ok":
            for x in r["block"] + r["problems"] + r["wait"]:
                print(f"  ✗ {x}")
            if r["verdict"] in ("wait", "block"):
                print("  本轮先停在这里" if r["verdict"] == "wait" else "  这条不能发，跳过")
                if r["verdict"] == "block":
                    it["status"] = "blocked"
                    continue
                break
            continue
        url = "https://x.com/intent/post?" + urllib.parse.urlencode(
            {"in_reply_to": _sid(it["url"]), "text": path.read_text(encoding="utf-8").strip()})
        webbrowser.open(url)
        if input("  在浏览器里看一眼再点 Reply。发出去了吗？[y/N] ").strip().lower() == "y":
            if _record(it["url"], it["to"], o["file"]):
                it["status"], it["sent_file"] = "sent", o["file"]
                print("  ✓ 已登记")
        cg._atomic_write(_queue_path(day), q)
    cg._atomic_write(_queue_path(day), q)
    return 0


# --------------------------------------------------------------------------- #
# config / schedule
# --------------------------------------------------------------------------- #
def cmd_check(_a) -> int:
    load_env()
    print(f"DEEPSEEK_API_KEY  {_mask(os.environ.get('DEEPSEEK_API_KEY', ''))}")
    print(f"DEEPSEEK_API_BASE {os.environ.get('DEEPSEEK_API_BASE', 'https://api.deepseek.com/v1（默认）')}")
    print(f"DEEPSEEK_MODEL    {os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat（默认）')}")
    print(f"X_BEARER_TOKEN    {_mask(os.environ.get('X_BEARER_TOKEN', ''))}"
          + ("" if os.environ.get("X_BEARER_TOKEN") else "（可选；不配就只处理收件箱）"))
    _, af, _ = xr._paths()
    acc = cg.load_accounts(af).get("x") or {}
    print(f"X 账号            {acc.get('handle') or '未登记 handle'}，注册 {acc.get('created') or '未登记'}")
    print(f"目标名单          {len(xr.load_targets().get('targets', {}))} 个")
    print(f"定时任务          {'已安装' if PLIST.is_file() else '未安装（x_auto.py install）'}")
    return 0 if os.environ.get("DEEPSEEK_API_KEY") else 2


def _plist(python: str) -> str:
    times = "".join(f"<dict><key>Hour</key><integer>{h}</integer><key>Minute</key><integer>{m}</integer></dict>"
                    for h, m in RUN_TIMES)
    logs = _dir() / "_logs"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>{LABEL}</string>
<key>ProgramArguments</key><array><string>{python}</string><string>{HERE}</string><string>run</string></array>
<key>WorkingDirectory</key><string>{_root()}</string>
<key>StartCalendarInterval</key><array>{times}</array>
<key>StandardOutPath</key><string>{logs}/run.log</string>
<key>StandardErrorPath</key><string>{logs}/run.err.log</string>
<key>RunAtLoad</key><false/>
</dict></plist>
"""


def cmd_install(a) -> int:
    if sys.platform != "darwin":
        print("非 macOS：用 cron，例如\n" + "\n".join(
            f"{m} {h} * * * cd {_root()} && {a.python or sys.executable} {HERE} run" for h, m in RUN_TIMES))
        return 0
    (_dir() / "_logs").mkdir(parents=True, exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    PLIST.write_text(_plist(a.python or sys.executable), encoding="utf-8")
    subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
    r = subprocess.run(["launchctl", "load", str(PLIST)], capture_output=True, text=True)
    print(r.stderr.strip() or f"已安装：每天 {', '.join(f'{h:02d}:{m:02d}' for h, m in RUN_TIMES)} 自动起草；日志 {_dir() / '_logs'}")
    return r.returncode


def cmd_uninstall(_a) -> int:
    if PLIST.is_file():
        subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
        PLIST.unlink()
    print("已卸载定时任务")
    return 0


def cmd_status(_a) -> int:
    r = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    line = next((x for x in r.stdout.splitlines() if LABEL in x), "")
    print(f"定时任务：{'运行中 ' + line if line else ('已写入但未加载' if PLIST.is_file() else '未安装')}")
    log = _dir() / "_logs" / "run.log"
    if log.is_file():
        print("最近日志：\n" + "\n".join(log.read_text(encoding="utf-8").splitlines()[-8:]))
    return 0


# --------------------------------------------------------------------------- #
# selftest（不联网：DeepSeek 和 oEmbed 都用假的）
# --------------------------------------------------------------------------- #
def cmd_selftest(_a) -> int:
    import tempfile
    global deepseek, oembed_text
    ok = True

    def case(name, cond):
        nonlocal ok
        print(f"  {'✓' if cond else '✗'} {name}")
        ok &= bool(cond)

    calls = []

    def fake_deepseek(messages, temperature=1.0):
        calls.append(messages)
        if "giveaway" in messages[1]["content"]:
            return {"skip": True, "reason": "giveaway"}
        if len(calls) == 2:   # 第一次给一条坏稿，看会不会带意见重写
            return {"skip": False, "options": [{"style": "x", "text": "Great point! So true 🔥"},
                                               {"style": "y", "text": "Did you pin the model version? Evals moved 6 points after an update."}]}
        pool = [("Tests between steps or only at the end? That decides most of it.",
                 "Renames across services still break, string imports never get caught."),
                ("Which repo size? Under 10k lines it works, monorepos are the pain.",
                 "Did you fence off generated code? That's where these go sideways.")]
        a, b = pool[len(calls) % 2]
        return {"skip": False, "options": [{"style": "precise_question", "text": a},
                                           {"style": "disagree_with_reason", "text": b}]}

    deepseek, oembed_text = fake_deepseek, (lambda url: "Agents are finally good enough for real refactors.")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ.update(EASEL_ROOT=tmp, EASEL_CADENCE_NOW="2026-10-12T09:00:00+08:00", EASEL_NO_NOTIFY="1")
        os.environ.pop("X_BEARER_TOKEN", None)
        _, af, _ = xr._paths()
        cg._atomic_write(af, {"x": {"created": "2026-10-10", "handle": "@me"}})
        xr.save_targets({"targets": {"@alice": {"tier": "core"}}})
        (_dir()).mkdir(parents=True, exist_ok=True)
        (_dir() / "inbox.md").write_text(
            "https://x.com/alice/status/111\n\nhttps://x.com/bob/status/222\nBig giveaway! RT to win\n"
            "https://x.com/carol/status/333\n", encoding="utf-8")
        now = _now()
        quota, idx, _ = slot_quota(now, "auto", False)
        case("早上时段配额 = 剩余量 / 3 个时段", idx == 0 and quota == math.ceil(10 / 3))
        ns = argparse.Namespace(slot="auto", force=False, max=None, dry_run=False, profile=None)
        cmd_run(ns)
        q = load_queue(now.date().isoformat())
        tos = [it["to"] for it in q["items"]]
        case("收件箱里的帖起草进队列，抽奖帖跳过", tos == ["@alice", "@carol"])
        case("坏稿带意见重写过一次", any("Fix these" in m[-1]["content"] for m in calls if m[-1]["role"] == "user"))
        case("每条 2 个备选且文件已写", all(len(it["options"]) == 2 and (_root() / it["options"][0]["file"]).is_file()
                                       for it in q["items"]))
        case("处理过的链接移出收件箱", "status/111" not in (_dir() / "inbox.md").read_text(encoding="utf-8"))
        n = len(calls)
        (_dir() / "inbox.md").write_text("https://x.com/alice/status/111\n", encoding="utf-8")
        cmd_run(ns)
        case("同一条帖不会重复起草", len(calls) == n)
        item = q["items"][0]
        case("登记成功", _record(item["url"], item["to"], item["options"][0]["file"]))
        case("登记后今日已回 1 条", xr.build_today(_now())["done_today"] == 1)
        case("plist 含三个时段", _plist("/usr/bin/python3").count("<key>Hour</key>") == 3)
    print("selftest", "通过" if ok else "失败")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="X 回复任务自动运行（DeepSeek 起草，人点发送）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").set_defaults(func=cmd_check)
    w = sub.add_parser("watchlist")
    w.add_argument("action", choices=("import",))
    w.add_argument("--file")
    w.set_defaults(func=cmd_watchlist)
    ib = sub.add_parser("inbox")
    ib.add_argument("action", choices=("add",))
    ib.add_argument("urls", nargs="+")
    ib.add_argument("--text")
    ib.add_argument("--no-draft", action="store_true")
    ib.set_defaults(func=cmd_inbox)
    r = sub.add_parser("run")
    r.add_argument("--slot", default="auto", choices=("auto", "0", "1", "2"))
    r.add_argument("--force", action="store_true", help="过了最后一个时段也起草")
    r.add_argument("--max", type=int)
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--profile")
    r.set_defaults(func=cmd_run)
    for name, fn in (("queue", cmd_queue), ("review", cmd_review)):
        p = sub.add_parser(name)
        p.add_argument("--date")
        p.set_defaults(func=fn)
    i = sub.add_parser("install")
    i.add_argument("--python")
    i.set_defaults(func=cmd_install)
    sub.add_parser("uninstall").set_defaults(func=cmd_uninstall)
    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("selftest").set_defaults(func=cmd_selftest)
    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
