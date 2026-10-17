# Easel SKILL 元数据

| 字段 | 值 |
|------|-----|
| **SKILL 名称** | skill-blogger-publisher |
| **所属层** | publish |
| **来源** | Easel 自研；流程与去 AI 味/自查规则参考 WorkBuddy「公众号爆文专家」（github.com/adsorgcn/WorkBuddy，MIT） |
| **功能描述** | Blogger 长文母本写作 + 官方 API v3 建草稿/发布（OAuth 桌面应用，PKCE） |
| **核心脚本** | scripts/blogger.py（纯标准库；check/auth/blogs/draft/publish/posts；draft 内置 content_guard + 去AI自查） |
| **profile_aware** | true |
| **自包含** | 是（Blogger 需用户自备 Google OAuth 客户端） |

> 创建时间: 2026-10-12
> 用途: 补齐海外平台（X / LinkedIn / Blogger / Reddit）的写作、去 AI 味与新号防 ban 节奏

## 设计说明

- 新号阶段 X / LinkedIn / Reddit 一律**人手发布**（预填官方发帖链接），不做浏览器自动化或非官方 API 代发：
  这三个平台对新号的自动化行为最敏感，自动化发帖是封号的头号原因。Blogger 走官方 API，默认只建草稿。
- 节奏限额固化在 `skills/shared/scripts/cadence_gate.py` 的 STAGES 表，与
  `skill-global-creator/references/cadence-playbook.md` 保持一致；改一边必须同步另一边。
