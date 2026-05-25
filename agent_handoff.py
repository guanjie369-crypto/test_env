#!/usr/bin/env python3
"""
agent_handoff.py — AI Agent 跨会话协作与长效记忆机制

功能：
  save   — 保存断点：归档 Git 状态、关键变量、决策日志到 .agent_session_states.json
           + 生成人类可读的 AGENT_HANDOFF.md 报告
  load   — 无缝继承：将上一轮的记忆注入系统 prompt，实现断点续传
  status — 快速查看上次断点摘要

用法：
  python3 agent_handoff.py save    [--message "可选备注"]
  python3 agent_handoff.py load
  python3 agent_handoff.py status

依赖：Python ≥ 3.8，git。
"""

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── 路径配置 ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
STATE_FILE = PROJECT_ROOT / ".agent_session_states.json"
HANDOFF_FILE = PROJECT_ROOT / "AGENT_HANDOFF.md"
CLAUDE_MD = PROJECT_ROOT / "CLAUDE.md"

TZ_OFFSET = "+08:00"  # 北京时间


def _now() -> str:
    """返回带时区的 ISO 时间戳。"""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _tz_now() -> str:
    """返回本地时间字符串 YYYY-MM-DD HH:MM。"""
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def _run(cmd: list[str], timeout: int = 15) -> str:
    """运行 shell 命令并返回 stdout，失败返回空字符串。"""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _git_status() -> dict[str, Any]:
    """收集 Git 状态信息。"""
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"
    recent_log = _run(["git", "log", "--oneline", "-5"]) or "(no commits)"
    diff = _run(["git", "diff", "--stat"]) or "(clean)"
    untracked = _run(["git", "ls-files", "--others", "--exclude-standard"]) or "(none)"
    return {
        "branch": branch,
        "recent_commits": recent_log.split("\n"),
        "uncommitted_changes": diff.split("\n"),
        "untracked_files": untracked.split("\n"),
    }


def _load_prev_state() -> dict[str, Any]:
    """读取上一次的 state 文件，若不存在返回空字典。"""
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _build_handoff_chain(prev: dict[str, Any]) -> list[str]:
    """维护手递手链：保留最近 8 个 session ID。"""
    chain = prev.get("handoff_chain", [])
    if prev.get("session_id"):
        chain = [prev["session_id"]] + chain
    return chain[:8]


def _inject_into_claude_md(state: dict[str, Any], handoff: str) -> None:
    """
    将交接上下文写入 CLAUDE.md 的 HANDOFF_CONTEXT 区域。
    新会话启动时自动读取该区域，实现断点续传。
    """
    if not CLAUDE_MD.exists():
        return

    marker_start = "<!-- HANDOFF_CONTEXT_START -->"
    marker_end = "<!-- HANDOFF_CONTEXT_END -->"

    content = CLAUDE_MD.read_text(encoding="utf-8")

    # 组装注入内容
    injection = (
        f"<!-- HANDOFF_CONTEXT_START -->\n"
        f"> **上次会话断点**（{_tz_now()}）| 项目：{state.get('project', '?')} | "
        f"阶段：{state.get('task', {}).get('current_phase', '?')}（{state.get('task', {}).get('progress_pct', 0)}%）| "
        f"分支：{state.get('git_status', {}).get('branch', '?')}\n"
        f"\n"
        f"本段由 `agent_handoff.py load` 自动生成。新会话 AI 请读取以下上下文并继承工作。\n"
        f"\n"
        f"### 任务摘要\n"
        f"{state.get('task', {}).get('summary', '无')}\n"
        f"\n"
        f"### 系统配置\n"
        f"- SSD 路径：`{state.get('confirmed_config', {}).get('ssd_path', '?')}`\n"
        f"- 活跃分支：`{state.get('git_status', {}).get('branch', '?')}`\n"
    )

    # Blockers
    blockers = state.get("blockers", [])
    open_bs = [b for b in blockers if b.get("status", "open") == "open"]
    resolved_bs = [b for b in blockers if b.get("status") == "resolved"]
    if open_bs:
        injection += "### 🟡 待处理 Blockers\n"
        for b in open_bs:
            injection += f"- **{b['issue']}** → {b.get('workaround', '待解决')}\n"
        injection += "\n"
    if resolved_bs:
        injection += "### ✅ 已解决\n"
        for b in resolved_bs:
            injection += f"- {b['issue']}\n"
        injection += "\n"

    # 近期 Git 提交
    commits = state.get("git_status", {}).get("recent_commits", [])
    if commits:
        injection += "### 最近提交\n"
        for c in commits[:3]:
            injection += f"- {c}\n"
        injection += "\n"

    # 手递手链
    chain = state.get("handoff_chain", [])
    if chain:
        injection += "### 手递手链\n"
        for sid in chain[:5]:
            injection += f"- `{sid[:8]}...`\n"
        injection += "\n"

    injection += (
        f"AI 请根据以上上下文恢复工作状态。"
        f"如需查看更多细节，可运行 `python3 agent_handoff.py status` 或阅读 `AGENT_HANDOFF.md`。\n"
        f"<!-- HANDOFF_CONTEXT_END -->"
    )

    if marker_start in content and marker_end in content:
        # 替换现有区域
        pre = content.split(marker_start, 1)[0]
        post = content.split(marker_end, 1)[1]
        new_content = pre + injection + post
    else:
        # 追加到文件末尾
        new_content = content.rstrip() + "\n\n" + injection + "\n"

    CLAUDE_MD.write_text(new_content, encoding="utf-8")
    print(f"  ✅ 上下文已注入 CLAUDE.md（新会话自动生效）")


# ══════════════════════════════════════════════════════════════════════════
#  公开 API
# ══════════════════════════════════════════════════════════════════════════


def collect_state(message: str = "") -> dict[str, Any]:
    """收集当前所有断点状态，返回完整的状态字典。"""
    prev = _load_prev_state()
    git_info = _git_status()

    state: dict[str, Any] = {
        "session_id": str(uuid.uuid4()),
        "created_at": _now(),
        "project": PROJECT_ROOT.name,
        "task": {
            "current_phase": prev.get("task", {}).get("next_phase", "未指定"),
            "progress_pct": prev.get("task", {}).get("progress_pct", 0),
            "summary": message or prev.get("task", {}).get("summary", ""),
        },
        "last_decision": prev.get("last_decision", {}),
        "confirmed_config": {
            "ssd_path": str(PROJECT_ROOT),
            "active_branch": git_info["branch"],
            "key_paths": {
                "project_root": str(PROJECT_ROOT),
                "state_file": str(STATE_FILE),
                "handoff_file": str(HANDOFF_FILE),
            },
        },
        "blockers": prev.get("blockers", []),
        "variables": prev.get("variables", {}),
        "handoff_chain": _build_handoff_chain(prev),
        "git_status": git_info,
    }
    return state


def save_checkpoint(message: str = "") -> None:
    """保存完整断点：写 JSON 状态 + Markdown 报告。"""
    state = collect_state(message)
    prev = _load_prev_state()

    # ── 写 .agent_session_states.json ──
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # ── 写 AGENT_HANDOFF.md ──
    blockers_resolved = [
        b for b in state["blockers"] if b.get("status") == "resolved"
    ]
    blockers_open = [
        b for b in state["blockers"] if b.get("status", "open") == "open"
    ]

    lines = [
        f"# Agent Handoff Report — {_tz_now()}",
        "",
        "## 任务状态",
        f"- **当前阶段**：{state['task']['current_phase']}（进度 {state['task']['progress_pct']}%）",
        f"- **会话 ID**：{state['session_id']}",
        f"- **分支**：{state['git_status']['branch']}",
        "",
        "## 已确认的系统配置",
        f"- SSD 工作路径：`{state['confirmed_config']['ssd_path']}`",
        "",
        "## Git 状态",
        "### 最近提交",
    ]
    for c in state["git_status"]["recent_commits"][:5]:
        lines.append(f"- {c}")
    lines.append("")
    if state["git_status"]["uncommitted_changes"] and state["git_status"]["uncommitted_changes"] != [""]:
        lines.append("### 未提交变更")
        for d in state["git_status"]["uncommitted_changes"]:
            lines.append(f"- {d}")
    lines.append("")

    if blockers_resolved:
        lines.append("## 遇到的坑（Blockers）")
        lines.append("### 🔴 已解决")
        for b in blockers_resolved:
            lines.append(f"- **{b['issue']}** → {b.get('workaround', '已修复')}")
        lines.append("")

    if blockers_open:
        if not blockers_resolved:
            lines.append("## 遇到的坑（Blockers）")
        lines.append("### 🟡 待处理")
        for b in blockers_open:
            lines.append(f"- **{b['issue']}** → {b.get('workaround', '尚未找到解决')}")
        lines.append("")

    if state["task"].get("summary"):
        lines.append("## 当前总结")
        lines.append(state["task"]["summary"])
        lines.append("")

    if prev.get("task", {}).get("next_steps"):
        lines.append("## 下一步（Next Steps）")
        for i, step in enumerate(prev["task"].get("next_steps", []), 1):
            lines.append(f"{i}. [ ] {step}")
        lines.append("")

    if state["last_decision"]:
        lines.append("## 最后的决策")
        lines.append(f"- **动作**：{state['last_decision'].get('action', 'N/A')}")
        lines.append(f"- **理由**：{state['last_decision'].get('rationale', 'N/A')}")
        lines.append("")

    if state["handoff_chain"]:
        lines.append("## 手递手链")
        for sid in state["handoff_chain"]:
            lines.append(f"- `{sid[:8]}...`")
        lines.append("")

    if message:
        lines.append("## 备注")
        lines.append(message)
        lines.append("")

    HANDOFF_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 注入到 CLAUDE.md（新会话自动生效）
    _inject_into_claude_md(state, "\n".join(lines))

    print(f"  ✅ 断点已保存：{STATE_FILE}")
    print(f"  ✅ 报告已生成：{HANDOFF_FILE}")


def load_checkpoint() -> None:
    """读取上次断点并注入 CLAUDE.md，新会话启动时自动继承上下文。"""
    if not STATE_FILE.exists():
        print("  ⚠️  未找到历史断点文件，无法恢复。", file=sys.stderr)
        sys.exit(1)

    state = _load_prev_state()
    if not state:
        print("  ⚠️  断点文件损坏或为空。", file=sys.stderr)
        sys.exit(1)

    handoff = HANDOFF_FILE.read_text(encoding="utf-8") if HANDOFF_FILE.exists() else ""

    print(f"\n{'='*60}")
    print("  🔄 跨 Session 记忆恢复 — 注入 CLAUDE.md")
    print(f"{'='*60}")
    print(f"  项目：{state.get('project', '?')}")
    print(f"  阶段：{state.get('task', {}).get('current_phase', '?')}")
    print(f"  进度：{state.get('task', {}).get('progress_pct', 0)}%")
    print(f"  分支：{state.get('git_status', {}).get('branch', '?')}")
    print(f"  上次会话：{state.get('session_id', '?')[:8]}...")
    print(f"{'='*60}\n")

    # 注入到 CLAUDE.md
    _inject_into_claude_md(state, handoff)

    # 如果有待处理的 blockers，醒目提示
    blockers = state.get("blockers", [])
    open_bs = [b for b in blockers if b.get("status", "open") == "open"]
    if open_bs:
        print("  ⚠️  上次会话有未解决的阻塞项：")
        for b in open_bs:
            print(f"     - {b['issue']}")
        print()

    print("  💡 新会话启动后，AI 将自动读取 CLAUDE.md 中的上一轮上下文。")
    print("     也可运行 `cat AGENT_HANDOFF.md` 查看完整报告。\n")


def show_status() -> None:
    """快速查看断点摘要。"""
    if not STATE_FILE.exists():
        print("  ⚠️  无历史断点。")
        return

    state = _load_prev_state()
    if not state:
        print("  ⚠️  断点文件损坏。")
        return

    handoff = HANDOFF_FILE.read_text(encoding="utf-8") if HANDOFF_FILE.exists() else ""

    print(f"\n📋 断点摘要")
    print(f"{'─'*40}")
    print(f"  项目：{state.get('project', '?')}")
    print(f"  会话 ID：{str(state.get('session_id', '?'))[:8]}...")
    print(f"  创建时间：{state.get('created_at', '?')}")
    print(f"  当前阶段：{state.get('task', {}).get('current_phase', '?')}")
    print(f"  进度：{state.get('task', {}).get('progress_pct', 0)}%")
    print(f"  分支：{state.get('git_status', {}).get('branch', '?')}")
    print(f"  手递手链长度：{len(state.get('handoff_chain', []))}")

    blockers = state.get("blockers", [])
    open_count = sum(1 for b in blockers if b.get("status", "open") == "open")
    resolved_count = len(blockers) - open_count
    print(f"  Blockers：{open_count} 待处理 / {resolved_count} 已解决")

    if state.get("variables", {}).get("pending_tasks"):
        pending = state["variables"]["pending_tasks"]
        print(f"\n  待办项：")
        for t in pending[:5]:
            print(f"    - {t}")
        if len(pending) > 5:
            print(f"    ... 还有 {len(pending)-5} 项")
    print()


# ══════════════════════════════════════════════════════════════════════════
#  入口
# ══════════════════════════════════════════════════════════════════════════

def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "save":
        msg = sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "--message" else ""
        save_checkpoint(msg)
    elif command == "load":
        load_checkpoint()
    elif command == "status":
        show_status()
    else:
        print(f"未知命令: {command}", file=sys.stderr)
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
