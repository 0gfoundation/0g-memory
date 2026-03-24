#!/bin/bash
# 诊断脚本：查看 EverMemOS OpenClaw 插件的运行情况
#
# 用法：
#   bash tests/test_openclaw.sh          # 运行所有三个检查
#   bash tests/test_openclaw.sh search   # 只看 query + search 结果
#   bash tests/test_openclaw.sh inject   # 只看注入内容（需重启 gateway 后生效）
#   bash tests/test_openclaw.sh store    # 只看存入 EverMemOS 的内容

LOG=/tmp/evermemos_openclaw.log
SEP="════════════════════════════════════════════════════════════════════"

run_search() {
    echo ""
    echo "$SEP"
    echo "  2. Per-message search：每条 query + search 结果"
    echo "$SEP"
    python3 - <<'EOF'
import json, urllib.request, urllib.parse
from pathlib import Path

BASE_URL = "http://localhost:1995"
USER_ID  = "openclaw_user"
GROUP_ID = "project_/home/op/.openclaw/workspace_openclaw_user"
LOG      = "/tmp/evermemos_openclaw.log"

def search_api(query, top_k=5):
    params = urllib.parse.urlencode({
        "user_id": USER_ID,
        "group_id": GROUP_ID,
        "retrieve_method": "hybrid",
        "top_k": top_k,
        "memory_types": "episodic_memory,event_log,foresight",
        "query": query,
    })
    with urllib.request.urlopen(f"{BASE_URL}/api/v1/memories/search?{params}", timeout=10) as r:
        return json.loads(r.read())

def format_api_results(query):
    """回退：用当前数据库重新搜索（注意：反映当前DB状态，非历史状态）"""
    try:
        groups = search_api(query).get("result", {}).get("memories", [])
        all_mems = []
        for g in groups:
            if isinstance(g, dict):
                for mems in g.values():
                    if isinstance(mems, list):
                        all_mems.extend(mems)
        if not all_mems:
            return "  (no results)"
        lines = ["  ⚠️  injected_text 不在日志中，以下为当前DB重新搜索的结果（非历史精确值）："]
        for i, m in enumerate(all_mems, 1):
            ts2     = (m.get("start_time") or m.get("timestamp") or m.get("created_at", "?"))[:19]
            subject = m.get("subject", "")
            body    = m.get("episode") or m.get("summary", "")
            text    = (subject + ("\n    " + body if body else "")).strip()
            lines.append(f"  [{i}] {ts2}  {text[:280]}")
        return "\n".join(lines)
    except Exception as e:
        return f"  ⚠️  API error: {e}"

# ── 从日志配对 "User message buffered" 与 "Injection summary" ──────────────
# 按 channelId 匹配：遇到 buffered 时暂存 query，遇到 Injection summary 时配对输出
pending = {}   # channelId -> {"ts": ..., "query": ...}
pairs   = []   # [{"ts", "query", "injected_text"}]

for line in Path(LOG).read_text().splitlines():
    try:
        d = json.loads(line)
    except:
        continue
    msg  = d.get("msg", "")
    data = d.get("data", {})
    ch   = data.get("channelId")

    if msg == "User message buffered for before_prompt_build" and ch:
        pending[ch] = {"ts": d["ts"], "query": data.get("content", "")}

    elif msg == "Injection summary" and ch and ch in pending:
        entry = pending.pop(ch)
        pairs.append({
            "ts":            entry["ts"],
            "query":         entry["query"],
            "injected_text": data.get("injected_text"),  # None if old log
        })

sep = "─" * 70
for p in pairs:
    ts = p["ts"][11:19]
    q  = p["query"]
    print(f"\n{sep}")
    print(f"[{ts}] 📥 Query: {q}")
    print(sep)
    if p["injected_text"]:
        print(p["injected_text"])
    else:
        print(format_api_results(q))
EOF
}

run_inject() {
    echo ""
    echo "$SEP"
    echo "  1. 注入内容（injected_text 需重启 gateway 后生效）"
    echo "$SEP"
    grep '"Injection summary"' "$LOG" | python3 -c "
import sys, json
for line in sys.stdin:
    d = json.loads(line)
    data = d.get('data', {})
    ts   = d['ts'][11:19]
    text = data.get('injected_text', '')
    print(f\"[{ts}] qry_ok={data.get('query_injected')}\")
    if text:
        print(text)
    else:
        print('  (injected_text 不在日志中，请重启 gateway 后生效)')
    print('─' * 70)
"
}

run_store() {
    echo ""
    echo "$SEP"
    echo "  3. 所有存入 EverMemOS 的内容（用户输入 + 工具调用 + AI 回复）"
    echo "$SEP"
    grep -E '"Storing assistant response"|"Storing tool call"|"User message buffered for before_prompt_build"' \
        "$LOG" | python3 -c "
import sys, json
for line in sys.stdin:
    d = json.loads(line)
    msg  = d.get('msg', '')
    ts   = d['ts'][11:19]
    data = d.get('data', {})
    sep = '─' * 70
    if msg == 'User message buffered for before_prompt_build':
        content = data.get('content', '')
        print(f\"\n[{ts}] 📥 USER  | ch={data.get('channelId','')}\")
        print(content)
        print(sep)
    elif msg == 'Storing assistant response':
        content = data.get('content', '')
        print(f\"\n[{ts}] 🤖 AI    | len={data.get('length')} | group={data.get('groupId','')}\")
        print(content)
        print(sep)
    elif msg == 'Storing tool call':
        content = data.get('content', '')
        print(f\"\n[{ts}] 🔧 TOOL  | tool={data.get('tool')} | group={data.get('groupId','')}\")
        print(content)
        print(sep)
"
}

# ── 入口 ──────────────────────────────────────────────────────────────────────

if [ ! -f "$LOG" ]; then
    echo "❌ 日志文件不存在：$LOG"
    exit 1
fi

case "${1:-all}" in
    search)  run_search ;;
    inject)  run_inject ;;
    store)   run_store  ;;
    all)
        run_inject
        run_search
        run_store
        ;;
    *)
        echo "用法: $0 [search|inject|store|all]"
        exit 1
        ;;
esac
