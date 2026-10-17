# Easel SKILL 元数据

| 字段 | 值 |
|------|-----|
| **SKILL 名称** | skill-x-reply |
| **所属层** | publish |
| **来源** | Easel 自研 |
| **功能描述** | X 每日回复任务：目标名单、今日任务单、发前检查（去AI/重复/同人次数/节奏）、回复链接、登记 |
| **核心脚本** | scripts/x_reply.py（纯标准库；复用 shared/scripts/cadence_gate.py 与 deai_check.py） |
| **profile_aware** | true |
| **自包含** | 是 |

> 创建时间: 2026-10-12
> 用途: 新号养号期的主要动作是回复；把“回谁、回几条、会不会被判机器号”固化成脚本

## 设计说明

- 只生成官方 reply intent 链接（`x.com/intent/post?in_reply_to=<id>&text=...`），人点发布，不做自动回复。
- 查重：回复原文存进 publish-log 的 notes，新回复与近 50 条做 difflib 相似度，≥0.6 判重复。
- 目标名单存 `outputs/_analytics/x-targets.json`；回复记录 tag `target:@handle`。
