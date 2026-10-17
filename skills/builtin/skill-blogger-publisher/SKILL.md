---
name: skill-blogger-publisher
description: >
  Blogger（blogspot）AI 方向长文：写一稿多发的母本长文（实测/教程/成本账），SEO 基础（标题、搜索描述、labels、
  alt），过去 AI 味自查，通过 Blogger 官方 API 建草稿，人在后台看完再发布。当用户说“发 Blogger/发博客/
  写博客/blogspot/写篇长文/建个博客”时使用。
layer: publish
version: 0.1.0
profile_aware: true
---

# Blogger 发布（AI 方向长文 · 母本）

> Blogger 是一稿多发的**母本**：长文写透，X / LinkedIn 从它拆。用官方 API v3，默认只建**草稿**，人在 Blogger 后台看过再发。
> 第一次使用的配置（Google Cloud OAuth 桌面应用）见 @references/setup.md。

## 环境

```bash
cd <项目根>
python skills/builtin/skill-blogger-publisher/scripts/blogger.py check     # 脱敏检查 .env 和令牌，不联网
```

缺配置就按 setup.md 带用户走一遍；不要让用户把 client secret 贴进对话，让他自己写进 `.env`。

## 执行

1. **查阶段**：`python skills/shared/scripts/cadence_gate.py check --platform blogger --type article`
2. **确认素材与骨架**：一句话说清这篇解决什么、读者是谁、独家内容在哪（≥15%，不够就在提纲里标出要作者补哪段）。
   骨架二选一：**实测复盘**（结果先行 → 背景 → 过程 → 数据 → 踩坑 → 成本 → 我现在怎么做）或
   **观点**（现象 → 拆穿 → 几类人 → 我的做法 → 故事 → 收尾）。等用户确认。
3. **出提纲**：3 个标题（标公式类型，见 `skill-global-creator/references/content-system.md`）、开头 150 词怎么写、
   小标题、表格/截图位规划（每 300–400 词一个视觉锚点）、[📝] 位置。等用户确认。
4. **写**，存 `outputs/<主题>/blogger.md`（Markdown，可用 ## 小标题和表格）。
5. **去 AI 味**：`skill-global-deai` →
   `python skills/shared/scripts/deai_check.py check --file outputs/<主题>/blogger.md --platform blogger --title "<标题>"`
6. **交付**：正文 + 3 个标题 + 搜索描述（≤150 字符）+ labels 建议（3–5 个，沿用已有分类）+ 封面图提示词 + 自查摘要。
7. **用户填完 [📝][📊][🖼] 后建草稿**（脚本内置 content_guard + `--mode publish` 去AI自查，任何 fail 都不会提交）：
   ```bash
   python skills/builtin/skill-blogger-publisher/scripts/blogger.py draft --file outputs/<主题>/blogger.md \
     --title "<标题>" --labels "AI Tools,Workflows" --description "<搜索描述>"
   ```
   把返回的 `edit_url` 给用户，让他在后台补图、预览。
8. **用户说“发”才发布**：先不带 `--yes` 打印标题确认是哪篇，用户说对再带：
   ```bash
   python skills/builtin/skill-blogger-publisher/scripts/blogger.py publish --post-id <ID>          # 只打印
   python skills/builtin/skill-blogger-publisher/scripts/blogger.py publish --post-id <ID> --yes    # 真发
   python skills/shared/scripts/cadence_gate.py record --platform blogger --type article --title "<标题>" --url <链接>
   ```
   没有“发”这个字，永远不跑 `--yes`。

## 写法规则

| 项 | 规则 |
|---|---|
| 标题 | ≤60–70 字符（中文 ≤32 字），含具体数字和主关键词，承诺正文兑现 |
| 开头 150 词 | 结果和证据先行；一句话说清读完得到什么；不写 "In this comprehensive guide" |
| 结构 | ## 小标题每 300–400 词一个；表格放真实对比数据；截图位 [🖼 说明] |
| 长度 | 1200–2500 词；低于 600 词容易被判薄内容 |
| 视角 | 第一人称实测；自嘲可以，自夸不行；数据让读者自己得结论 |
| 独家 | ≥15% 是自己的数据、截图、实验、判断 |
| 链接 | 引用来源要链接原始出处；联盟/推广链接加 `rel="sponsored"`，克制 |
| 结尾 | 回扣标题 + 一个真问题；不升华，不 "I hope this helps" |
| SEO | 搜索描述、labels、图片 alt；不堆关键词 |

## 参考文件

| 什么时候读 | 读哪个 |
|---|---|
| 首次配置 OAuth、拿 Blog ID | @references/setup.md |
| SEO 与 Google 垃圾政策要点 | @references/blogger-seo.md |
| 新站节奏 | `skill-global-creator/references/cadence-playbook.md` |
