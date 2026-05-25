---
name: session-handoff
description: AI Agent 跨会话手递手交接 — 保存断点或将上一轮记忆注入当前会话，实现断点续传
metadata:
  type: skill
  trigger: session-handoff, handoff
---

# session-handoff — 跨会话手递手交接

## 触发词

用户说「handoff」「session-handoff」「交接」「保存断点」「恢复上下文」「断点续传」时，执行本技能。

## 工作流程

### 保存断点（保存当前上下文快照）

1. 确认当前会话的决策、进度、 blockers 等关键状态
2. 运行：
   ```bash
   python3 agent_handoff.py save --message "本轮完成/未完成的工作摘要"
   ```
3. 输出完成后告知用户：
   - `.agent_session_states.json` 已保存（机器可读）
   - `AGENT_HANDOFF.md` 已生成（人类可读）

### 恢复断点（在新会话中继承上下文）

1. 在新会话中运行：
   ```bash
   python3 agent_handoff.py load
   ```
2. 脚本会将上次的完整上下文（包括 blockers、配置、决策链）注入到 AI 的系统提示中
3. 根据恢复的信息继续工作

### 快速查看状态

```bash
python3 agent_handoff.py status
```

## 关键设计原则

- **JSON + MD 双写**：兼顾机器解析和人类阅读
- **手递手链**：每个新 session 记录前一个 session_id，形成可追溯的上下文面包屑（最长 8 跳）
- **Blockers 追踪**：区分「已解决」和「待处理」，新会话醒目提示未解决的阻塞项
- **Git 状态快照**：每次保存自动记录分支、最近提交、未提交变更，避免丢失工作上下文
- **无侵入**：只在需要时执行交接，不干扰正常开发流程

## 使用场景

| 场景 | 操作 |
|------|------|
| 复杂任务未完成，需关闭当前会话 | `handoff save` |
| 新会话打开，继续上次任务 | `handoff load` |
| 不确定是否还有未完成的上下文 | `handoff status` |
| 切换窗口/IDE | 先 `save` 再 `load` |
