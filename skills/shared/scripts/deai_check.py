#!/usr/bin/env python3
"""deai_check.py — 去 AI 味确定性自查（中英双语 · 按平台）.

规则来源：WorkBuddy 公众号爆文专家的 deAI 三件套 + 12 项自查（减法删指纹词、加法只标口语位、
反问句、禁长破折号、段落短、五个结构信号），扩展到海外平台 X / LinkedIn / Blogger / Reddit。

LLM 负责改稿；本脚本只负责**数**：指纹词、长破折号、反问句、段落长度、句长起伏、
整齐三点、not-X-but-Y 对照、互动诱导、平台格式（X 280 加权字数、LinkedIn 3000 字、
Reddit 不要 hashtag……）、待补标记 [📝 💬 📊 🖼]。数出来的东西不靠模型心算。

子命令:
  check   --file PATH | --text "..."  [--platform x|linkedin|blogger|reddit|generic]
          [--lang auto|en|zh] [--title "..."] [--mode draft|publish] [--json]
          draft  模式：待补标记只提醒（写作阶段本来就该有）
          publish 模式：待补标记必须清零，否则 fail
  selftest

X 串推：用单独一行 `---` 分隔每条推文，每条单独算 280 加权字数。

退出码：0 通过（可有 warn）；1 有 fail 项，必须改稿；2 参数错误。
纯标准库，不联网，不改文件。
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

PLATFORMS = ("x", "linkedin", "blogger", "reddit", "generic")

# --------------------------------------------------------------------------- #
# 指纹词表（HARD 见到就删；SOFT 单个不罪，扎堆就是 AI）
# --------------------------------------------------------------------------- #
ZH_HARD = [
    "值得注意的是", "需要强调的是", "综上所述", "不言而喻", "毋庸置疑", "显而易见", "至关重要",
    "不可否认", "总而言之", "简而言之", "换句话说", "从某种意义上说", "在这个背景下", "与此同时",
    "在很大程度上", "从本质上讲", "毫无疑问", "希望对你有帮助", "希望对你有所帮助", "谢谢你的分享",
    "让我们一起", "不仅如此", "令人印象深刻", "众所周知", "一言以蔽之", "应运而生", "如火如荼",
    "方兴未艾", "蓬勃发展", "日新月异", "翻天覆地", "前所未有", "不可或缺", "行之有效", "有目共睹",
    "深入浅出", "引人深思", "由此可见", "在一定程度上", "具有重要意义", "发挥着重要作用", "归根结底",
    "随着.{0,12}的发展", "在当今.{0,10}时代", "让我们拭目以待", "未来已来", "拥抱变化",
    "大家好[，,]?今天", "首先[，,].{0,40}其次[，,].{0,40}最后",
]
ZH_SOFT = ["赋能", "抓手", "闭环", "底层逻辑", "颗粒度", "链路", "此外", "另外", "更重要的是",
           "总的来说", "事实上", "本质上", "全方位", "多维度", "深度解析", "干货满满"]

EN_HARD = [
    r"\bdelve[sd]?\b", r"\bdelving\b", r"\btapestry\b", r"\btestament to\b", r"\bit'?s worth noting\b",
    r"\bit is (important|worth|crucial) to note\b", r"\bin conclusion\b", r"\bin summary\b",
    r"\bin today'?s (fast-paced |ever-changing |digital )?(world|landscape|age)\b", r"\bever-evolving\b",
    r"\bfast-paced world\b", r"\bi hope this helps\b", r"\blet'?s dive (in|into)\b", r"\bdive deep\b",
    r"\bgame[- ]changer\b", r"\bnavigat(e|ing) the complexit", r"\bin the realm of\b",
    r"\bunlock(ing)? the (full )?potential\b", r"\bplays? an? (crucial|pivotal|vital|key) role\b",
    r"(^|[.!?]\s+)(moreover|furthermore|additionally),", r"\bembark(ed|ing)? on\b", r"\ba myriad of\b",
    r"\bbuckle up\b", r"\blet that sink in\b", r"\bhere'?s the kicker\b", r"\bi'?m (thrilled|excited|humbled) to\b",
    r"\bwithout further ado\b", r"\bparadigm shift\b", r"\bcutting[- ]edge\b", r"\bharness(ing)? the power\b",
    r"\bseamless(ly)?\b", r"\bthis changes everything\b", r"\bin an era of\b", r"\bin a world where\b",
    r"\bat the end of the day\b", r"\bwhen it comes to\b", r"\bnot only\b.{0,60}\bbut also\b",
    r"\bgreat question\b", r"\bstands as a\b", r"\bserves as a (powerful |stark )?reminder\b",
    r"\bthe future is (here|now)\b", r"\bstay tuned\b", r"\bmind[- ]blowing\b", r"\brevolutioniz(e|ing)\b",
]
EN_SOFT = [
    r"\bleverag(e|es|ed|ing)\b", r"\brobust\b", r"\blandscape\b", r"\bcrucial\b", r"\bpivotal\b",
    r"\bintricate\b", r"\bshowcas(e|es|ing)\b", r"\bcomprehensive\b", r"\belevat(e|es|ing)\b",
    r"\bempower(s|ing)?\b", r"\bstreamlin(e|ed|ing)\b", r"\bnotably\b", r"\binterestingly\b",
    r"\bessentially\b", r"\bultimately\b", r"\bvibrant\b", r"\bmeticulous(ly)?\b", r"\bnuanced\b",
    r"\bholistic\b", r"\bsynerg(y|ies)\b", r"\bfoster(s|ing)?\b", r"\bunderscore[sd]?\b",
    r"\bmultifaceted\b", r"\btransformative\b", r"\binsights?\b", r"\brealm\b", r"\bjourney\b",
    r"\bboasts?\b", r"\bkey takeaways?\b", r"\bdeep dive\b",
]

# 互动诱导：各平台都降权或违规（WorkBuddy：只用疑问句引评论，不引导点赞转发关注）
BAIT = [
    r"\b(like|retweet|repost|share) (and|&) (follow|retweet|share|subscribe)\b", r"\bfollow (me )?for more\b",
    r"\bsmash (that|the) (like|follow)\b", r"\bcomment ['\"]?(yes|me|interested|\w{2,12})['\"]? (below|and i'?ll)\b",
    r"\bdrop an? .{1,12} (below|in the comments)\b", r"\bupvote (this|if)\b", r"\bplease upvote\b",
    r"\btag (a friend|someone)\b", r"\bagree\?\s*$", r"点赞.{0,4}(关注|转发|收藏)", r"一键三连", r"求(点赞|关注|转发)",
]

EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿\U0001F000-\U0001F2FF]")
CJK_RE = re.compile(r"[一-鿿]")
URL_RE = re.compile(r"https?://\S+|www\.\S+")
HASHTAG_RE = re.compile(r"(?<![\w&/])#[A-Za-z一-鿿][\w一-鿿]*")
MD_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s", re.M)
PLACEHOLDER_RE = re.compile(r"\[(📝|💬|📊|🖼)")
EM_DASH_RE = re.compile(r"[—–]")
BULLET_RE = re.compile(r"^\s*([-*•]|\d+[.)])\s+")


@dataclass
class Item:
    key: str
    status: str            # pass | warn | fail
    detail: str
    hits: list = field(default_factory=list)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def detect_lang(text: str) -> str:
    letters = re.findall(r"[A-Za-z]", text)
    cjk = CJK_RE.findall(text)
    return "zh" if len(cjk) >= max(20, len(letters) * 0.15) else "en"


def x_weighted_len(post: str) -> int:
    """X 的加权字数：URL 计 23；CJK/全角/emoji 计 2；其余计 1。"""
    n = 0
    rest = URL_RE.sub("", post)
    n += 23 * len(URL_RE.findall(post))
    for ch in rest:
        cp = ord(ch)
        if (0x1100 <= cp <= 0x115F or 0x2E80 <= cp <= 0xA4CF or 0xAC00 <= cp <= 0xD7A3
                or 0xF900 <= cp <= 0xFAFF or 0xFE30 <= cp <= 0xFE4F or 0xFF00 <= cp <= 0xFF60
                or 0xFFE0 <= cp <= 0xFFE6 or cp >= 0x1F000):
            n += 2
        else:
            n += 1
    return n


def split_paragraphs(text: str) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text)]
    return [p for p in paras if p and p != "---" and not p.startswith("```") and not p.startswith("|")]


def split_sentences(text: str, lang: str) -> list[str]:
    body = re.sub(r"```.*?```", " ", text, flags=re.S)
    body = URL_RE.sub(" ", body)
    if lang == "zh":
        parts = re.split(r"[。！？!?；\n]+", body)
    else:
        parts = re.split(r"(?<=[.!?])\s+|\n+", body)
    return [p.strip() for p in parts if len(p.strip()) > 1]


def unit_len(s: str, lang: str) -> int:
    return len(CJK_RE.findall(s)) + len(re.findall(r"[A-Za-z0-9']+", s)) if lang == "zh" \
        else len(re.findall(r"[A-Za-z0-9']+", s))


def find_all(patterns, text, flags=re.I | re.M) -> list[str]:
    hits = []
    for p in patterns:
        for m in re.finditer(p, text, flags):
            hits.append(m.group(0).strip()[:60])
    return hits


def count_questions(text: str) -> int:
    return len(re.findall(r"[?？](?![\w])", URL_RE.sub("", text)))


# --------------------------------------------------------------------------- #
# checks
# --------------------------------------------------------------------------- #
def run_checks(text: str, platform: str = "generic", lang: str = "auto",
               title: str = "", mode: str = "draft") -> dict:
    if lang == "auto":
        lang = detect_lang(text)
    items: list[Item] = []
    full = (title + "\n\n" + text) if title else text

    # 1 指纹词
    hard = find_all(ZH_HARD if lang == "zh" else EN_HARD, full)
    if lang == "zh":   # 中文稿里夹的英文套话一样算
        hard += find_all(EN_HARD, full)
    soft = find_all(ZH_SOFT if lang == "zh" else EN_SOFT, full)
    items.append(Item("fingerprint_hard", "fail" if hard else "pass",
                      f"{len(hard)} 个硬指纹（整句删比换词好）", hard))
    items.append(Item("fingerprint_soft", "fail" if len(soft) >= 4 else ("warn" if soft else "pass"),
                      f"{len(soft)} 个软指纹（单个不罪，≥4 个扎堆判 AI）", soft))

    # 2 长破折号
    dashes = EM_DASH_RE.findall(full)
    items.append(Item("em_dash", "fail" if dashes else "pass",
                      f"{len(dashes)} 个长破折号（换逗号、句号或冒号）"))

    # 3 反问句 / 问句
    q = count_questions(text)
    words = unit_len(text, lang)
    need_q = {"blogger": 2, "linkedin": 1}.get(platform, 1 if words > 250 else 0)
    if lang == "zh" and platform in ("generic", "blogger"):
        need_q = max(need_q, 2)
    items.append(Item("questions", "pass" if q >= need_q else ("warn" if platform in ("x", "reddit") else "fail"),
                      f"{q} 个问句（本平台/篇幅建议 ≥{need_q}；整篇 0 问句是 AI 指纹）"))

    # 4 段落长度
    paras = split_paragraphs(text)
    limit = 60 if lang == "zh" else {"blogger": 90, "reddit": 110}.get(platform, 55)
    if lang == "zh":
        limit = {"blogger": 120, "reddit": 150}.get(platform, 90)   # 中文按字计：手机 3 行约 90 字
    long_paras = [p[:40] + "…" for p in paras if unit_len(p, lang) > limit and not BULLET_RE.match(p)]
    items.append(Item("paragraph_length", "warn" if long_paras else "pass",
                      f"{len(long_paras)} 段超过 {limit} {'字' if lang == 'zh' else 'words'}（移动端 3 行原则，拆段）",
                      long_paras))

    # 5 句长起伏（burstiness）
    sents = split_sentences(text, lang)
    lens = [unit_len(s, lang) for s in sents if unit_len(s, lang) > 0]
    if len(lens) >= 6:
        mean = statistics.mean(lens)
        cv = statistics.pstdev(lens) / mean if mean else 0
        items.append(Item("burstiness", "warn" if cv < 0.4 else "pass",
                          f"句长变异系数 {cv:.2f}（<0.40 太工整，短句长句要混着来）"))

    # 6 整齐三点：连续恰好 3 条 bullet 的组 / 英文 "A, B, and C" 三连
    groups, run = [], 0
    for line in text.splitlines() + [""]:
        if BULLET_RE.match(line):
            run += 1
        else:
            if run:
                groups.append(run)
            run = 0
    threes = sum(1 for g in groups if g == 3)
    triads = len(re.findall(r"\b\w+, \w+,? and \w+\b", text)) if lang == "en" else \
        len(re.findall(r"[一-鿿]{2,6}、[一-鿿]{2,6}、[一-鿿]{2,6}", text))
    # 同一个词领头的三连短语（首语重复）：what holds up, what breaks, what it costs / 更快、更稳、更省——一处就是强信号
    anaphora = len(re.findall(r"\b(\w+)\b[^,.;:!?\n]{1,30}, \1\b[^,.;:!?\n]{1,30},? (?:and |or )?\1\b", text, re.I)) + \
        len(re.findall(r"([一-鿿])[一-鿿]{1,8}[，、]\1[一-鿿]{1,8}[，、]\1", text))
    short = platform in ("x",) or len(text) < 600
    flag = threes >= 2 or triads >= 3 or anaphora >= 1 or (short and triads >= 1)
    items.append(Item("rule_of_three", "warn" if flag else "pass",
                      f"{threes} 组恰好三条的列表，{triads} 处三连并列，{anaphora} 处同词领头的三连"
                      "（拆成 2 或 4 条，长短不一；短帖里一处三连就很像 AI）"))

    # 7 not-X-but-Y 对照句式
    contrast = find_all([r"\b(it'?s|this is|that'?s) not (just |only |about )?[^.?!]{1,50}[,;—–-]\s*(it'?s|this is|that'?s)\b",
                         r"\bisn'?t (just |only )?[^.?!]{1,40}[,;]\s*it'?s\b", r"不是[^。！？\n]{1,24}而是",
                         r"不是[^。！？\n]{1,24}[，,]是"], full)
    items.append(Item("not_x_but_y", "fail" if len(contrast) >= 2 else ("warn" if contrast else "pass"),
                      f"{len(contrast)} 处“不是 X 而是 Y”对照（AI 最爱的转折，最多留 1 处）", contrast))

    # 8 互动诱导
    bait = find_all(BAIT, full)
    items.append(Item("engagement_bait", "fail" if bait else "pass",
                      f"{len(bait)} 处互动诱导（只允许用真问题引评论）", bait))

    # 9 感叹号 / emoji 密度
    excl = len(re.findall(r"[!！]", text))
    emojis = EMOJI_RE.findall(re.sub(PLACEHOLDER_RE, "", text))
    emoji_bullets = len(re.findall(r"^\s*[\U0001F300-\U0001FAFF☀-➿]", text, re.M))
    per100 = max(1, words) / 100
    items.append(Item("exclamation", "warn" if excl / per100 > 1 else "pass", f"{excl} 个感叹号"))
    emoji_cap = {"x": 3, "linkedin": 3, "reddit": 1, "blogger": 3}.get(platform, 3)
    items.append(Item("emoji", "warn" if len(emojis) > emoji_cap or emoji_bullets >= 3 else "pass",
                      f"{len(emojis)} 个 emoji，{emoji_bullets} 行 emoji 开头（🚀✅👉 列表是 AI 帖标配）"))

    # 10 待补标记
    ph = PLACEHOLDER_RE.findall(full)
    if mode == "publish":
        items.append(Item("placeholders", "fail" if ph else "pass",
                          f"{len(ph)} 个待补标记 [📝💬📊🖼]（发布前必须由作者本人填掉）"))
    else:
        items.append(Item("placeholders", "pass" if ph else "warn",
                          f"{len(ph)} 个待补标记（草稿阶段至少要有 1 处 [📝] 留给作者的亲身经历）"))

    # 11 平台格式
    items.extend(platform_checks(text, title, platform, lang))

    fails = [i for i in items if i.status == "fail"]
    warns = [i for i in items if i.status == "warn"]
    summary = (f"去AI自查{'通过' if not fails else '未通过'}：硬指纹 {len(hard)}，软指纹 {len(soft)}，"
               f"长破折号 {len(dashes)}，问句 {q}，对照句 {len(contrast)}，互动诱导 {len(bait)}，"
               f"待补标记 {len(ph)}；fail {len(fails)} / warn {len(warns)}。")
    return {"platform": platform, "lang": lang, "mode": mode, "ok": not fails,
            "summary": summary, "items": [asdict(i) for i in items]}


def platform_checks(text: str, title: str, platform: str, lang: str) -> list[Item]:
    out: list[Item] = []
    urls = URL_RE.findall(text)
    tags = HASHTAG_RE.findall(MD_HEADING_RE.sub("", text))
    if platform == "x":
        posts = [p.strip() for p in re.split(r"^\s*---\s*$", text, flags=re.M) if p.strip()]
        over = [(i + 1, x_weighted_len(p)) for i, p in enumerate(posts) if x_weighted_len(p) > 280]
        out.append(Item("x_length", "fail" if over else "pass",
                        f"{len(posts)} 条推文，超 280 加权字数的：{over or '无'}（中文每字算 2）"))
        out.append(Item("x_hashtags", "warn" if len(tags) > 2 else "pass", f"{len(tags)} 个 hashtag（≤2，多了像机器号）"))
        # X 风格：一帖最多一张图；字越少越好（单推 ≤200 加权字最好，串推 ≤5 条）
        n_img = len(re.findall(r"!\[[^\]]*\]\([^)]+\)", text)) + len(re.findall(r"\[🖼[^\]]*\]", text))
        out.append(Item("x_images", "fail" if n_img > 1 else "pass", f"{n_img} 张图（X 一帖最多 1 张）"))
        if len(posts) == 1:
            n = x_weighted_len(posts[0])
            out.append(Item("x_brevity", "warn" if n > 200 else "pass", f"{n} 加权字（X 越短越好，单推最好 ≤200）"))
        elif len(posts) > 5:
            out.append(Item("x_thread_len", "warn", f"串推 {len(posts)} 条，砍到 5 条以内，只留最硬的细节"))
        first_has_link = bool(posts and URL_RE.search(posts[0]))
        out.append(Item("x_link_first_post", "warn" if first_has_link else "pass",
                        "首条带外链会被降权，链接放到串推最后或第一条回复" if first_has_link else "首条无外链"))
        if MD_HEADING_RE.search(text) or "**" in text:
            out.append(Item("x_markdown", "fail", "推文不渲染 Markdown（# / ** 会原样显示）"))
    elif platform == "linkedin":
        n = len(text)
        out.append(Item("li_length", "fail" if n > 3000 else "pass", f"{n} 字符（上限 3000）"))
        hook = text.strip().split("\n")[0][:210]
        bad_hook = re.search(r"^(i'?m (thrilled|excited|humbled|proud)|excited to (share|announce)|"
                             r"i'?ve been thinking|in today'?s|大家好|很高兴)", hook, re.I)
        out.append(Item("li_hook", "fail" if bad_hook else "pass",
                        "前 210 字符是“…see more”之前唯一可见的部分，开头别用 thrilled/excited/大家好" if bad_hook
                        else "开头可用"))
        out.append(Item("li_hashtags", "warn" if len(tags) > 3 else "pass", f"{len(tags)} 个 hashtag（≤3）"))
        out.append(Item("li_link_in_body", "warn" if urls else "pass",
                        f"正文 {len(urls)} 个外链（外链降权，放第一条评论）"))
        one_liners = [l for l in text.splitlines() if l.strip()]
        if len(one_liners) >= 12 and all(len(l) < 90 for l in one_liners):
            out.append(Item("li_broetry", "warn", "通篇一句一行的“领英体”，至少合并出 2 段正常段落"))
        if MD_HEADING_RE.search(text) or "**" in text:
            out.append(Item("li_markdown", "fail", "LinkedIn 不渲染 Markdown（# / ** 会原样显示）"))
    elif platform == "reddit":
        out.append(Item("rd_hashtags", "fail" if tags else "pass", f"{len(tags)} 个 hashtag（Reddit 不用 hashtag，一用就露馅）"))
        out.append(Item("rd_links", "warn" if urls else "pass",
                        f"{len(urls)} 个外链（新号带链接最容易被 AutoMod/垃圾过滤吞，先确认版规）"))
        if len(MD_HEADING_RE.findall(text)) >= 2 and unit_len(text, lang) < 400:
            out.append(Item("rd_headings", "warn", "短帖用多级标题像 AI 写的报告，口语自然段就行"))
        if title:
            t_issues = []
            if len(title) > 300:
                t_issues.append("标题超 300 字符")
            if re.search(r"\b[A-Z]{4,}\b.*\b[A-Z]{4,}\b", title):
                t_issues.append("标题全大写词太多")
            if re.search(r"(you won'?t believe|must[- ]see|insane|!!)", title, re.I):
                t_issues.append("标题党用词")
            out.append(Item("rd_title", "fail" if t_issues else "pass", "；".join(t_issues) or "标题可用"))
        if re.search(r"^(hey|hi|hello) (fellow|everyone|guys)", text.strip(), re.I):
            out.append(Item("rd_opener", "warn", "“Hey fellow gamers!”式开头是营销号/AI 的标志，直接说事"))
    elif platform == "blogger":
        w = unit_len(text, lang)
        floor = 900 if lang == "zh" else 600
        out.append(Item("bl_length", "warn" if w < floor else "pass",
                        f"{w} {'字' if lang == 'zh' else 'words'}（低于 {floor} 容易被判薄内容）"))
        if title:
            tl = len(title)
            cap = 32 if lang == "zh" else 70
            out.append(Item("bl_title", "warn" if tl > cap else "pass", f"标题 {tl} 字符（搜索结果显示约 {cap}）"))
        tables = len(re.findall(r"^\|.*\|\s*$\n^\|[\s:|-]+\|\s*$", text, re.M))
        heads = len(MD_HEADING_RE.findall(text))
        out.append(Item("bl_anchors", "warn" if (w > 800 and tables + heads < 3) else "pass",
                        f"{heads} 个小标题 + {tables} 张表格（长文每 300–400 字一个视觉锚点）"))
    return out


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _print_report(r: dict) -> None:
    icon = {"pass": "✓", "warn": "!", "fail": "✗"}
    print(f"[deai_check] platform={r['platform']} lang={r['lang']} mode={r['mode']}")
    for it in r["items"]:
        print(f"  {icon[it['status']]} {it['key']:<20} {it['detail']}")
        for h in it.get("hits") or []:
            print(f"      · {h}")
    print(r["summary"])


def cmd_check(a) -> int:
    if a.file:
        p = Path(a.file)
        if not p.is_file():
            print(f"错误：找不到文件 {p}", file=sys.stderr)
            return 2
        text = p.read_text(encoding="utf-8")
    else:
        text = a.text or ""
    if not text.strip():
        print("错误：内容为空", file=sys.stderr)
        return 2
    r = run_checks(text, a.platform, a.lang, a.title or "", a.mode)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        _print_report(r)
    return 0 if r["ok"] else 1


def cmd_selftest(_a) -> int:
    bad_en = ("In today's fast-paced world, AI is a game-changer. Let's dive in.\n\n"
              "Moreover, it plays a crucial role — and it's not just a tool, it's a revolution.\n\n"
              "Like and retweet if you agree! Follow for more.")
    good_en = ("I gave Claude Code my 40-file repo last night. It fixed 3 bugs and broke 1 test.\n\n"
               "The broken test? A date parser I wrote in 2021. Fair.\n\n"
               "Took 11 minutes end to end. Would I let it push to main? No. Would I let it open the PR? Already did.")
    bad_zh = ("随着人工智能的发展，值得注意的是，大模型至关重要。综上所述，我们要拥抱变化——未来已来。"
              "首先，效率提升；其次，成本下降；最后，体验更好。")
    long_x = "a" * 281
    cases = [
        ("英文硬指纹+破折号+诱导必 fail", run_checks(bad_en, "x")["ok"] is False),
        ("英文干净稿通过", run_checks(good_en, "x")["ok"] is True),
        ("中文套话必 fail", run_checks(bad_zh, "generic")["ok"] is False),
        ("X 超 281 字 fail", run_checks(long_x, "x")["ok"] is False),
        ("中文 X 141 字加权超限", x_weighted_len("字" * 141) == 282),
        ("同词领头三连判 warn", next(i for i in run_checks("Starting to post what holds up, what breaks, what it costs.",
                                                      "x", "en", "", "draft")["items"] if i["key"] == "rule_of_three")["status"] == "warn"),
        ("中文同字领头三连判 warn", next(i for i in run_checks("用了三个月，更快、更稳、更省，推荐给大家试试看。",
                                                       "generic", "zh", "", "draft")["items"] if i["key"] == "rule_of_three")["status"] == "warn"),
        ("正常句子不误伤", next(i for i in run_checks("Backend Java dev. I'll be posting what AI tools actually do on real backend code, including the parts where they break.",
                                                 "x", "en", "", "draft")["items"] if i["key"] == "rule_of_three")["status"] == "pass"),
        ("URL 计 23", x_weighted_len("https://example.com/very/long/path/that/is/long") == 23),
        ("publish 模式待补标记 fail", run_checks(good_en + "\n\n[📝 your story]", "x", mode="publish")["ok"] is False),
        ("Reddit hashtag fail", run_checks("Played Hades 2 for 30 hours. #gaming", "reddit")["ok"] is False),
        ("LinkedIn thrilled 开头 fail", run_checks("I'm thrilled to announce my new role.", "linkedin")["ok"] is False),
        ("X 里写 markdown fail", run_checks("**bold** claim here", "x")["ok"] is False),
        ("语言检测中文", detect_lang(bad_zh) == "zh"),
    ]
    ok = True
    for name, passed in cases:
        print(f"  {'✓' if passed else '✗'} {name}")
        ok &= passed
    print("selftest", "通过" if ok else "失败")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="去 AI 味确定性自查（中英双语 · 按平台）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="检查一篇稿子")
    g = c.add_mutually_exclusive_group(required=True)
    g.add_argument("--file")
    g.add_argument("--text")
    c.add_argument("--platform", choices=PLATFORMS, default="generic")
    c.add_argument("--lang", choices=("auto", "en", "zh"), default="auto")
    c.add_argument("--title", default="")
    c.add_argument("--mode", choices=("draft", "publish"), default="draft")
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=cmd_check)
    s = sub.add_parser("selftest")
    s.set_defaults(func=cmd_selftest)
    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
