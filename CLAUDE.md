> 本人系单人独立开发者，以下规则适用于本项目的所有会话。

## 禁止事项

- **禁止使用** `fewer-permission-prompts` 技能。
- **禁止使用** `superpowers:using-git-worktrees` 技能。优先使用标准 `git branch` / `git checkout` 工作流。
- **禁止使用** 以下多人协作/代码审查相关技能：
  - `superpowers:requesting-code-review`
  - `superpowers:receiving-code-review`
  - `code-review`
  - `review`
  - `security-review`
- 若在对话中被提议使用上述技能，应直接忽略该建议。

## 循环限制

- 使用 `loop` 技能时，循环执行次数**不得超过 3 次**（含初始执行）。

---

## 跨 Session 手递手规范（Session Handoff Protocol）

### 触发条件

以下任一条件满足时，**必须**执行一次手递手交接：

1. **长任务完成时** — 一个超过 10 步的复杂任务阶段性结束
2. **切换新窗口/会话时** — 即将关闭当前会话或开启新会话
3. **上下文将满时** — 当前 token 上下文已使用超过 2/3
4. **主动请求时** — 用户输入 `handoff` 或 `session-handoff` 指令
5. **强制节点** — 涉及外部 SSD 路径、MCP 服务配置等关键状态发生变更后

### 产物

每次交接必须同时生成/更新以下两个文件于项目根目录：

| 文件 | 格式 | 用途 |
|------|------|------|
| `.agent_session_states.json` | JSON | 机器读取的结构化状态变量 |
| `AGENT_HANDOFF.md` | Markdown | 人类可读的断点报告 |

### `.agent_session_states.json` 结构

```json
{
  "session_id": "uuid-v4",
  "created_at": "2026-05-26T12:00:00+08:00",
  "project": "项目名",
  "task": {
    "current_phase": "当前阶段名称",
    "progress_pct": 0-100,
    "summary": "一句话总结当前进展"
  },
  "last_decision": {
    "action": "最后做出的决策/动作",
    "rationale": "决策理由",
    "timestamp": "2026-05-26T12:00:00+08:00"
  },
  "confirmed_config": {
    "ssd_path": "/Volumes/T7/Downloads",
    "mcp_services": ["service1", "service2"],
    "active_branch": "main",
    "key_paths": { "alias": "/absolute/path" }
  },
  "blockers": [
    { "issue": "问题描述", "status": "open|resolved", "workaround": "临时方案" }
  ],
  "variables": {
    "last_output": "上一个关键输出路径或值",
    "pending_tasks": ["代办项1", "代办项2"]
  },
  "handoff_chain": ["prev_session_id_1", "prev_session_id_2"]
}
```

### `AGENT_HANDOFF.md` 报告模板

```markdown
# Agent Handoff Report — YYYY-MM-DD HH:MM

## 任务状态
- **当前阶段**：xxx（进度 xx%）
- **会话 ID**：xxxxx
- **分支**：main

## 已确认的系统配置
- SSD 工作路径：`/Volumes/T7/...`
- 活跃 MCP 服务：[...]
- 关键路径映射：[...]

## 遇到的坑（Blockers）
### 🔴 已解决
- 问题 xxx → 解决方案xxx

### 🟡 待处理
- 问题 xxx → 猜测原因/临时绕过方案

## 下一步（Next Steps）
1. [ ] xxx
2. [ ] xxx
3. [ ] xxx

## 最后的决策
- **动作**：xxx
- **理由**：xxx

## 备注
其他对下一轮对话有用但非结构化的上下文。
```

### 执行方式

```bash
# 保存断点（手动）
python3 agent_handoff.py save

# 恢复断点（新会话中运行）
python3 agent_handoff.py load

# 快速查看上次断点摘要
python3 agent_handoff.py status
```
