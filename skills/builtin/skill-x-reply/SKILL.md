---
name: skill-x-reply
description: >
  X（Twitter）每日回复任务：维护要长期互动的目标账号名单，按新号阶段给出今天回几条、回谁、分几个时段；
  为用户贴来的推文写 2 个回复备选，发前查去 AI 味、和历史回复是否重复、同一个人今天回了几次、节奏闸门，
  生成官方回复链接由人点发，发完登记。当用户说“回复别人/X 回复任务/今天回谁/帮我回这条推/养号回复/
  加个对标账号/目标名单/自动回复/回复队列”时使用。
layer: publish
version: 0.2.0
profile_aware: true
---

# X 每日回复任务

> 新号在 X 上的原创帖几乎没人看，**前 30 天涨粉主要靠回复**：在同领域账号下面，赶在帖子刚发出时，
> 写一条比原帖多一点信息的回复，让对方和他的读者点进你的主页。回复也是最容易被判“机器号”的动作：
> 千篇一律的 “Great point!”、短时间回几十条、同一句话回给不同的人。本技能把这件事做成每天一张任务单，
> 并在发出去之前把这些风险挡住。

## 一次性准备：目标名单

```bash
cd <项目根>
python skills/builtin/skill-x-reply/scripts/x_reply.py targets add --handle @xxx --tier core --topic "ai agents"
python skills/builtin/skill-x-reply/scripts/x_reply.py targets list
```

- 10–30 个账号。`core` 5–10 个：同领域、5k–100k 粉、经常发帖、评论区有来回讨论的；其余 `normal`。
- 不要只盯百万粉大号：回复会被淹没，而且大号评论区机器号最多，混在里面反而危险。
- 每月看一次：对方很少回复、或者你的回复从没带来主页访问的，换掉。
- 帮用户找人时，从他已经在读的人开始问，再看这些人经常和谁互动。不要凭空编账号名。

## 每天的流程

1. **出任务单**：
   ```bash
   python skills/builtin/skill-x-reply/scripts/x_reply.py today
   ```
   内容包括：当前阶段、今天建议回几条（S0 5–10 条，S1 10–20 条，S2 起 15–30 条）、已经回了几条、
   分到三个时段各几条，以及按“最久没回”排好的主页链接。今天已经回过的人会被跳过。
2. **用户去看主页，把想回的推文贴过来**：链接加原文，截图也行。只回近 24 小时的帖子，最好是对方刚发 15–60 分钟内的。
3. **写 2 个回复备选**，存 `outputs/x-replies/<日期>/<对方>-<推文ID>.md`，写法见下表。用户没有相关经历的，就用“精确追问”的写法，不编实测。
4. **发前检查**（exit 0 才能发；1 = 改稿，3 = 等一等，4 = 不能发）：
   ```bash
   python skills/builtin/skill-x-reply/scripts/x_reply.py check --file <回复.md> --to @对方
   ```
   这一步检查的内容：去 AI 味自查（X 规则）、空泛附和、太短、@ 了第三人、和近 50 条历史回复的相似度（≥60% 算重复）、
   同一个人今天回复的次数（S0–S1 1 次，S2 起 2 次）、今日回复上限、两条回复间隔 3 分钟，以及养号期不能带链接。
5. **用户确认后生成回复链接**，由用户点开自己发：
   ```bash
   python skills/builtin/skill-x-reply/scripts/x_reply.py link --url <推文链接> --file <回复.md> --open
   ```
6. **用户说“发了”就登记**（写入 publish-log，更新这个人的最后回复时间；以后查重也靠这份记录）：
   ```bash
   python skills/builtin/skill-x-reply/scripts/x_reply.py record --url <推文链接> --file <回复.md>
   ```
   有人回复了用户的推，用户再回过去，也要按同样流程检查和登记（`--to` 填对方）。这类互动权重最高，优先回。

## 自动运行（DeepSeek 起草，人点发送）

每天 08:35 / 12:05 / 20:05 自动跑一轮（macOS launchd）：找帖 → DeepSeek 写 2 个备选 → 自动过检 → 进当天队列 → 弹系统通知。
人只做最后一步：`x_auto.py review` 逐条看、选稿、点 Reply、按 y 登记。

```bash
python skills/builtin/skill-x-reply/scripts/x_auto.py check        # 配置自检（脱敏）
python skills/builtin/skill-x-reply/scripts/x_auto.py install      # 装定时；uninstall 卸载，status 看日志
python skills/builtin/skill-x-reply/scripts/x_auto.py run          # 手动跑一轮（--dry-run 只看会起草哪些）
python skills/builtin/skill-x-reply/scripts/x_auto.py review       # 逐条确认发送并登记
```

- **为什么不全自动发**：X 自动化规则不允许程序自动给别人发回复，新号一查就是机器号。自动化停在“点发送”之前。
- **目标名单**：维护在 `outputs/x-replies/watchlist.md`（★ = core），改完跑 `x_auto.py watchlist import`。
- **没有 API 时**：每个时段弹通知（配了 `X_REPLY_LIST_URL` 会顺便打开你的 X 列表），人扫一眼挑 3–4 条，
  `x_auto.py inbox add <链接>...` 丢进来**马上起草**（不等下一个定时）。用户在对话里甩推文链接时，Agent 直接跑这条命令。
- **帖子来源**：配了 `X_BEARER_TOKEN` 就自动拉目标名单 12 小时内的新帖和别人对你的回复；没配就处理
  `outputs/x-replies/inbox.md`（一行一个推文链接，可附原文；没附时用官方 oEmbed 取正文）。用户在对话里甩来推文链接时，追加进收件箱即可。
- **频度**：当天剩余配额平均分到还没过的时段，队列里有没发的稿就少起草；同一个人一天的上限、两条间隔 3 分钟在 review 时由 `check` 再卡一次。
  优先级：别人回你的 > 收件箱 > core 目标 > 其他，同级里越新越先。
- **字数**：越短越像真人。每条随机抽长度档：极短 30–70 / 短 70–130 / 中 130–190 加权字（35% / 50% / 15%，养号期不抽中档），
  避免条条一样长。一句最好，最多两句；回复不配图。
- **不编经历**：DeepSeek 只能引用 `outputs/x-replies/my-notes.md` 里写过的真实经历和数据；这个文件是空的时，
  稿子里出现 “I tested / I've seen / for me” 一类说法会被打回重写，只能用追问、反对理由或公开事实。
- **自动过检**：每条稿走 `x_reply.check_reply`（去 AI 味、空泛附和、@、链接、和历史回复查重）+ 破折号 + 长度 + 本轮内互相查重；
  不过就带意见重写一次，还不过就丢掉。抽奖、广告、政治、事故类帖子由模型判 skip。

## 好回复的 5 种写法

| 写法 | 例（原帖：“Agents are finally good enough for real refactors.”） |
|---|---|
| 补数据 | "Ran one on a 40k-line Django app last week. 31 of 34 changes were fine, the 3 bad ones were all in migrations." |
| 亲身反例 | "Held up for me until it hit generated code. Then it 'fixed' files that get overwritten on every build." |
| 精确追问 | "Did you let it run the test suite between steps, or only at the end? That was the whole difference for me." |
| 补工具或步骤 | "What made it work for me: a CLAUDE.md that lists the 5 directories it must never touch." |
| 不同意，但给理由 | "Refactors yes, renames across services no. It missed every string-based import in our config." |

- 一句最好，最多两句，像同行之间随口一说。第一句就是信息，不要先夸。回复不配图。
- 不写：Great point / So true / This 🔥 / Couldn't agree more / Thanks for sharing。
- 不放链接，不 @ 第三人，不说“我也写过一篇”。主页和置顶会替你做转化。
- 不和人吵架。不同意的时候给一个具体理由就停，对方反驳了，最多再回一次。
- 一个人一天最多回 1 次（S2 起 2 次）。不要把他当天的每条帖子都回一遍。

## 和其他技能的关系

- 节奏和上限来自 `skills/shared/scripts/cadence_gate.py`（`type=reply`）。回复和原创帖分开计数，回复不占发帖配额。
- 原创帖和串推用 `skill-x-publisher`；平台知识见 `skill-x-publisher/references/x-playbook.md`。
- 去 AI 味规则见 `skill-global-deai`。回复很短，重点看指纹词、破折号和空泛附和。
