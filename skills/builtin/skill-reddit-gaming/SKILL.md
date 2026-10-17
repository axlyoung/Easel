---
name: skill-reddit-gaming
description: >
  Reddit 游戏内容：新号养号（只评论攒 karma）、选版读版规、写讨论帖/心得帖/推荐回答，按 karma 与账号年龄
  控节奏（同版冷却、9:1 自推比例），去 AI 味自查，生成预填发帖链接由人点发布。当用户说“发 Reddit/发红迪/
  reddit 游戏/去哪个版发/攒 karma/reddit 养号/会不会被 shadowban”时使用。只做游戏方向。
layer: publish
version: 0.1.0
profile_aware: true
---

# Reddit 发布（游戏方向）

> Reddit 是四个平台里对新号最严的：大量版块的 AutoModerator 按账号年龄和 karma 静默删帖，带链接和发得快
> 会触发站点级垃圾过滤甚至 shadowban。所以本技能**先养号、后发帖、全程人手发**。
> 平台知识见 @references/reddit-playbook.md，版块清单见 @references/gaming-subs.md。

## 输入

- 用户自己真玩过的经历：游戏名、平台、游玩时长、具体的关卡/机制/配置/感受。**AI 不编游玩经历**，不够就标 [📝]。
- 目标：评论攒 karma / 发讨论帖 / 回答推荐帖 / 发心得
- 画像：游戏画像（不要和 AI 创作者画像混用，不往 AI 博客导流）

## 执行

1. **查阶段**（每周先更新一次 karma）：
   ```bash
   python skills/shared/scripts/cadence_gate.py account --platform reddit --karma <当前 karma>
   python skills/shared/scripts/cadence_gate.py check --platform reddit --type post --sub r/<版名>
   ```
   S0 潜水期 `check --type post` 一定 block：这时只做第 2 步的评论。
2. **养号评论**（S0 主要工作，之后也一直做）：
   - 用 `global_topics.py subreddit --sub <版> --t day` 看版里在聊什么，挑用户真有经验的帖子。
   - 每条评论 2–5 句，补一个具体信息（时长、配置、哪一关、哪个设置）；不复述原帖，不 "Great post!"。
   - 存 `outputs/<主题>/reddit-comments.md`，逐条过 `deai_check.py --platform reddit`，用户自己贴。
   - 每条贴完登记：`cadence_gate.py record --platform reddit --type comment --sub r/<版> --title "<一句话>"`
3. **发帖前读版规**：打开版块侧栏（Rules）和置顶帖，记下：是否允许文字帖、要求的 flair、标题格式、
   自推规则、是否禁止 AI 生成内容、最低 karma/账号年龄（多数不公开，被删就说明不够）。写进 `outputs/<主题>/sub-rules.md`。
4. **写帖**，存 `outputs/<主题>/reddit-<版名>.md`，标题单独给。规则见下表。
5. **去 AI 味**：`skill-global-deai` →
   `python skills/shared/scripts/deai_check.py check --file outputs/<主题>/reddit-<版名>.md --platform reddit --title "<标题>"`
6. **过闸并发布**：
   ```bash
   python skills/shared/scripts/deai_check.py check --file <稿> --platform reddit --title "<标题>" --mode publish
   python skills/shared/scripts/content_guard.py scan --file <稿>
   python skills/shared/scripts/cadence_gate.py check --platform reddit --type post --sub r/<版名> [--link] [--promo]
   python skills/builtin/skill-global-creator/scripts/compose_link.py reddit --file <稿> --sub <版名> --title "<标题>" --open
   ```
   提醒：在页面上选好 flair；发完 1–2 小时内回评论。
7. **登记**：`cadence_gate.py record --platform reddit --type post --sub r/<版名> --title "<标题>" --url <链接>`（自推加 `--promo`）。
8. **24 小时后自查**：无痕窗口打开帖子链接，看不到 = 被过滤，按 playbook 处理，**不要重发同一帖**。

## 写法规则

| 项 | 规则 |
|---|---|
| 标题 | 具体、口语、像玩家说话："60 hours into Silksong and the difficulty spike at Act 2 is not what people say"；不全大写、不标题党、不加 emoji |
| 开头 | 直接说事；不写 "Hey fellow gamers!"、"Hi everyone, long time lurker" |
| 长度 | 150–600 词；r/truegaming 这类深度版可以更长 |
| 格式 | Markdown 可用；短帖不要多级标题和加粗小标题（像 AI 写的报告）；TL;DR 放最后一行可以 |
| 口吻 | 玩家对玩家，可以小写、可以 imo/tbh；有立场，承认自己的偏好 |
| hashtag | **0**（Reddit 不用 hashtag） |
| 外链 | 新号不带；之后只在允许的版，且自推 ≤10% |
| 结尾 | 一句话，或问大家的具体经验："Anyone else bail at the same boss?" |
| 禁 | 求 upvote、同一内容同时发多个版、短链、小号互赞、ban 后开新号回同一版、版规禁止时发 AI 写的内容 |

## 参考文件

| 什么时候读 | 读哪个 |
|---|---|
| karma、AutoMod、shadowban、9:1、版主关系、恢复 | @references/reddit-playbook.md |
| 游戏版块清单与各版特点 | @references/gaming-subs.md |
| 爬坡总表 | `skill-global-creator/references/cadence-playbook.md` |
