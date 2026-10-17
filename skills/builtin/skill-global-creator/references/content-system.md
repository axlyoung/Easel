# AI 赛道内容体系（X / LinkedIn / Blogger）+ 游戏（Reddit）

## 选题：两边对上才是题

和 WorkBuddy 的选题法一样：**需求侧**是今天大家在聊什么（`global_topics.py`），**供给侧**是你手里有什么别人没有的。
AI 新闻人人都在转，转述没有价值；有价值的是“这件事 × 我的实测/数据/判断”。

每条候选题四项：

| 项 | 内容 |
|---|---|
| 方向 | 一句话，带具体对象（哪个模型、哪个工具、哪个功能） |
| 需求侧 | 来源、几个平台同时在聊、多久之前 |
| 独家 | **空着让用户填**：我测过吗？我有截图/数据吗？我的判断和主流哪里不同？ |
| 平台 | X 快评 / LinkedIn 职场视角 / Blogger 深度实测 / 不写 |

独家栏填不出来的题不写，或者先去做实验再写。

## AI 创作者的 5 个内容支柱

| 支柱 | 例子 | 最适合 | 占比 |
|---|---|---|---|
| 实测 | “用 Claude Code 重构 4 万行老项目，11 小时，改了什么、坏了什么” | Blogger 母本 → X 串推 | 30% |
| 工作流 | “我每天用 AI 处理邮件的 3 步，省 40 分钟” | LinkedIn、X | 25% |
| 成本账 | “一个月 AI 订阅花了 $187，砍掉哪 2 个” | X、Blogger | 15% |
| 事件判断 | 新模型发布、行业新闻 + 我的一个具体判断（不是摘要） | X（快）、LinkedIn（次日） | 20% |
| 踩坑与失败 | “AI agent 删了我的测试数据库，复盘” | 全平台，失败帖最容易被转 | 10% |

一周节奏示例（S1 阶段）：Blogger 1 篇实测 → 拆 1 条 X 串推 + 1 条 LinkedIn 帖；另外 X 每天 1 条短观点，
LinkedIn 再补 1–2 条工作流帖。事件判断随热点插入，但不挤掉当周的实测。

## 一稿多发怎么拆（以一篇 Blogger 实测为例）

| 平台 | 从哪一点开头 | 怎么收 |
|---|---|---|
| Blogger | 结果数字 + 我为什么做这个实验 | 回扣标题 + 一个真问题 |
| X 串推 | 最反常识的那个结果（第 1 条必须能单独成立） | 最后一条一句判断；链接放最后一条或回复 |
| LinkedIn | 这件事对“做这份工作的人”意味着什么 | 一个问读者实际做法的问题 |
| X 单推（隔几天） | 文中一个小细节或一张截图 | 不收，说完就走 |

## Reddit 游戏内容

| 类型 | 例子 | 合适的版（以版规为准） |
|---|---|---|
| 心得/评测 | “Finished X after 60h. The thing nobody mentions is…” | r/patientgamers（游戏需发售 1 年以上）、对应游戏的版 |
| 讨论 | “Which game made you change how you play other games?” | r/gaming、r/truegaming（要求长文深度） |
| 推荐请求/回答 | 回答别人的推荐帖是最好的养号方式 | r/gamingsuggestions、r/ShouldIbuythisgame |
| 硬件/设置 | 具体配置 + 帧数 + 设置截图 | r/pcgaming、r/SteamDeck、r/buildapc |
| 新闻讨论 | 新闻 + 自己的看法 | r/Games（只收新闻/讨论，规则严）、r/pcgaming |

游戏内容必须来自用户自己真玩过的经历：游玩时长、平台、具体关卡/机制。AI 只负责组织结构和改语气，
**不编游玩经历**，素材不够就标 [📝 你在这里卡了多久/用的什么配置]。

## 标题公式（英文平台）

| 类型 | 公式 | 例 |
|---|---|---|
| 数据型 | 动作 + 具体数字 + 结果 | I let an AI agent run my inbox for 14 days. It sent 3 emails I'd never send. |
| 反差型 | 预期 vs 实际 | Everyone says RAG is dead. My support bot's accuracy says otherwise. |
| 否定型 | 否定一个常见做法 + 证据 | Stop writing longer prompts. Mine got 2x better at half the length. |
| 痛点型 | 具体痛点 + 解法 + 数字 | Spent $187/mo on AI tools. Here's the $40 stack I kept. |

不要标题党（“This changes everything”“You won't believe”）：高点击低停留会被判为诱导点击。
标题承诺的数字，正文必须兑现。
