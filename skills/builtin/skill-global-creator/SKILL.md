---
name: skill-global-creator
description: >
  海外自媒体总编排：AI 方向内容发 X / LinkedIn / Blogger，游戏内容发 Reddit。从选题雷达、定题、
  一稿多发（Blogger 长文做母本 → X 串推 → LinkedIn 帖 → Reddit 讨论帖）、去 AI 味自查，到新号防 ban
  节奏闸门、人手发布与回填记录，整条链。当用户说“发推/发 X/发领英/发 LinkedIn/发 Blogger/发 Reddit/
  海外自媒体/出海账号/AI 自媒体/今天发什么/排一周海外内容/新号怎么起步/会不会被 ban”时使用。
layer: plan
version: 0.1.0
profile_aware: true
---

# 海外自媒体总编排（AI → X / LinkedIn / Blogger；游戏 → Reddit）

> 流程与规则参考 WorkBuddy「公众号爆文专家」：人只在两处拍板（**定题、审稿**），发布那一下永远人点；
> 没素材不写、不编数字不编经历、去 AI 味 + 自查全绿才交稿。这里把它扩到四个海外平台，
> 并加了一道公众号没有的闸：**新号发帖节奏**。

## 一条链（9 步）

| 步 | 干什么 | 谁 | 用什么 | 交付 |
|---|---|---|---|---|
| 1 | 摸账号阶段 | AI 查 | `cadence_gate.py plan` | 每个平台在哪一阶段、今天/本周还能发几条 |
| 1b | X 回复任务（每天） | AI 排，人发 | `skill-x-reply` 的 `x_reply.py today` | 今天回谁、回几条、分几个时段 |
| 2 | 找题 | AI 找，**人定** | `scripts/global_topics.py ai` / `subreddit` | 5 条候选，每条带来源、几个平台在聊、你能加的独家（空着让人填） |
| 3 | 收素材 | 人给 | 亲身使用记录、截图、数据、踩坑 | 素材 + 独家点（≥15%） |
| 4 | 写母本 | AI 写 | Blogger 长文（`skill-blogger-publisher`） | MD 正文、3 个标题、[📝][📊][🖼] 待补位 |
| 5 | 拆多平台 | AI 改 | `skill-x-publisher` / `skill-linkedin-publisher` / `skill-reddit-gaming` | 每平台一个原生稿，不是复制粘贴 |
| 6 | 去 AI 味 + 自查 | AI 改，脚本数 | `skill-global-deai` + `deai_check.py` | 每份稿的自查报告，全绿才往下 |
| 7 | **审稿** | **人** | 填掉 [📝][💬][📊]，改成自己的话 | 定稿 |
| 8 | 过闸发布 | AI 过闸，**人点发布** | `deai_check --mode publish` → `content_guard` → `cadence_gate check` → Blogger 草稿 / 预填发帖链接 | 已发链接 |
| 9 | 登记 + 回查 | AI | `cadence_gate.py record`；3 天后回填数据 | publish-log、下周节奏 |

清晰单平台任务（“把这段改成推文”）直接跳到第 5 步，但 **6、8 两步永远不跳**。

## 账号定位（默认两套画像）

| 画像 | 平台 | 定位 | 语言 |
|---|---|---|---|
| AI 创作者 | X、LinkedIn、Blogger | 一个真在用 AI 干活的人：工具实测、工作流、踩坑、成本账、行业事件的个人判断 | 由画像 `preferences.md` 定，默认英文；中文 AI 圈也可以，选一种别混发 |
| 游戏玩家 | Reddit | 真玩家：游戏心得、对比、冷门推荐、讨论 | 英文 |

两套画像**不要互相导流**：Reddit 游戏号不推 AI 博客，否则就是典型的“营销号”画像，ban 得最快。
画像读 `easel-profiles/<画像>/`，平台阶段数据读 `outputs/_analytics/intl-accounts.json`。

## 第 1 步：先摸阶段（每次排期前必做）

```bash
cd <项目根>
python skills/shared/scripts/cadence_gate.py plan                 # 四个平台一起看
python skills/shared/scripts/cadence_gate.py stages               # 爬坡表
# 第一次用：登记注册日期（Reddit 再登记 karma，每周更新一次）
python skills/shared/scripts/cadence_gate.py account --platform x --created 2026-10-12 --handle @xxx
python skills/shared/scripts/cadence_gate.py account --platform reddit --created 2026-10-12 --karma 1
```

阶段决定能做什么，**不是内容决定**。S0 的 Reddit 号再好的稿子也只能留着，先去评论。
完整的爬坡节奏、封号触发点、被限流后怎么恢复，见 @references/cadence-playbook.md。

## 第 2 步：选题

```bash
python skills/builtin/skill-global-creator/scripts/global_topics.py ai --lang en --hot-only --n 15
python skills/builtin/skill-global-creator/scripts/global_topics.py ai --keyword agent,claude,cursor,openai
python skills/builtin/skill-global-creator/scripts/global_topics.py subreddit --sub pcgaming,Games,patientgamers --t week
```

- 需求侧：WorkBuddy 每日清单（免费，80+ 源跨平台聚类），几个平台同时在聊的优先。
- 交付 5 条，每条四项：方向、来源与热度、**你能加的独家（空着让用户填）**、适合哪个平台。
- 独家栏空着的题不建议写：没有亲身使用、数据或判断的 AI 新闻转述，在 X 和 LinkedIn 上是零分内容。
- 选题方法与 AI 赛道内容支柱见 @references/content-system.md。

## 第 4–5 步：一稿多发矩阵

| | Blogger（母本） | X | LinkedIn | Reddit（仅游戏） |
|---|---|---|---|---|
| 视角 | 第一人称实测 | 第一人称、更冲、更短 | 第一人称职业视角：我在工作里怎么用 | 玩家对玩家，口语 |
| 长度 | 1200–2500 词 | 单推最好 ≤200 加权字（上限 280）/ 串推少用，≤5 条；最多 1 张图；回复一两句、不配图 | 800–1600 字符最好，≤3000 | 150–600 词 |
| 格式 | 小标题、表格、截图 | 纯文本，不渲染 Markdown | 纯文本短段落，不渲染 Markdown | Markdown，少用标题 |
| 外链 | 正常 | 新号不带；之后放最后一条或回复 | 正文不带，放第一条评论 | 新号不带；之后只在允许的版 |
| 结尾 | 回扣标题 + 真问题 | 一句判断或一个问题 | 一个具体问题 | 一句话收，或问大家的经验 |
| 禁 | 关键词堆砌、批量 AI 文 | hashtag 刷屏、@ 一串大号 | “I'm thrilled”、求赞、engagement pod | hashtag、求 upvote、营销腔 |

拆稿不是缩写：每个平台要从**它的读者最关心的那一点**重新开头。
母本写完先存 `outputs/<主题>/blogger.md`，其余存 `x.md` / `linkedin.md` / `reddit-<版名>.md`。

## 第 6 步：去 AI 味（强制）

按 `skill-global-deai` 走三件套（减法删指纹词、加法只标 [💬] 位、补问句），然后：

```bash
python skills/shared/scripts/deai_check.py check --file outputs/<主题>/x.md --platform x
python skills/shared/scripts/deai_check.py check --file outputs/<主题>/linkedin.md --platform linkedin
python skills/shared/scripts/deai_check.py check --file outputs/<主题>/blogger.md --platform blogger --title "<标题>"
```

exit 1 就当场改，改到通过再给用户看。把脚本最后一行自查摘要原样附在交付里。

## 第 8 步：发布前三道闸（顺序固定）

```bash
python skills/shared/scripts/deai_check.py check --file <定稿> --platform <p> --mode publish   # 待补标记必须清零
python skills/shared/scripts/content_guard.py scan --file <定稿>                               # 内部信息泄露 exit 7
python skills/shared/scripts/cadence_gate.py check --platform <p> --type post [--link] [--promo] [--sub r/xx]
```

- `cadence_gate` 返回 `wait`：告诉用户最早什么时候能发（`next_allowed_at`），帮他排进日历，**不劝他硬发**。
- 返回 `block`：照实说原因（比如新号带链接、Reddit karma 不够），给能走的替代做法（链接挪进回复、先去评论攒 karma）。
- 全过后：Blogger 用官方 API 建**草稿**；X / LinkedIn / Reddit 生成预填链接，人点开看一眼自己发：

```bash
python skills/builtin/skill-global-creator/scripts/compose_link.py x --file outputs/<主题>/x.md --open
python skills/builtin/skill-global-creator/scripts/compose_link.py linkedin --file outputs/<主题>/linkedin.md --open
python skills/builtin/skill-global-creator/scripts/compose_link.py reddit --file outputs/<主题>/reddit-pcgaming.md --sub pcgaming --title "<标题>" --open
```

## 第 9 步：登记

用户说“发了”并给出链接后立刻登记（节奏闸门靠这份记录算配额，漏记 = 闸门失效）：

```bash
python skills/shared/scripts/cadence_gate.py record --platform x --type thread --title "<首句>" --url <链接> --profile <画像>
python skills/shared/scripts/cadence_gate.py record --platform reddit --type post --sub r/pcgaming --title "<标题>" --url <链接>
python skills/shared/scripts/cadence_gate.py record --platform reddit --type comment --title "评论 r/Games: <一句话>"   # 评论也记，9:1 比例要用
```

3 天后回查数据，用 `skill-publish-log` 回填 views/likes/comments；值得沉淀的规律问用户后写进画像 `memory.md`。

## 铁律

- 没素材不写；没有亲身使用/数据/判断的题不写。不编数字、不编经历、不编引语、不编“我测了”。
- 每份稿都过 `deai_check`；发布模式下 [📝][💬][📊][🖼] 必须由用户本人填掉。
- 新号阶段 X / LinkedIn / Reddit **一律人手发布**，不用浏览器自动化、不用第三方定时发帖工具代发。
- 不做：多账号矩阵、互赞互关群、engagement pod、买粉、刷量、同一内容同时刷多个版、求赞求转。
- 去 AI 味是写作质量编辑，不是规避平台或版规的 AI 内容披露要求：版规禁止 AI 生成内容的版块，只发用户自己写的内容。
- 对外文案不暴露任何工具和配置痕迹（见 AGENTS 对外发布安全）；但写 AI 工具测评时点名工具是正常内容。

## 参考文件

| 什么时候读 | 读哪个 |
|---|---|
| 新号爬坡、封号触发点、限流恢复、发帖时间 | @references/cadence-playbook.md |
| AI 赛道内容支柱、选题方法、一周内容配比 | @references/content-system.md |
| 各平台写法细则 | `skill-x-publisher` / `skill-linkedin-publisher` / `skill-blogger-publisher` / `skill-reddit-gaming` |
| X 每日回复任务（养号主力） | `skill-x-reply` |
| 去 AI 味规则与自查 | `skill-global-deai` |
