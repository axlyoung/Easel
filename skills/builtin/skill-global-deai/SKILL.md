---
name: skill-global-deai
description: >
  去 AI 味（中英双语，X / LinkedIn / Blogger / Reddit 专用）：deAI 三件套（减法删指纹词、加法只标口语位、
  补反问句）+ 五个结构信号 + 12 项自查，并用 deai_check.py 确定性计数，全绿才交稿。
  当用户说“去 AI 味/去AI化/太像 AI/de-AI/humanize/改得像人写的/发之前查一下”，或任何海外平台稿件交付前使用。
  中文公众号长文仍可用 text-polisher；本技能侧重海外平台与英文。
layer: produce
version: 0.1.0
profile_aware: true
---

# 去 AI 味（海外平台版）

> 规则来自 WorkBuddy 公众号爆文专家的 deAI 三件套和 12 项自查，扩到英文和四个海外平台。
> 核心洞察不变：**AI 最大的指纹不是它多说了什么，是它少说了什么**。真人写东西有立场、有具体的人和时间、
> 有不完美；AI 写的永远干净、平均、三点对齐。去 AI 味不是“改得不像 AI”，是“把 AI 不会有的人味加回去”。

## 什么时候用

- 任何要发到 X / LinkedIn / Blogger / Reddit 的稿子，交付前**强制**跑一遍（总编排 `skill-global-creator` 第 6 步）
- 用户贴来别人写的或 AI 写的初稿，要去 AI 味
- 用户问“这段像不像 AI 写的”

## 怎么跑

1. **定语言和平台**：语言跟画像 `preferences.md` 走；平台决定格式规则（见 @references/self-check.md 的平台表）。
2. **减法**：删指纹词，整句删比换词好（英文表 @references/deai-en.md，中文表 @references/deai-zh.md）。
3. **结构**：查五个信号：只有结论没有动作、整齐三点、模板连接词、空泛升华、标题导语结尾三重复。改法见 self-check.md。
4. **加法**：只标位置，不自己填：
   - `[💬 voice: tbh / ngl / honestly / 说白了…]` 口语位，每篇 1–3 处
   - `[📝 your experience: …]` 亲身经历位，至少 1 处，告诉作者这里需要什么样的经历
   - `[📊 need a number: …]` 模糊形容词换数字的位置
   - `[🖼 screenshot: …]` 截图位（Blogger、LinkedIn、X 都需要真截图）
5. **问句**：按平台补问句（Blogger ≥2，LinkedIn ≥1，X/Reddit 看篇幅），在关键观点处把陈述改成问句。
6. **跑脚本**，exit 1 就当场改，直到通过：

```bash
cd <项目根>
python skills/shared/scripts/deai_check.py check --file <稿件> --platform x|linkedin|blogger|reddit [--title "<标题>"]
```

7. **交付**：改好的全文 + 脚本最后一行的自查摘要 + 一句“下一步：把 [📝][💬][📊] 换成你自己的经历和说法”。
   用户填完后发布前再跑一次 `--mode publish`，待补标记必须清零。

## 必须守住的

- 不编数字、不编经历、不编引语、不编“我测了/我用了三个月”。素材没有就标位置。
- AI 不硬塞俚语（tbh、ngl、lol、说白了），AI 加的口语本身就有 AI 味；只标位置，作者自己决定。
- 不用长破折号（— –），换逗号、句号、冒号或括号。这是英文 AI 文本最显眼的标志之一。
- “It's not X, it's Y / 不是 X 而是 Y”整篇最多 1 处。
- 不用 emoji 做列表符号（🚀 ✅ 👉 💡），不在每段结尾加 emoji。
- 结尾是一句结论或一个真问题，不是升华（“The future is here”“未来已来”），也不是求赞求关注。
- 去 AI 味是写作质量编辑，**不是**用来规避平台或版规对 AI 内容的披露要求。版规要求披露或禁止 AI 内容的地方，照规矩来。

## 参考文件

| 什么时候读 | 读哪个 |
|---|---|
| 英文指纹词、英文结构信号、各平台的 AI 腔 | @references/deai-en.md |
| 中文指纹词、口语词库、反问改写 | @references/deai-zh.md |
| 12 项自查表、平台格式表、自查报告句式 | @references/self-check.md |
