#!/usr/bin/env python3
"""global_topics.py — 海外 AI / 游戏选题雷达（读 WorkBuddy 每日热点清单，免费）.

需求侧数据来自 WorkBuddy 仓库每天北京时间 06:30 自动更新的 data/hot/latest.json
（80+ 公开源跨平台聚类：HN、Product Hunt、TechCrunch、Google News AI、量子位、IT 之家……）。
优先读本机的 WorkBuddy 副本，读不到再拉 GitHub raw。只读、不扣费、不搬运正文。

用法:
  python global_topics.py ai     [--n 15] [--lang en|zh|all] [--hot-only] [--keyword agent,claude]
  python global_topics.py gaming [--n 15]          # 用游戏关键词从全部分组里筛（给 Reddit 用）
  python global_topics.py groups                   # 看清单里有哪些分组、各多少条
  python global_topics.py subreddit --sub pcgaming,Games [--n 10] [--t day|week]
                                                   # 读版块公开热帖（只读、限速、不登录），看这个版现在在聊什么
  --source PATH_OR_URL  指定清单位置；--json 输出机器可读

交付格式：每条 = 标题 / 来源 / 几个平台在聊 / 时间 / 链接。选题由人定；写的时候至少 15% 独家。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve()
PROJECT_ROOT = Path(os.environ.get("EASEL_ROOT") or HERE.parents[4])
LOCAL_CANDIDATES = [
    Path(os.environ["EASEL_HOT_FEED"]) if os.environ.get("EASEL_HOT_FEED") else None,
    PROJECT_ROOT.parent / "WorkBuddy" / "data" / "hot" / "latest.json",
]
REMOTE = "https://raw.githubusercontent.com/adsorgcn/WorkBuddy/main/data/hot/latest.json"

AI_GROUPS = ("AI", "海外", "产品", "科技")
GAMING_KEYWORDS = (
    "game", "gaming", "steam", "nintendo", "switch 2", "playstation", "ps5", "xbox", "valve", "epic games",
    "esports", "indie", "gta", "elden", "zelda", "pokemon", "minecraft", "roblox", "hollow knight", "silksong",
    "游戏发售", "新游", "主机", "任天堂", "索尼", "米哈游", "原神", "黑神话", "电竞", "独立游戏", "手游",
)


def load_feed(source: str | None) -> dict:
    if source and source.startswith("http"):
        cands, remote = [], source
    elif source:
        cands, remote = [Path(source)], None
    else:
        cands, remote = [p for p in LOCAL_CANDIDATES if p], REMOTE
    for p in cands:
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    if remote:
        try:
            with urllib.request.urlopen(remote, timeout=20) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001
            sys.exit(f"错误：读不到热点清单（{e}）。可 git clone WorkBuddy 到本项目同级目录，或用 --source 指定。")
    sys.exit("错误：找不到热点清单文件")


def all_items(feed: dict) -> list[dict]:
    items = []
    for g, lst in (feed.get("groups") or {}).items():
        for it in lst:
            it = dict(it)
            it.setdefault("group", g)
            items.append(it)
    return items


def _match(it: dict, kws) -> bool:
    blob = " ".join([it.get("title", "")] + [m.get("title", "") for m in it.get("members", [])]).lower()
    return any(k.lower() in blob for k in kws)


def pick(items, groups=None, kws=None, lang="all", hot_only=False, n=15):
    out = []
    seen = set()
    for it in items:
        if groups and it.get("group") not in groups:
            continue
        if kws and not _match(it, kws):
            continue
        if lang != "all" and it.get("lang") != lang:
            continue
        if hot_only and int(it.get("platforms") or 1) < 2:
            continue
        key = it.get("title", "")[:40]
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    out.sort(key=lambda x: (-int(x.get("platforms") or 1), x.get("time", "")), reverse=False)
    return out[:n]


def show(rows, feed, as_json):
    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    print(f"# 清单日期 {feed.get('date')}（生成于 {feed.get('generated_at', '?')}）共 {len(rows)} 条\n")
    for i, it in enumerate(rows, 1):
        srcs = "、".join(it.get("sources") or [it.get("source", "")])
        print(f"{i:>2}. [{it.get('group')}] {it.get('title')}")
        print(f"    {it.get('platforms', 1)} 个平台在聊：{srcs} · {it.get('time', '')} · {it.get('lang', '')}")
        print(f"    {it.get('url', '')}")


def subreddit_top(subs: list[str], n: int, t: str) -> list[dict]:
    """Reddit 公开 JSON：只读热帖标题/分数/评论数，用来摸版块口味，不抓正文、不批量。"""
    import time
    rows = []
    for sub in subs:
        sub = sub.strip().removeprefix("r/")
        url = f"https://www.reddit.com/r/{sub}/top.json?t={t}&limit={n}"
        req = urllib.request.Request(url, headers={"User-Agent": "easel-topic-radar/0.1 (read-only)"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001
            print(f"  r/{sub} 读取失败：{e}", file=sys.stderr)
            continue
        for c in data.get("data", {}).get("children", []):
            d = c.get("data", {})
            rows.append({"group": f"r/{sub}", "title": d.get("title", ""), "platforms": 1,
                         "sources": [f"score {d.get('score')} · {d.get('num_comments')} comments · "
                                     f"flair {d.get('link_flair_text') or '-'} · {'self' if d.get('is_self') else 'link'}"],
                         "time": "", "lang": "en", "url": "https://www.reddit.com" + d.get("permalink", "")})
        time.sleep(2)   # 礼貌间隔
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="海外 AI / 游戏选题雷达（读 WorkBuddy 热点清单）")
    ap.add_argument("mode", choices=("ai", "gaming", "groups", "subreddit"))
    ap.add_argument("--sub", default="pcgaming,Games,patientgamers", help="subreddit 模式：逗号分隔")
    ap.add_argument("--t", choices=("day", "week", "month"), default="week")
    ap.add_argument("--n", type=int, default=15)
    ap.add_argument("--lang", choices=("en", "zh", "all"), default="all")
    ap.add_argument("--hot-only", action="store_true", help="只要 ≥2 个平台同时在聊的")
    ap.add_argument("--keyword", help="逗号分隔，再按关键词过滤")
    ap.add_argument("--source")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.mode == "subreddit":
        rows = subreddit_top(a.sub.split(","), a.n, a.t)
        show(rows, {"date": "live", "generated_at": "reddit"}, a.json)
        return 0
    feed = load_feed(a.source)
    items = all_items(feed)
    if a.mode == "groups":
        for g, lst in (feed.get("groups") or {}).items():
            print(f"  {g}: {len(lst)}")
        return 0
    kws = [k.strip() for k in a.keyword.split(",")] if a.keyword else None
    if a.mode == "ai":
        rows = pick(items, AI_GROUPS, kws, a.lang, a.hot_only, a.n)
    else:
        rows = pick(items, None, kws or GAMING_KEYWORDS, a.lang, a.hot_only, a.n)
    show(rows, feed, a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
