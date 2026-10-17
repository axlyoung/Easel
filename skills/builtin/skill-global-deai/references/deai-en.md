# English de-AI rules

脚本 `deai_check.py` 里的 EN_HARD / EN_SOFT 是这份表的机器版，改一边同步另一边。

## 减法：硬指纹（见到就删，整句删比换词好）

| 类别 | 例 |
|---|---|
| 开场白 | In today's fast-paced world · In an era of · In a world where · Let's dive in · Buckle up · Without further ado · Great question |
| 连接词 | Moreover, · Furthermore, · Additionally, · In conclusion · In summary · It's worth noting · It is important to note · When it comes to · At the end of the day |
| 标志词 | delve · tapestry · testament to · ever-evolving · realm · embark on · a myriad of · navigate the complexities · harness the power · unlock the potential · plays a crucial/pivotal role · stands as · serves as a reminder |
| 吹捧 | game-changer · revolutionize · paradigm shift · cutting-edge · seamless · mind-blowing · This changes everything · The future is here |
| 收尾 | I hope this helps · Stay tuned · Let that sink in · Here's the kicker |
| 领英腔 | I'm thrilled/excited/humbled to announce · Agree? · Thoughts? 单独一行收尾 |
| 对照 | not only … but also · It's not just X, it's Y（最多 1 处） |

## 减法：软指纹（单个不罪，一篇 ≥4 个就是 AI）

leverage（→ use）· robust · landscape · crucial · pivotal · intricate · showcase · comprehensive · elevate · empower ·
streamline · notably · interestingly · essentially · ultimately · vibrant · meticulous · nuanced · holistic · synergy ·
foster · underscore · multifaceted（→ complex）· transformative · insights · journey · boasts · key takeaways · deep dive

## 结构信号（删词删不掉的 AI 味）

| 信号 | 长什么样 | 改法 |
|---|---|---|
| 只有结论没有动作 | "Focus on quality and consistency." | 换成一个人在某个时间做的一件事，带数字："I posted at 9am for 21 days. Replies doubled by week 3." |
| 整齐三点 | 每段三条并列、长度一样；"fast, reliable, and scalable" | 拆成 2 条或 4 条，长短不一，其中一条写成整句 |
| 模板过渡 | Moreover / Additionally / On the other hand 开头 | 整句删，上下段直接接 |
| 空泛升华 | "AI is reshaping how we work." | 换成一个具体判断或一个真问题 |
| 三重复 | 标题、开头、结尾说同一句话 | 开头只给证据，结尾只回扣一个点 |
| 句长太齐 | 每句 15–20 词 | 短句和长句混着来："It broke. Twice. The second time it took my test database with it, which I only noticed because CI went green for the wrong reason." |
| 永远对冲 | "can potentially", "may help to", "it could be argued" | 要么说死，要么说清楚不确定在哪 |
| 过度礼貌 | "Feel free to", "Happy to help" | 删 |

## 加法：口语位（只标不填）

| 平台 | 可以考虑的 | 频率 |
|---|---|---|
| X | honestly · tbh · ngl · wild · lol（少）· "ok so" · "hot take:" | 每条串推 1–2 处 |
| LinkedIn | honestly · "here's the thing I got wrong" · "I'll be blunt" | 每帖 ≤1 处，比 X 克制 |
| Reddit | tbh · ngl · imo · fwiw · lowkey · "idk" · "fr" · 小写开头也正常 | 随意，但别每句都有 |
| Blogger | "I was skeptical" · "here's where it got weird" | 每篇 2–4 处 |

## 各平台的 AI 腔（读者一眼看穿的）

| 平台 | AI 腔 | 真人写法 |
|---|---|---|
| X | 🧵👇 + "Here's what I learned:" + 10 条每条一个 emoji 开头 | 第 1 条就是结论本身，后面每条一个具体细节 |
| X | 每条都是 "1/ … 2/ …" 的教科书结构 | 编号可以有，但内容要有起伏：一条长、一条一句话、一条截图 |
| LinkedIn | 一句一行的“broetry” + "Agree?" | 2–4 句一段，正常段落；问一个具体问题 |
| LinkedIn | "I'm humbled to share…" | 直接说发生了什么 |
| Reddit | "Hey fellow gamers! 🎮" + 加粗小标题 + "TL;DR" + "Hope this helps!" | 直接说事；TL;DR 放最后一行可以 |
| Reddit | 回答像客服："Great question! Here are 5 options:" | "Played both. Go with X if you hate grinding, Y if you don't." |
| Blogger | "In this comprehensive guide, we will explore…" | "I spent 11 hours on this. Here's what broke." |

## 反问句

| 陈述 | 问句 |
|---|---|
| This pricing doesn't make sense. | Who is this pricing actually for? |
| Most people won't read the docs. | When did you last read a changelog end to end? |
| The agent wasn't reliable. | Would you let it touch prod after that? |
