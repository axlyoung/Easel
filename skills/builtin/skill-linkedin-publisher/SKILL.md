---
name: skill-linkedin-publisher
description: >
  LinkedIn（领英）AI 方向内容：写职场视角的文本帖、文档轮播帖大纲、评论，按新号阶段控节奏（发帖间隔、
  邀请上限、外链放评论），过去 AI 味自查后生成预填发帖链接由人点发布。当用户说“发领英/发 LinkedIn/
  写个领英帖/LinkedIn 涨粉/领英怎么发/加人”时使用。
layer: publish
version: 0.1.0
profile_aware: true
---

# LinkedIn 发布（AI 方向）

> 新号阶段**人手发布**；LinkedIn 明确禁止自动化插件（自动加人/发消息/访问主页），一旦被检出会限制甚至封号。
> 节奏以 `cadence_gate.py` 为准，平台知识见 @references/linkedin-playbook.md。

## 输入

- 素材：用户在工作里用 AI 的真实经历、数据、截图、一个判断。没有就拒写。
- 形式：文本帖 / 文档帖（PDF 轮播）/ 评论别人的帖子
- 画像与语言按 `easel-profiles/<画像>/`

## 执行

1. **查阶段**：`python skills/shared/scripts/cadence_gate.py check --platform linkedin --type post`
2. **写**，存 `outputs/<主题>/linkedin.md`；外链单独写在 `outputs/<主题>/linkedin-first-comment.md`。
3. **去 AI 味**：`skill-global-deai` →
   `python skills/shared/scripts/deai_check.py check --file outputs/<主题>/linkedin.md --platform linkedin`
4. **交付**：定稿 + 第一条评论（放链接）+ 自查摘要 + 2 个备选开头（前 210 字符）+ 建议发布时间（读者时区的周二到周四 8–10 点）。
5. **过闸并发布**：
   ```bash
   python skills/shared/scripts/deai_check.py check --file outputs/<主题>/linkedin.md --platform linkedin --mode publish
   python skills/shared/scripts/content_guard.py scan --file outputs/<主题>/linkedin.md
   python skills/shared/scripts/cadence_gate.py check --platform linkedin --type post
   python skills/builtin/skill-global-creator/scripts/compose_link.py linkedin --file outputs/<主题>/linkedin.md --open
   ```
   提醒用户：发完立刻把链接贴进第一条评论，接下来 60 分钟守着回评论。
6. **登记**：`cadence_gate.py record --platform linkedin --type post --title "<首句>" --url <链接>`；
   加好友邀请也记 `--type invite`（每天上限按阶段）。

## 写法规则

| 项 | 规则 |
|---|---|
| 开头（前 210 字符） | “…see more”之前唯一能看到的部分。用一个结果、一个反常识的数字或一个具体场景。不写 "I'm thrilled/excited/humbled"。 |
| 视角 | 第一人称，职业视角：这件事对做这份工作的人意味着什么；可以承认自己错了 |
| 长度 | 800–1600 字符最好，上限 3000 |
| 段落 | 2–4 句一段；可以有一两句单独成行强调，但**不要通篇一句一行**（broetry 是 AI 和营销号的标志） |
| 格式 | 纯文本，不渲染 Markdown；列表用换行 + 简单符号（• 或 1.），不用 emoji 当列表符 |
| 外链 | 正文不放，放第一条评论 |
| hashtag | 0–3 个，放末尾 |
| @ | ≤3 个，只 @ 真正相关的人或公司 |
| 结尾 | 一个读者能回答的具体问题（“What's the one task you still won't hand to an agent?”），不写 "Agree?"、"Thoughts?" |
| 禁 | 求赞、“评论 YES 我私信你”、engagement pod、编造头衔和成绩 |

## 文档帖（PDF 轮播）

适合工作流、对比、清单类。8–12 页，每页一个点、大字、少字。本技能出每页文案大纲；
出图用 `card-design` / `infographic` 等制作层技能，导出 PDF 后由用户上传。封面页 = 标题 + 一个数字。

## 评论别人（养号期主要动作）

每天 3–10 条，对象是你想进入的圈子里的人。好评论 = 补充一个自己的经验或数据，2–4 句，比 "Great post!" 长。
评论同样过 `deai_check.py --platform linkedin`。

## 参考文件

| 什么时候读 | 读哪个 |
|---|---|
| 算法、Day 0 资料、邀请规则、封号行为、帖子模板 | @references/linkedin-playbook.md |
| 爬坡总表 | `skill-global-creator/references/cadence-playbook.md` |
