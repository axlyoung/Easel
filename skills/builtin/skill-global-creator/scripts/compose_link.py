#!/usr/bin/env python3
"""compose_link.py — 生成“预填好内容的发帖链接”，人点开、看一眼、自己按发布.

新号阶段 X / LinkedIn / Reddit 一律人手发：浏览器自动化和第三方 API 发帖是新号被判
“自动化/不真实行为”的头号原因。这里只把定稿塞进各平台官方的分享/发帖入口，
最后那一下永远是人点。

  python compose_link.py x        --file post.md          # 单条推文（串推请逐条发：用 --index 取第 N 条）
  python compose_link.py x        --file thread.md --index 2
  python compose_link.py linkedin --file post.md
  python compose_link.py reddit   --file post.md --sub pcgaming --title "..."
  可加 --open 直接用默认浏览器打开。

发帖前务必已跑过：deai_check.py check --mode publish、content_guard.py scan、cadence_gate.py check。
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
import webbrowser
from pathlib import Path


def split_thread(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"^\s*---\s*$", text, flags=re.M) if p.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description="生成预填内容的官方发帖链接（人手发布）")
    ap.add_argument("platform", choices=("x", "linkedin", "reddit"))
    ap.add_argument("--file", required=True)
    ap.add_argument("--index", type=int, default=1, help="X 串推取第几条（1 起）")
    ap.add_argument("--sub", help="Reddit 版名")
    ap.add_argument("--title", help="Reddit 标题")
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args()

    text = Path(a.file).read_text(encoding="utf-8").strip()
    if a.platform == "x":
        posts = split_thread(text)
        if not 1 <= a.index <= len(posts):
            sys.exit(f"错误：只有 {len(posts)} 条")
        body = posts[a.index - 1]
        url = "https://x.com/intent/post?" + urllib.parse.urlencode({"text": body})
        if len(posts) > 1:
            print(f"串推共 {len(posts)} 条：发完第 1 条后，其余在该推下面点“回复”逐条贴（或在 X 里用 + 号组串推）。")
    elif a.platform == "linkedin":
        url = "https://www.linkedin.com/feed/?" + urllib.parse.urlencode({"shareActive": "true", "text": text})
    else:
        if not a.sub or not a.title:
            sys.exit("错误：reddit 需要 --sub 和 --title")
        sub = a.sub[2:] if a.sub.startswith("r/") else a.sub
        url = f"https://www.reddit.com/r/{sub}/submit?" + urllib.parse.urlencode(
            {"type": "TEXT", "title": a.title, "text": text})
        print(f"提交前在页面上选好 flair，并再看一眼 r/{sub} 的版规侧栏。")
    print(url)
    if a.open:
        webbrowser.open(url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
