---
name: skill-x-publisher
description: >
  X（Twitter）AI 方向内容：写单推、串推（thread）、引用评论、回复，按新号阶段控节奏，过去 AI 味自查后
  生成预填发帖链接由人点发布。当用户说“发推/发 X/写推文/写个 thread/串推/推特/回复这条推/X 涨粉”时使用。
layer: publish
version: 0.1.0
profile_aware: true
---

# X 发布（AI 方向）

> 原创帖：配了官方 API 凭据就**自动定时发**（人只审内容），没配就产出定稿 + 预填链接让人点发。不用浏览器自动化、不用第三方定时工具。
> 节奏以 `cadence_gate.py` 为准，平台专家知识见 @references/x-playbook.md。

## 输入

- 素材：用户的实测、截图、数据、一个判断（没有就拒写，告诉他素材从哪来：自己用 AI 干过的活、踩过的坑、花过的钱）
- 形式：默认**单推**；素材有 3 个以上必须展开的硬细节才写串推（≤5 条）。X 的风格是短，能一句说完不写两句。
- 画像：`easel-profiles/<画像>/`，语言按 preferences

## 执行

1. **查阶段**：`python skills/shared/scripts/cadence_gate.py check --platform x --type post`（串推用 `--type thread`）。
   block / wait 先告诉用户，再决定是存草稿排期还是继续写。
2. **写**（规则见下表和 playbook），存 `outputs/<主题>/x.md`；串推每条之间用单独一行 `---`。
3. **去 AI 味**：按 `skill-global-deai`，然后
   `python skills/shared/scripts/deai_check.py check --file outputs/<主题>/x.md --platform x`，exit 1 就改。
4. **交付**：定稿 + 自查摘要 + 2 个备选首条（首条决定一切）+ 建议发布时间。`deai_check` 会卡：图 >1 张判 fail，单推 >200 加权字提醒再砍。
5. **用户填完 [📝][💬] 后过闸**：
   ```bash
   python skills/shared/scripts/deai_check.py check --file outputs/<主题>/x.md --platform x --mode publish
   python skills/shared/scripts/content_guard.py scan --file outputs/<主题>/x.md
   python skills/shared/scripts/cadence_gate.py check --platform x --type thread [--link]
   python skills/builtin/skill-global-creator/scripts/compose_link.py x --file outputs/<主题>/x.md --open
   ```
6. **登记**：用户贴回链接后 `cadence_gate.py record --platform x --type thread --title "<首条前 50 字>" --url <链接>`。
   回复别人也记 `--type reply`（养号期回复是主要动作，配额要算）。

## 自动发帖（官方 API，人只审内容）

X 允许用官方 API 定时发**自己的原创帖**（自动回复别人仍不允许，回复走 `skill-x-reply`）。

| 步 | 谁 | 命令 |
|---|---|---|
| 资讯点评：每天 19:30 抓 AI 热点 → 抓英文原文摘要 → DeepSeek 写短评 → 自动过检 → 进队列 | 自动 | `x_news.py run`（launchd） |
| 个人实战：用户给素材 → 写 2–3 个版本 → 用户挑 | AI 写，人挑 | `x_post.py add --file <稿> --kind personal` |
| 审稿：用户在对话里说“发 #4”/“发 A” | 人 | `x_post.py approve --id N`（自动排到下一个空闲时段） |
| 到点过三道闸 → 官方 API 发出 → 资讯帖把来源链接挂在第一条回复 → 自动登记 | 自动 | `x_post.py run`（launchd 每 15 分钟） |

```bash
python skills/builtin/skill-x-publisher/scripts/x_post.py check          # 凭据自检
python skills/builtin/skill-x-publisher/scripts/x_post.py queue          # 看队列（draft 待审 / approved 已排）
python skills/builtin/skill-x-publisher/scripts/x_post.py approve --id 4 # 通过
python skills/builtin/skill-x-publisher/scripts/x_news.py pick           # 今天能挑的 AI 资讯
```

- **内容配比**：资讯点评 + 个人实战交替，别连着三天都是资讯（没有亲身内容的号涨不了粉）。
- **防编造**（资讯稿脚本硬卡）：只许用标题和原文摘要里的事实；短评里的数字必须在来源里出现过；不许写亲身经历；
  空话（more competition / one to watch…）判不过；同一条新闻的中英文版只写一次，4 天内不重复。
- **时段**：默认北京时间 21:15（美东早 9 点）前后随机 ±12 分钟；S2 起加 09:30。起步期 1 条/天。
- **凭据**：`.env` 的 `X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_SECRET`，用户自己填，不进对话。
  App 权限必须是 Read and write，改权限后要重新生成 Access Token。
- `X_AUTO_APPROVE=1` 时资讯稿不等人审直接排队；默认关，先人审一两周、质量稳定再开。

## 写法规则

| 项 | 规则 |
|---|---|
| 第一句 | 就是结论、最反常识的数字或一个冲突，不铺垫。"I let Claude Code refactor 40k lines. It took 11 hours and broke 1 thing I didn't expect." |
| 单推 | 一个点；越短越好，**最好 ≤200 加权字**（中文 ≤100 字），上限 280；删到删不动为止 |
| 串推 | 少用；3–5 条；第 1 条单独成立；每条一个具体细节；最后一条一句判断 |
| 图片 | **一帖最多 1 张**（串推整串也只 1 张），只放真能替代一段字的：截图、数据图、一张流程图；没有就不放 |
| 视角 | 第一人称，像跟同行说话；可以有立场，可以说“我错了” |
| 外链 | S0 不放；S1 起放串推最后一条或首条的回复里 |
| hashtag | 0–1 个；不放热门 hashtag 蹭流量 |
| @ | 只 @ 真正相关的人（你测的工具官方号、你回应的作者），≤2 个 |
| 格式 | 纯文本；X 不渲染 Markdown；列表用换行，别用 emoji 当符号 |
| 结尾 | 一句判断或一个具体问题；不写 "Follow for more"、"RT if you agree" |
| 语言 | 一个号只用一种主语言 |

## 回复（养号期最重要的动作）

> 每天的回复任务（目标名单、今日任务单、发前查重、登记）走 **`skill-x-reply`**；下面是写法要点。

- 回复对象：同领域 5k–100k 粉、近 24 小时发帖、内容你真有话说的。
- 一条好回复 = 补一个数据 / 一个反例 / 一次自己的实测 / 一个精确的追问。一句最好，最多两句，不配图。
- 不回 "Great point!"、"This 🔥"、"Couldn't agree more"；同一句话不回给两个人。
- 回复也要过 `deai_check.py --platform x`（短文本只看指纹词和诱导即可）。

## 参考文件

| 什么时候读 | 读哪个 |
|---|---|
| 算法信号、Day 0 清单、发帖时间、封号行为、串推结构模板 | @references/x-playbook.md |
| 爬坡总表（四平台） | `skill-global-creator/references/cadence-playbook.md` |
