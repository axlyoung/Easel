#!/usr/bin/env python3
"""x_news.py — 每天从各媒体热点里挑 AI 资讯，DeepSeek 写成一条有观点的短评，进 X 发帖队列.

内容配比：资讯点评（本脚本，自动）+ 个人实战（用户的真实经历，人给素材）。
资讯来自 WorkBuddy 每日热点清单（80+ 源跨平台聚类，GitHub 上每天早上更新）。

防编造：
  - 只许用标题里写到的事实；短评里出现的数字必须在来源标题里出现过，否则判不过
  - 不许写“我测了/我用了”这类亲身经历（没有素材）
  - 去AI自查（X 规则）不过就带意见重写一次，还不过就丢
来源链接不进正文，发帖后自动挂在第一条回复里（起步期正文不放外链）。

子命令:
  run [--n 1] [--dry-run] [--hours 30]     挑题 + 起草 + 进队列（默认草稿等人审；.env 设 X_AUTO_APPROVE=1 直接排队）
  pick [--n 8]                              只看今天能挑的题
  install / uninstall                      macOS launchd：每天 19:30 跑一次 run
  selftest
"""
from __future__ import annotations

import argparse
import html as _html
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1].parent / "skill-x-reply" / "scripts"))

import x_post as xp  # noqa: E402
import x_auto as xa  # noqa: E402  (复用 DeepSeek 调用与“没素材不写亲身经历”的规则)

cg, dc = xp.cg, xp.dc
REMOTE = "https://raw.githubusercontent.com/adsorgcn/WorkBuddy/main/data/hot/latest.json"
LOCAL = HERE.parents[4].parent / "WorkBuddy" / "data" / "hot" / "latest.json"
GROUPS = ("AI", "海外", "产品", "科技")
LABEL = "com.easel.x-news"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
# 和 AI 号定位无关、或容易翻车的题
SKIP_RE = re.compile(r"(election|trump|biden|war|killed|shooting|lawsuit settlement|stock price|股价|涨停|跌停|"
                     r"去世|遇难|战争|大选|彩票|赌|crypto|bitcoin|比特币|nft|sext|porn|色情)", re.I)

SYSTEM = """You write one short X post for a backend Java developer who covers AI. English only.

Rules:
- One point. A take, not a summary: a concrete consequence, trade-off, or thing a developer should check because of this.
  Generic lines are banned: "more competition is good", "one to watch", "worth weighing/watching", "exciting times",
  "big step", "this changes everything".
- Use ONLY facts stated in the headlines and article text below. Do not add numbers, names, dates or claims not in them.
- No first-person experience ("I tried", "I tested", "in my team"): there is no material for that.
- Short: {lo}-{hi} characters. One or two sentences. Plain words, contractions ok.
- No hashtags, no emoji, no links, no @mentions, no em dashes, no "game-changer/revolutionary/delve/landscape",
  no lists of three, no "it's not X, it's Y", no question aimed at everyone.
- If the story is not about AI, is politics/tragedy/finance gossip, or there is nothing worth saying, set "skip": true.

Return JSON: {{"skip": bool, "reason": "short", "text": "..."}}"""


def _now() -> datetime:
    return cg._now()


def _state_file() -> Path:
    return xp._root() / "outputs" / "_analytics" / "x-news-state.json"


def load_feed() -> dict:
    """先拉 GitHub 当天的，拉不到再用本地 WorkBuddy 克隆（可能是旧的）。"""
    try:
        with urllib.request.urlopen(REMOTE, timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception:  # noqa: BLE001
        if LOCAL.is_file():
            return json.loads(LOCAL.read_text(encoding="utf-8"))
        raise RuntimeError("读不到热点清单（GitHub 和本地 WorkBuddy 都没有）")


def _items(feed: dict) -> list[dict]:
    out = []
    for g, lst in (feed.get("groups") or {}).items():
        for it in lst:
            out.append({**it, "group": it.get("group") or g})
    return out


def _parse_time(s: str, year: int) -> datetime | None:
    m = re.match(r"^(\d{2})-(\d{2}) (\d{2}):(\d{2})$", s or "")
    if not m:
        return None
    return datetime(year, int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))).astimezone()


def candidates(feed: dict, hours: int, used: set[str]) -> list[dict]:
    now = _now()
    rows = []
    for it in _items(feed):
        title = it.get("title", "")
        if it.get("group") not in GROUPS or not title or SKIP_RE.search(title):
            continue
        key = (it.get("url") or title)[:200]
        if key in used:
            continue
        t = _parse_time(it.get("time", ""), now.year)
        if t and now - t > timedelta(hours=hours):
            continue
        blob = " ".join([title] + [m.get("title", "") for m in it.get("members", [])])
        if it.get("group") != "AI" and not re.search(r"\b(ai|llm|gpt|claude|gemini|agent|model|openai|anthropic|"
                                                      r"deepseek|copilot|cursor)\b|人工智能|大模型|智能体", blob, re.I):
            continue
        rows.append({**it, "_key": key, "_blob": blob})
    # 多平台同聊的优先，其次英文（账号写英文），再次越新越好
    rows.sort(key=lambda r: (-int(r.get("platforms") or 1), r.get("lang") != "en", r.get("time", "")), reverse=False)
    return rows


def _numbers_ok(text: str, blob: str) -> list[str]:
    """短评里的每个数字都要在来源标题里作为完整数字出现过（"1M" 不能靠 "6.1" 里的 1 蒙混过关）。"""
    num = r"\d+(?:[.,]\d+)?"
    have = set(re.findall(num, blob))
    return [n for n in re.findall(num, text) if n not in have]


GENERIC_RE = re.compile(r"(good for (everyone|anyone|devs|developers)|more competition|one to watch|"
                        r"worth (watching|weighing|keeping an eye)|exciting (times|news)|big step|changes everything|"
                        r"remains to be seen|time will tell)", re.I)
STOP = {"The", "This", "That", "With", "From", "Says", "After", "Into", "About", "What", "When", "How", "Why",
        "Report", "Reportedly", "New", "First", "Its", "Their", "Will", "Now", "Just"}


def story_tokens(blob: str) -> set[str]:
    """一条新闻的“身份”：标题里的专有名词（大写开头的英文词、≥3 字母）。中英文版共享这些词。"""
    return {w for w in re.findall(r"\b[A-Z][A-Za-z0-9.+-]{2,}\b", blob) if w not in STOP}


def same_story(a: set[str], b: set[str]) -> bool:
    return len(a & b) >= 2 or (bool(a) and a == b)


def article_text(url: str, limit: int = 1500) -> str:
    """抓原文页的描述和前几段（只用来补事实，不转载）。抓不到返回空。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (easel-x-news)"})
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read(600_000).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""
    parts = re.findall(r'<meta[^>]+(?:name|property)="(?:og:)?description"[^>]+content="([^"]{20,})"', raw, re.I)
    for ptxt in re.findall(r"<p[^>]*>(.*?)</p>", raw, re.S | re.I)[:12]:
        t = re.sub(r"<[^>]+>", "", ptxt).strip()
        if len(t) > 60:
            parts.append(t)
    text = _html.unescape(" ".join(dict.fromkeys(p.strip() for p in parts)))
    return re.sub(r"\s+", " ", text)[:limit]


def _best_url(it: dict) -> str:
    """优先英文媒体原文（TechCrunch/Wired/The Verge…），再退回聚合页。"""
    urls = [(it.get("lang"), it.get("url"))] + [(None, m.get("url")) for m in it.get("members", [])]
    for _, u in urls:
        if u and re.search(r"techcrunch|theverge|wired|arstechnica|reuters|bloomberg|venturebeat|technologyreview|"
                           r"openai\.com|anthropic\.com|blog\.google|github\.blog", u):
            return u
    return it.get("url") or ""


def draft(it: dict, used_texts: list[str]) -> dict:
    lo, hi = (70, 170)
    heads = "\n".join(f"- {t}" for t in [it["title"]] + [m.get("title", "") for m in it.get("members", [])][:4] if t)
    body = it.get("_article") or ""
    it["_blob"] = it["_blob"] + " " + body
    msgs = [{"role": "system", "content": SYSTEM.format(lo=lo, hi=hi)},
            {"role": "user", "content": f"Headlines (source: {it.get('source', '')}):\n{heads}"
                                        + (f"\n\nArticle text:\n{body}" if body else "")}]
    out = xa.deepseek(msgs, temperature=0.9)
    for attempt in range(2):
        if out.get("skip"):
            return {"skip": True, "reason": out.get("reason", "")}
        text = (out.get("text") or "").strip().strip('"')
        probs = []
        r = dc.run_checks(text, "x", "en", "", "publish")
        probs += [f"{i['key']}: {i['detail']}" for i in r["items"] if i["status"] in ("fail",) or
                  (i["status"] == "warn" and i["key"] in ("rule_of_three", "x_brevity"))]
        if GENERIC_RE.search(text):
            probs.append(f"generic filler: '{GENERIC_RE.search(text).group(0)}', say something specific")
        if xa.FIRST_PERSON.search(text):
            probs.append("no first-person experience")
        bad = _numbers_ok(text, it["_blob"])
        if bad:
            probs.append(f"numbers not in the headlines: {', '.join(bad)}")
        n = dc.x_weighted_len(text)
        if not (lo * 0.6 <= n <= 200):
            probs.append(f"length {n}, want {lo}-{hi}")
        if "—" in text:
            probs.append("em dash")
        for prev in used_texts:
            import difflib
            if difflib.SequenceMatcher(None, text.lower(), prev.lower()).ratio() > 0.6:
                probs.append("too similar to a recent post")
                break
        if not probs:
            return {"skip": False, "text": text}
        if attempt == 1:
            return {"skip": True, "reason": "两次都没过检：" + "; ".join(probs[:2])}
        msgs += [{"role": "assistant", "content": json.dumps(out, ensure_ascii=False)},
                 {"role": "user", "content": "Fix and return the same JSON: " + "; ".join(probs)}]
        out = xa.deepseek(msgs, temperature=0.8)
    return {"skip": True, "reason": "没生成出可用稿"}


def cmd_pick(a) -> int:
    st = cg._load_json(_state_file(), {"used": {}})
    rows = candidates(load_feed(), a.hours, set(st["used"]))
    for r in rows[:a.n]:
        print(f"[{r.get('platforms', 1)} 平台] {r['title'][:90]} | {r.get('source', '')} | {r.get('time', '')}")
    if not rows:
        print("今天没有合适的 AI 资讯")
    return 0


def cmd_run(a) -> int:
    xp.load_env()
    st = cg._load_json(_state_file(), {"used": {}})
    st.setdefault("stories", [])
    feed = load_feed()
    rows = candidates(feed, a.hours, set(st["used"]))
    done_stories = [set(s["tokens"]) for s in st["stories"]]
    q = xp.load_queue()
    recent = [i["text"] for i in q["items"]][-30:]
    auto = os.environ.get("X_AUTO_APPROVE") == "1"
    made = 0
    for it in rows:
        if made >= a.n:
            break
        toks = story_tokens(it["_blob"])
        if any(same_story(toks, s) for s in done_stories):
            st["used"][it["_key"]] = _now().date().isoformat()
            continue
        st["used"][it["_key"]] = _now().date().isoformat()
        done_stories.append(toks)
        st["stories"].append({"tokens": sorted(toks), "date": _now().date().isoformat()})
        src = _best_url(it)
        it["_article"] = article_text(src) if src and not a.dry_run else ""
        if a.dry_run:
            print(f"  · 会起草：{it['title'][:80]}")
            made += 1
            continue
        try:
            d = draft(it, recent)
        except RuntimeError as e:
            print(f"  ! {e}")
            break
        if d.get("skip"):
            print(f"  - 跳过：{it['title'][:60]}（{d.get('reason', '')}）")
            continue
        item = xp.add_item(d["text"], None, src or it.get("url"), "news", auto,
                           meta={"headline": it["title"], "source": it.get("source", "")})
        recent.append(d["text"])
        made += 1
        print(f"  + #{item['id']} {'已排 ' + item['at'] if auto else '待审'}：{d['text']}")
        print(f"    来源：{it['title'][:80]}（{it.get('source', '')}）")
    if not a.dry_run:
        cutoff = (_now() - timedelta(days=10)).date().isoformat()
        st["used"] = {k: v for k, v in st["used"].items() if v >= cutoff}
        st["stories"] = [s for s in st["stories"] if s["date"] >= (_now() - timedelta(days=4)).date().isoformat()]
        cg._atomic_write(_state_file(), st)
        if made and not auto and sys.platform == "darwin" and not os.environ.get("EASEL_NO_NOTIFY"):
            subprocess.run(["osascript", "-e", f'display notification "今天的 AI 资讯短评写好了 {made} 条，等你审" '
                                               'with title "X 发帖"'], capture_output=True)
    if not rows:
        print("今天没有合适的 AI 资讯")
    return 0


def cmd_install(a) -> int:
    py = a.python or sys.executable
    logs = xp._root() / "outputs" / "_logs"
    logs.mkdir(parents=True, exist_ok=True)
    PLIST.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>{LABEL}</string>
<key>ProgramArguments</key><array><string>{py}</string><string>{HERE}</string><string>run</string></array>
<key>WorkingDirectory</key><string>{xp._root()}</string>
<key>StartCalendarInterval</key><dict><key>Hour</key><integer>19</integer><key>Minute</key><integer>30</integer></dict>
<key>StandardOutPath</key><string>{logs}/x-news.log</string>
<key>StandardErrorPath</key><string>{logs}/x-news.err.log</string>
</dict></plist>
""", encoding="utf-8")
    subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
    r = subprocess.run(["launchctl", "load", str(PLIST)], capture_output=True, text=True)
    print(r.stderr.strip() or "已安装：每天 19:30 挑 AI 资讯写短评，进发帖队列")
    return r.returncode


def cmd_uninstall(_a) -> int:
    if PLIST.is_file():
        subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
        PLIST.unlink()
    print("已卸载")
    return 0


def cmd_selftest(_a) -> int:
    import tempfile
    ok = True

    def case(name, cond):
        nonlocal ok
        print(f"  {'✓' if cond else '✗'} {name}")
        ok &= bool(cond)

    feed = {"groups": {"AI": [
        {"title": "OpenAI ships GPT-6.1 with 500k context in Codex", "url": "https://e.com/a", "platforms": 3,
         "lang": "en", "time": "10-14 08:00", "source": "TechCrunch"},
        {"title": "Election polls tighten", "url": "https://e.com/b", "platforms": 5, "lang": "en", "time": "10-14 08:00"}],
        "产品": [{"title": "New phone case colors", "url": "https://e.com/c", "platforms": 2, "time": "10-14 08:00"}]}}
    with tempfile.TemporaryDirectory() as tmp:
        os.environ.update(EASEL_ROOT=tmp, EASEL_CADENCE_NOW="2026-10-14T19:30:00+08:00", EASEL_NO_NOTIFY="1")
        rows = candidates(feed, 30, set())
        case("只留 AI 相关、跳过政治", [r["url"] for r in rows] == ["https://e.com/a"])
        case("编出来的数字被抓", _numbers_ok("Context jumps to 1M tokens", rows[0]["_blob"]) == ["1"])
        case("中英文同一条新闻判为同一件事", same_story(story_tokens("Meta 发布 Muse Wonder 系列前沿模型"),
                                                      story_tokens("Meta releases its first frontier model, Muse Wonder")))
        case("不同新闻不误合并", not same_story(story_tokens("OpenAI ships Codex update"),
                                               story_tokens("OpenAI sued over training data")))
        case("空话被识别", bool(GENERIC_RE.search("More competition at the top is good for anyone shipping AI.")))
        case("来源里有的数字放行", _numbers_ok("500k context in Codex changes code review", rows[0]["_blob"]) == [])
        replies = iter([{"skip": False, "text": "I tested it and context is now 2M tokens, a game-changer."},
                        {"skip": False, "text": "500k context in Codex means whole services fit in one prompt. Review gets harder, not easier."}])
        xa.deepseek = lambda msgs, temperature=1.0: next(replies)
        d = draft(rows[0], [])
        case("坏稿（亲身经历+编数字+AI 腔）重写后通过", not d.get("skip") and d["text"].startswith("500k"))
    print("selftest", "通过" if ok else "失败")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="X 每日 AI 资讯短评")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run"); p.add_argument("--n", type=int, default=1); p.add_argument("--dry-run", action="store_true")
    p.add_argument("--hours", type=int, default=30); p.set_defaults(func=cmd_run)
    p = sub.add_parser("pick"); p.add_argument("--n", type=int, default=8); p.add_argument("--hours", type=int, default=30)
    p.set_defaults(func=cmd_pick)
    p = sub.add_parser("install"); p.add_argument("--python"); p.set_defaults(func=cmd_install)
    sub.add_parser("uninstall").set_defaults(func=cmd_uninstall)
    sub.add_parser("selftest").set_defaults(func=cmd_selftest)
    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
