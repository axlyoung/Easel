#!/usr/bin/env python3
"""blogger.py — Blogger 官方 API v3 发布（默认只建草稿，人在后台看完再发）.

为什么用官方 API 而不是浏览器自动化：Blogger 有免费、稳定的官方接口，OAuth 授权一次，
之后用 refresh token 续期；比模拟点击安全得多，也不存在“像机器人”的问题。

配置（项目根 .env，不进对话、不回显）：
  BLOGGER_CLIENT_ID       Google Cloud → 凭据 → OAuth 客户端 ID（类型：桌面应用）
  BLOGGER_CLIENT_SECRET   同上
  BLOGGER_BLOG_ID         目标博客 ID（`blogs` 子命令能列出来）
令牌存 ~/.config/easel/blogger-token.json（权限 600），不进仓库、不进 outputs。

子命令:
  check                                      脱敏检查配置与令牌（不联网）
  auth                                       浏览器授权一次，本机回环接收 code，换 refresh token
  blogs                                      列出账号下的博客（拿 BLOGGER_BLOG_ID）
  draft   --file post.md --title T [--labels a,b] [--description "搜索描述"] [--html]
                                             建草稿：先跑 content_guard + deai_check(publish)，任何 fail 都不提交
  publish --post-id ID --yes                 把草稿正式发布（不带 --yes 只打印将要发布的标题）
  posts   [--status draft|live] [--n 10]     列出最近文章

退出码：0 成功；1 一般错误；2 配置缺失；5 去AI自查未过；7 敏感信息命中（content_guard）。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import os
import secrets
import socket
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve()
PROJECT_ROOT = Path(os.environ.get("EASEL_ROOT") or HERE.parents[4])
SHARED = PROJECT_ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SHARED))

TOKEN_FILE = Path(os.environ.get("EASEL_BLOGGER_TOKEN") or Path.home() / ".config" / "easel" / "blogger-token.json")
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/blogger/v3"
SCOPE = "https://www.googleapis.com/auth/blogger"


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #
def load_env() -> dict:
    env = {}
    p = PROJECT_ROOT / ".env"
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET", "BLOGGER_BLOG_ID"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def _mask(v: str) -> str:
    return "(未配置)" if not v else (v[:4] + "…" + v[-3:] if len(v) > 10 else "***")


def _die(msg: str, code: int = 1):
    print(f"错误：{msg}", file=sys.stderr)
    sys.exit(code)


def _need(env: dict, *keys):
    miss = [k for k in keys if not env.get(k)]
    if miss:
        _die(f"项目根 .env 缺少 {', '.join(miss)}；见 skill-blogger-publisher/references/setup.md", 2)


# --------------------------------------------------------------------------- #
# http
# --------------------------------------------------------------------------- #
def _post_form(url: str, data: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        _die(f"令牌接口 HTTP {e.code}：{e.read().decode()[:300]}")


def _save_token(tok: dict):
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(tok), encoding="utf-8")
    os.chmod(TOKEN_FILE, 0o600)


def access_token(env: dict) -> str:
    if not TOKEN_FILE.is_file():
        _die("还没授权：先运行 blogger.py auth", 2)
    tok = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    r = _post_form(TOKEN_URL, {"client_id": env["BLOGGER_CLIENT_ID"], "client_secret": env["BLOGGER_CLIENT_SECRET"],
                               "refresh_token": tok["refresh_token"], "grant_type": "refresh_token"})
    return r["access_token"]


def api(env: dict, method: str, path: str, body: dict | None = None, query: dict | None = None) -> dict:
    url = API + path + ("?" + urllib.parse.urlencode(query) if query else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {access_token(env)}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        _die(f"Blogger API HTTP {e.code}：{e.read().decode()[:400]}")


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def cmd_check(_a) -> int:
    env = load_env()
    for k in ("BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET", "BLOGGER_BLOG_ID"):
        print(f"  {k:<22} {_mask(env.get(k, ''))}")
    print(f"  {'令牌':<22} {'已授权' if TOKEN_FILE.is_file() else '未授权（运行 auth）'}")
    ok = all(env.get(k) for k in ("BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET")) and TOKEN_FILE.is_file()
    if not env.get("BLOGGER_BLOG_ID"):
        print("  提示：授权后运行 blogs 拿到博客 ID，写进 .env 的 BLOGGER_BLOG_ID")
    return 0 if ok else 2


def cmd_auth(_a) -> int:
    env = load_env()
    _need(env, "BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET")
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    redirect = f"http://127.0.0.1:{port}"
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": env["BLOGGER_CLIENT_ID"], "redirect_uri": redirect, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256"})
    got: dict = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("授权完成，可以关闭这个页面回到终端。".encode())

        def log_message(self, *args):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", port), H)
    t = threading.Thread(target=srv.handle_request, daemon=True)
    t.start()
    print("在浏览器里打开下面的链接并同意授权（会自动尝试打开）：\n" + url)
    webbrowser.open(url)
    t.join(timeout=300)
    srv.server_close()
    if got.get("state") != state or "code" not in got:
        _die(f"没收到授权码（{got.get('error', '超时')}）")
    tok = _post_form(TOKEN_URL, {"client_id": env["BLOGGER_CLIENT_ID"], "client_secret": env["BLOGGER_CLIENT_SECRET"],
                                 "code": got["code"], "code_verifier": verifier, "grant_type": "authorization_code",
                                 "redirect_uri": redirect})
    if "refresh_token" not in tok:
        _die("Google 没返回 refresh_token；去 https://myaccount.google.com/permissions 撤销本应用后重试")
    _save_token({"refresh_token": tok["refresh_token"]})
    print(f"授权成功，令牌已保存到 {TOKEN_FILE}（权限 600）")
    return 0


def cmd_blogs(_a) -> int:
    env = load_env()
    _need(env, "BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET")
    r = api(env, "GET", "/users/self/blogs")
    for b in r.get("items", []):
        print(f"  {b['id']}  {b['name']}  {b['url']}  posts={b.get('posts', {}).get('totalItems')}")
    return 0


def md_to_html(md: str) -> str:
    try:
        import markdown
    except ImportError:
        _die("需要 markdown 库（pip install markdown），或用 --html 直接传 HTML")
    return markdown.markdown(md, extensions=["extra", "sane_lists"])


def cmd_draft(a) -> int:
    env = load_env()
    _need(env, "BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET", "BLOGGER_BLOG_ID")
    src = Path(a.file)
    if not src.is_file():
        _die(f"找不到 {src}")
    text = src.read_text(encoding="utf-8")

    import content_guard
    content_guard.guard_or_die([a.title, text, a.description or ""], exec_mode=True, label="Blogger 文章")
    import deai_check
    if not a.html:
        r = deai_check.run_checks(text, "blogger", "auto", a.title, "publish")
        if not r["ok"]:
            deai_check._print_report(r)
            _die("去AI自查未通过，改稿后再提交草稿", 5)

    body = {"kind": "blogger#post", "title": a.title, "content": text if a.html else md_to_html(text)}
    if a.labels:
        body["labels"] = [x.strip() for x in a.labels.split(",") if x.strip()]
    if a.description:
        body["customMetaData"] = json.dumps({"description": a.description})   # 搜索描述需在博客设置里开启
    r = api(env, "POST", f"/blogs/{env['BLOGGER_BLOG_ID']}/posts", body, {"isDraft": "true"})
    print(json.dumps({"ok": True, "status": r.get("status"), "post_id": r.get("id"), "title": r.get("title"),
                      "edit_url": f"https://www.blogger.com/blog/post/edit/{env['BLOGGER_BLOG_ID']}/{r.get('id')}"},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_publish(a) -> int:
    env = load_env()
    _need(env, "BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET", "BLOGGER_BLOG_ID")
    blog = env["BLOGGER_BLOG_ID"]
    post = api(env, "GET", f"/blogs/{blog}/posts/{a.post_id}", query={"view": "AUTHOR"})
    if not a.yes:
        print(f"将要发布：《{post.get('title')}》（{post.get('status')}）。确认后带 --yes 再跑一次。")
        return 0
    r = api(env, "POST", f"/blogs/{blog}/posts/{a.post_id}/publish")
    print(json.dumps({"ok": True, "status": r.get("status"), "url": r.get("url"), "title": r.get("title")},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_posts(a) -> int:
    env = load_env()
    _need(env, "BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET", "BLOGGER_BLOG_ID")
    q = {"maxResults": a.n, "view": "AUTHOR", "fetchBodies": "false"}
    if a.status:
        q["status"] = a.status
    r = api(env, "GET", f"/blogs/{env['BLOGGER_BLOG_ID']}/posts", query=q)
    for p in r.get("items", []):
        print(f"  {p['id']}  [{p.get('status', 'LIVE')}]  {p.get('published', '')[:10]}  {p['title']}  {p.get('url', '')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Blogger 官方 API 发布（默认草稿）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").set_defaults(func=cmd_check)
    sub.add_parser("auth").set_defaults(func=cmd_auth)
    sub.add_parser("blogs").set_defaults(func=cmd_blogs)
    d = sub.add_parser("draft")
    d.add_argument("--file", required=True)
    d.add_argument("--title", required=True)
    d.add_argument("--labels")
    d.add_argument("--description")
    d.add_argument("--html", action="store_true", help="--file 已经是 HTML（跳过 Markdown 转换与去AI自查）")
    d.set_defaults(func=cmd_draft)
    p = sub.add_parser("publish")
    p.add_argument("--post-id", required=True, dest="post_id")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_publish)
    l = sub.add_parser("posts")
    l.add_argument("--status", choices=("draft", "live", "scheduled"))
    l.add_argument("--n", type=int, default=10)
    l.set_defaults(func=cmd_posts)
    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
