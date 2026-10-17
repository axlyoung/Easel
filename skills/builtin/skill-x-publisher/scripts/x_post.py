#!/usr/bin/env python3
"""x_post.py — X 原创帖自动发布：官方 API（OAuth 1.0a 用户上下文）+ 排队 + 定时 + 发前三道闸 + 自动登记.

X 允许用官方 API 定时发**自己的原创帖**；自动回复别人仍不允许（回复走 skill-x-reply，人点发送）。
人只做一件事：审内容（在对话里说“发 A”= approve）。排时间、过闸、发帖、挂来源链接、登记全自动。

凭据（项目根 .env，developer.x.com → 你的 App → Keys and tokens；App 权限要 Read and write）:
  X_API_KEY / X_API_SECRET            （Consumer Keys）
  X_ACCESS_TOKEN / X_ACCESS_SECRET    （Access Token and Secret，改成 Read and write 之后要重新生成）
可选：X_POST_SLOTS="21:15,09:30"（北京时间发帖时段，默认 21:15 = 美东早 9 点；S2 起才用第二个）
      X_AUTO_APPROVE=1                （资讯点评草稿不等人审，直接排队；默认关）

子命令:
  check                                            凭据自检（调 /2/users/me，不发帖）
  add --file x.md [--image a.png] [--source-url U] [--approve] [--at "2026-10-14 21:15"] [--kind personal|news]
                                                   加入发帖队列（默认 draft，等人审）
  approve --id N [--at ...] / reject --id N        审稿：通过并排时间 / 丢弃
  queue [--all]                                    看队列
  run [--dry-run]                                  发到点的已审帖（launchd 每 15 分钟跑一次）
  post --file x.md [--image a.png] [--yes]         立刻发一条（仍过三道闸；不带 --yes 只预演）
  install / uninstall / status                     macOS launchd 定时
  selftest
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import random
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve()
CODE_ROOT = HERE.parents[4]
SHARED = CODE_ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SHARED))

import cadence_gate as cg  # noqa: E402
import deai_check as dc  # noqa: E402

API = "https://api.x.com/2"
MEDIA_UPLOAD = "https://upload.twitter.com/1.1/media/upload.json"
LABEL = "com.easel.x-post"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
DEFAULT_SLOTS = "21:15,09:30"
JITTER_MIN = 12           # 发帖时间随机前后 12 分钟，不卡整点


def _root() -> Path:
    return Path(os.environ.get("EASEL_ROOT") or CODE_ROOT)


def _queue_file() -> Path:
    return _root() / "outputs" / "_analytics" / "x-post-queue.json"


def _now() -> datetime:
    return cg._now()


def load_env() -> None:
    f = _root() / ".env"
    if not f.is_file():
        return
    for raw in f.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _creds() -> tuple[str, str, str, str]:
    keys = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")
    vals = tuple(os.environ.get(k, "").strip() for k in keys)
    missing = [k for k, v in zip(keys, vals) if not v]
    if missing:
        raise RuntimeError("缺 X 发帖凭据：" + "、".join(missing) + "（写进项目根 .env，见 x_post.py 开头说明）")
    return vals  # type: ignore[return-value]


# --------------------------------------------------------------------------- #
# OAuth 1.0a（HMAC-SHA1）
# --------------------------------------------------------------------------- #
def _pct(s: str) -> str:
    return urllib.parse.quote(str(s), safe="~-._")


def oauth_signature(method: str, url: str, params: dict, consumer_secret: str, token_secret: str) -> str:
    pairs = sorted((_pct(k), _pct(v)) for k, v in params.items())
    base = "&".join([method.upper(), _pct(url), _pct("&".join(f"{k}={v}" for k, v in pairs))])
    key = f"{_pct(consumer_secret)}&{_pct(token_secret)}".encode()
    return base64.b64encode(hmac.new(key, base.encode(), hashlib.sha1).digest()).decode()


def oauth_header(method: str, url: str, query: dict | None = None, form: dict | None = None,
                 creds: tuple[str, str, str, str] | None = None, nonce: str | None = None,
                 ts: str | None = None) -> str:
    ck, cs, tk, ts_secret = creds or _creds()
    oauth = {"oauth_consumer_key": ck, "oauth_nonce": nonce or secrets.token_hex(16),
             "oauth_signature_method": "HMAC-SHA1", "oauth_timestamp": ts or str(int(time.time())),
             "oauth_token": tk, "oauth_version": "1.0"}
    params = {**oauth, **(query or {}), **(form or {})}       # JSON / multipart 正文不参与签名
    oauth["oauth_signature"] = oauth_signature(method, url, params, cs, ts_secret)
    return "OAuth " + ", ".join(f'{_pct(k)}="{_pct(v)}"' for k, v in sorted(oauth.items()))


def _request(method: str, url: str, body: bytes | None = None, ctype: str | None = None,
             query: dict | None = None, timeout: int = 30) -> dict:
    full = url + ("?" + urllib.parse.urlencode(query) if query else "")
    req = urllib.request.Request(full, data=body, method=method)
    req.add_header("Authorization", oauth_header(method, url, query=query))
    req.add_header("User-Agent", "easel-x-post/1.0")
    if ctype:
        req.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8") or "{}"
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        hint = {401: "凭据不对，或改了 App 权限后没重新生成 Access Token",
                403: "App 没有写权限（User authentication settings 里设成 Read and write，再重新生成 Access Token），或内容被拒",
                429: "触发频率限制，过一阵再发"}.get(e.code, "")
        raise RuntimeError(f"X API {e.code}：{hint} {detail}".strip()) from e


def me() -> dict:
    return _request("GET", f"{API}/users/me")["data"]


def upload_image(path: Path) -> str:
    data = path.read_bytes()
    if len(data) > 5 * 1024 * 1024:
        raise RuntimeError("图片超过 5MB，先压缩")
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"media\"; filename=\"{path.name}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
    r = _request("POST", MEDIA_UPLOAD, body, f"multipart/form-data; boundary={boundary}", timeout=120)
    return str(r["media_id_string"])


def create_tweet(text: str, reply_to: str | None = None, media_ids: list[str] | None = None) -> str:
    payload: dict = {"text": text}
    if reply_to:
        payload["reply"] = {"in_reply_to_tweet_id": reply_to}
    if media_ids:
        payload["media"] = {"media_ids": media_ids}
    r = _request("POST", f"{API}/tweets", json.dumps(payload).encode(), "application/json")
    return str(r["data"]["id"])


# --------------------------------------------------------------------------- #
# 闸门
# --------------------------------------------------------------------------- #
def gates(text: str, n_images: int) -> dict:
    """三道闸：去AI（发布模式）→ 内容泄露 → 节奏。返回 {ok, verdict, reasons, next_allowed_at}。"""
    r = dc.run_checks(text, "x", "auto", "", "publish")
    fails = [f"去AI：{i['key']} {i['detail']}" for i in r["items"] if i["status"] == "fail"]
    if n_images > 1:
        fails.append("X 一帖最多 1 张图")
    guard = subprocess.run([sys.executable, str(SHARED / "content_guard.py"), "scan", "--text", text],
                           capture_output=True, text=True)
    if guard.returncode == 7:
        fails.append("content_guard：有内部信息泄露")
    if fails:
        return {"ok": False, "verdict": "fix", "reasons": fails, "next_allowed_at": None}
    _, af, lf = _paths()
    g = cg.evaluate("x", "post", bool(dc.URL_RE.search(text)), False, None, cg.load_accounts(af),
                    cg.load_entries(lf), _now())
    return {"ok": g["verdict"] == "allow", "verdict": g["verdict"], "reasons": g["reasons"],
            "next_allowed_at": g.get("next_allowed_at")}


def _paths():
    a = _root() / "outputs" / "_analytics"
    return a / "x-targets.json", a / "intl-accounts.json", a / "publish-log.json"


def _record(text: str, url: str, kind: str, typ: str = "post") -> None:
    cmd = [sys.executable, str(SHARED / "cadence_gate.py"), "record", "--platform", "x", "--type", typ,
           "--title", text[:60], "--url", url, "--notes", text, "--skill-source", "skill-x-publisher",
           "--tags", f"kind:{kind},auto"]
    subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ, EASEL_ROOT=str(_root())))


# --------------------------------------------------------------------------- #
# 队列
# --------------------------------------------------------------------------- #
def load_queue() -> dict:
    return cg._load_json(_queue_file(), {"next_id": 1, "items": []})


def save_queue(q: dict) -> None:
    cg._atomic_write(_queue_file(), q)


def _slots() -> list[tuple[int, int]]:
    out = []
    for s in (os.environ.get("X_POST_SLOTS") or DEFAULT_SLOTS).split(","):
        m = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", s)
        if m:
            out.append((int(m.group(1)), int(m.group(2))))
    return out or [(21, 15)]


def next_slot(now: datetime, taken: list[datetime], per_day: int) -> datetime:
    """下一个空闲发帖时段：每天最多 per_day 条（按阶段），同一天的时段按 X_POST_SLOTS 顺序用。"""
    slots = _slots()[:max(1, per_day)]
    rnd = random.Random(int(now.timestamp()) // 60)
    for day in range(0, 14):
        d = (now + timedelta(days=day)).date()
        used = sum(1 for t in taken if t.date() == d)
        for h, m in sorted(slots):
            if used >= per_day:
                break
            at = now.replace(year=d.year, month=d.month, day=d.day, hour=h, minute=m, second=0, microsecond=0)
            at += timedelta(minutes=rnd.randint(-JITTER_MIN, JITTER_MIN))
            if at > now + timedelta(minutes=5) and all(abs((at - t).total_seconds()) > 3 * 3600 for t in taken):
                return at
    return now + timedelta(days=1)


def _per_day() -> int:
    _, af, _ = _paths()
    st, _, _ = cg.stage_for("x", cg.load_accounts(af).get("x"), _now())
    # 起步期第一周按 1 条/天走；之后按阶段上限，但不超过时段数
    key = st["name"].split()[0]
    return {"S0": 1, "S1": 1, "S2": 2, "S3": 2}.get(key, 1)


def _parse_at(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M").astimezone()


def schedule(item: dict, q: dict, at: str | None = None) -> None:
    taken = [datetime.fromisoformat(i["at"]) for i in q["items"]
             if i.get("at") and i["status"] in ("approved", "posted") and i is not item]
    item["at"] = (_parse_at(at) if at else next_slot(_now(), taken, _per_day())).isoformat(timespec="minutes")


def add_item(text: str, image: str | None, source_url: str | None, kind: str, approve: bool,
             at: str | None = None, meta: dict | None = None) -> dict:
    q = load_queue()
    item = {"id": q["next_id"], "text": text.strip(), "image": image, "source_url": source_url, "kind": kind,
            "status": "draft", "created": _now().isoformat(timespec="minutes"), **(meta or {})}
    q["next_id"] += 1
    if approve:
        item["status"] = "approved"
        schedule(item, q, at)
    q["items"].append(item)
    save_queue(q)
    return item


def _find(q: dict, iid: int) -> dict:
    for it in q["items"]:
        if it["id"] == iid:
            return it
    sys.exit(f"错误：队列里没有 #{iid}")


def post_item(item: dict, dry_run: bool = False) -> str:
    img = [Path(item["image"])] if item.get("image") else []
    g = gates(item["text"], len(img))
    if not g["ok"]:
        if g["verdict"] == "wait":
            item["note"] = f"节奏闸：{'；'.join(g['reasons'])}，顺延到 {g['next_allowed_at']}"
            if g.get("next_allowed_at"):
                item["at"] = g["next_allowed_at"]
            return "wait"
        item["status"], item["note"] = "blocked", "；".join(g["reasons"])
        return "blocked"
    if dry_run:
        return "ok(dry-run)"
    media = [upload_image(p) for p in img]
    tid = create_tweet(item["text"], media_ids=media or None)
    user = os.environ.get("X_HANDLE") or (cg.load_accounts(_paths()[1]).get("x") or {}).get("handle", "i")
    url = f"https://x.com/{user.lstrip('@')}/status/{tid}"
    item.update(status="posted", tweet_id=tid, url=url, posted_at=_now().isoformat(timespec="minutes"))
    _record(item["text"], url, item.get("kind", "personal"))
    if item.get("source_url"):
        # 资讯帖：来源链接挂在自己的第一条回复里（起步期正文不放外链）
        try:
            rid = create_tweet(f"Source: {item['source_url']}", reply_to=tid)
            _record(f"Source: {item['source_url']}", url.rsplit("/", 1)[0] + f"/{rid}", item.get("kind", "news"),
                    typ="reply")
        except RuntimeError as e:
            item["note"] = f"正文已发，来源链接回复失败：{e}"
    return "posted"


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def _read(path: str) -> str:
    p = Path(path)
    if not p.is_file():
        sys.exit(f"错误：找不到 {p}")
    return p.read_text(encoding="utf-8").strip()


def cmd_check(_a) -> int:
    load_env()
    try:
        u = me()
    except RuntimeError as e:
        print(f"✗ {e}")
        return 1
    print(f"✓ 凭据可用：@{u.get('username')}（{u.get('name')}）")
    return 0


def cmd_add(a) -> int:
    load_env()
    it = add_item(_read(a.file), a.image, a.source_url, a.kind, a.approve or os.environ.get("X_AUTO_APPROVE") == "1"
                  and a.kind == "news", a.at)
    print(json.dumps(it, ensure_ascii=False, indent=2))
    return 0


def cmd_approve(a) -> int:
    load_env()
    q = load_queue()
    it = _find(q, a.id)
    if it["status"] not in ("draft", "blocked"):
        sys.exit(f"#{a.id} 当前是 {it['status']}，不用再审")
    it["status"] = "approved"
    schedule(it, q, a.at)
    save_queue(q)
    print(f"✓ #{a.id} 已通过，排在 {it['at']} 自动发")
    return 0


def cmd_reject(a) -> int:
    q = load_queue()
    _find(q, a.id)["status"] = "rejected"
    save_queue(q)
    print(f"#{a.id} 已丢弃")
    return 0


def cmd_queue(a) -> int:
    q = load_queue()
    rows = [i for i in q["items"] if a.all or i["status"] in ("draft", "approved", "blocked")]
    if not rows:
        print("队列为空")
    for i in rows:
        print(f"#{i['id']:<3} {i['status']:<9} {i.get('kind', ''):<8} {i.get('at') or '-':<17} "
              f"{dc.x_weighted_len(i['text']):>3}字 {i['text'][:70]}")
        if i.get("note"):
            print(f"      ! {i['note']}")
    return 0


def cmd_run(a) -> int:
    load_env()
    q = load_queue()
    now = _now()
    due = [i for i in q["items"] if i["status"] == "approved" and i.get("at")
           and datetime.fromisoformat(i["at"]) <= now]
    if not due:
        print(f"[{now:%m-%d %H:%M}] 没有到点的帖")
        return 0
    for it in due[:1]:                       # 一次最多发 1 条，下一条等下一轮（闸门也会卡间隔）
        try:
            r = post_item(it, a.dry_run)
        except RuntimeError as e:
            it["note"] = str(e)[:300]
            r = "error"
        print(f"[{now:%m-%d %H:%M}] #{it['id']} {r} {it.get('url') or it.get('note') or ''}")
        if r == "posted" and sys.platform == "darwin" and not os.environ.get("EASEL_NO_NOTIFY"):
            subprocess.run(["osascript", "-e", 'display notification "已自动发出 1 条推文" with title "X 发帖"'],
                           capture_output=True)
    if not a.dry_run:
        save_queue(q)
    return 0


def cmd_post(a) -> int:
    load_env()
    item = {"id": 0, "text": _read(a.file), "image": a.image, "kind": a.kind, "source_url": a.source_url}
    if not a.yes:
        g = gates(item["text"], 1 if a.image else 0)
        print(json.dumps(g, ensure_ascii=False, indent=2))
        print("预演：加 --yes 才真发")
        return 0 if g["ok"] else 3
    r = post_item(item)
    print(r, item.get("url") or item.get("note") or "")
    return 0 if r == "posted" else 3


def cmd_install(a) -> int:
    py = a.python or sys.executable
    logs = _root() / "outputs" / "_logs"
    logs.mkdir(parents=True, exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    PLIST.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>{LABEL}</string>
<key>ProgramArguments</key><array><string>{py}</string><string>{HERE}</string><string>run</string></array>
<key>WorkingDirectory</key><string>{_root()}</string>
<key>StartInterval</key><integer>900</integer>
<key>StandardOutPath</key><string>{logs}/x-post.log</string>
<key>StandardErrorPath</key><string>{logs}/x-post.err.log</string>
</dict></plist>
""", encoding="utf-8")
    subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
    r = subprocess.run(["launchctl", "load", str(PLIST)], capture_output=True, text=True)
    print(r.stderr.strip() or f"已安装：每 15 分钟检查一次到点的帖；日志 {logs}/x-post.log")
    return r.returncode


def cmd_uninstall(_a) -> int:
    if PLIST.is_file():
        subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
        PLIST.unlink()
    print("已卸载")
    return 0


def cmd_status(_a) -> int:
    r = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    print("定时：" + ("运行中" if LABEL in r.stdout else ("已写入未加载" if PLIST.is_file() else "未安装")))
    return cmd_queue(argparse.Namespace(all=False))


def cmd_selftest(_a) -> int:
    import tempfile
    ok = True

    def case(name, cond):
        nonlocal ok
        print(f"  {'✓' if cond else '✗'} {name}")
        ok &= bool(cond)

    # X 官方文档里的 OAuth 1.0a 签名示例
    sig = oauth_signature("POST", "https://api.twitter.com/1.1/statuses/update.json", {
        "status": "Hello Ladies + Gentlemen, a signed OAuth request!", "include_entities": "true",
        "oauth_consumer_key": "xvz1evFS4wEEPTGEFPHBog", "oauth_nonce": "kYjzVBB8Y0ZFabxSWbWovY3uYSQ2pTgmZeNu2VS4cg",
        "oauth_signature_method": "HMAC-SHA1", "oauth_timestamp": "1318622958",
        "oauth_token": "370773112-GmHxMAgYyLbNEtIKZeRNFsMKPR9EyMZeS9weJAEb", "oauth_version": "1.0"},
        "kAcSOqF21Fu85e7zjz7ZN2U4ZRhfV3WpwPAoE3Z7kBw", "LswwdoUaIvS8ltyTt5jkRh4J50vUPVVHtR2YPi5kE")
    case("OAuth 签名与 X 官方示例一致", sig == "hCtSmYh+iHYCEqBWrE7C7hYmtUk=")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ.update(EASEL_ROOT=tmp, EASEL_CADENCE_NOW="2026-10-14T10:00:00+08:00", EASEL_NO_NOTIFY="1")
        cg._atomic_write(_paths()[1], {"x": {"created": "2025-07-01", "active_since": "2026-10-12"}})
        a = add_item("Backend devs: the model got stubborn. Screenshots still win the argument.", None, None,
                     "personal", True)
        case("通过即排到当天 21:15 前后", a["at"].startswith("2026-10-14T21") or a["at"].startswith("2026-10-14T21:0"))
        b = add_item("Second approved post for the queue test, different words here.", None, None, "personal", True)
        case("第二条排到次日（起步期 1 条/天）", b["at"].startswith("2026-10-15"))
        d = add_item("Draft only.", None, None, "news", False)
        case("草稿不排时间", d["status"] == "draft" and "at" not in d)
        case("两张图被拦", not gates("short text that is fine to post here", 2)["ok"])
        case("AI 腔被拦", gates("In today's fast-paced landscape, let's delve into this game-changer.", 0)["verdict"] == "fix")
        os.environ["EASEL_CADENCE_NOW"] = "2026-10-14T21:30:00+08:00"
        q = load_queue()
        r = post_item(q["items"][0], dry_run=True)
        case("到点的帖过闸（预演）", r == "ok(dry-run)")
    print("selftest", "通过" if ok else "失败")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="X 原创帖自动发布（官方 API）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").set_defaults(func=cmd_check)
    p = sub.add_parser("add")
    p.add_argument("--file", required=True); p.add_argument("--image"); p.add_argument("--source-url")
    p.add_argument("--approve", action="store_true"); p.add_argument("--at")
    p.add_argument("--kind", choices=("personal", "news"), default="personal")
    p.set_defaults(func=cmd_add)
    p = sub.add_parser("approve"); p.add_argument("--id", type=int, required=True); p.add_argument("--at")
    p.set_defaults(func=cmd_approve)
    p = sub.add_parser("reject"); p.add_argument("--id", type=int, required=True); p.set_defaults(func=cmd_reject)
    p = sub.add_parser("queue"); p.add_argument("--all", action="store_true"); p.set_defaults(func=cmd_queue)
    p = sub.add_parser("run"); p.add_argument("--dry-run", action="store_true"); p.set_defaults(func=cmd_run)
    p = sub.add_parser("post")
    p.add_argument("--file", required=True); p.add_argument("--image"); p.add_argument("--source-url")
    p.add_argument("--kind", choices=("personal", "news"), default="personal"); p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_post)
    p = sub.add_parser("install"); p.add_argument("--python"); p.set_defaults(func=cmd_install)
    sub.add_parser("uninstall").set_defaults(func=cmd_uninstall)
    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("selftest").set_defaults(func=cmd_selftest)
    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
