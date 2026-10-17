# Blogger 首次配置（约 10 分钟，只做一次）

1. **建博客**：用要用的 Google 账号登录 https://www.blogger.com ，新建博客，选一个跟定位一致的地址（如 `xxx-ai-notes.blogspot.com`）。
   设置里：开启“搜索描述”（Settings → Meta tags → Enable search description）、时区、语言。
2. **Google Cloud 项目**：打开 https://console.cloud.google.com ，新建项目（如 `easel-blogger`）。
3. **启用 API**：APIs & Services → Library → 搜 “Blogger API v3” → Enable。
4. **OAuth 同意屏幕**：APIs & Services → OAuth consent screen → User type 选 External → 填应用名和邮箱 →
   Scopes 可以不加 → Test users 里**加上你自己的 Google 账号**。保持 Testing 状态即可（自用不需要提交审核）。
   注意：Testing 状态下 refresh token 7 天过期，过期后重跑一次 `auth`；想长期免授权，把应用发布为 In production（自用不需要验证也能用，会有“未验证应用”提示，点继续）。
5. **建凭据**：APIs & Services → Credentials → Create credentials → OAuth client ID → Application type 选 **Desktop app**。
6. **写进项目根 `.env`**（自己写，不要贴到对话里）：
   ```
   BLOGGER_CLIENT_ID=xxxxx.apps.googleusercontent.com
   BLOGGER_CLIENT_SECRET=xxxxx
   ```
7. **授权**：
   ```bash
   python skills/builtin/skill-blogger-publisher/scripts/blogger.py auth
   ```
   浏览器会打开 Google 授权页，同意后终端显示“授权成功”。令牌存在 `~/.config/easel/blogger-token.json`（权限 600）。
8. **拿 Blog ID**：
   ```bash
   python skills/builtin/skill-blogger-publisher/scripts/blogger.py blogs
   ```
   把对应博客的 ID 写进 `.env`：`BLOGGER_BLOG_ID=1234567890`。
9. **自检**：`blogger.py check` 三项都有值、令牌已授权即可。
10. **登记账号**：`python skills/shared/scripts/cadence_gate.py account --platform blogger --created <建站日期>`
11. **接 Search Console**（建议囤够 3 篇后）：https://search.google.com/search-console 添加博客地址，提交 `https://<博客>/sitemap.xml`。
