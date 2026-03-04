# EverMemOS — Claude Code Integration

EverMemOS gives Claude Code persistent memory across sessions. Every conversation is stored, indexed, and automatically retrieved on the next session start.

---

## Prerequisites

- Python 3.12
- Docker 20.10+ (auto-installed if missing)
- [uv](https://astral.sh/uv/) package manager (auto-installed if missing)
- 4 GB RAM

---

## Step 1 — Install

```bash
git clone https://github.com/EverMind-AI/EverMemOS.git
cd EverMemOS
./install.sh
```

`install.sh` does the following once:
- Installs Python dependencies into `.venv/`
- Copies EverMemOS skills to `~/.claude/skills/`
- Adds hooks to `~/.claude/settings.json`
- Generates `.0g_secrets` (stream ID + encryption key for 0G KV storage)

After it finishes, **fill in `.env`** with your API keys:

```bash
# Required
LLM_API_KEY=...           # LLM provider key (for memory extraction)
VECTORIZE_API_KEY=...     # Embedding service key
RERANK_API_KEY=...        # Rerank service key
ZEROG_WALLET_KEY=...      # 0G-funded EVM wallet private key
```

You also need the `zgs_kv` binary — download from
[0g-storage-kv releases](https://github.com/0glabs/0g-storage-kv/releases)
and place it at `0g_kv_server/zgs_kv`.

> If Claude Code is already running, **restart it** so the newly added hooks take effect.

---

## Step 2 — Start

**First time** (right after `install.sh`):
```bash
./start_service.sh
```

**Subsequent starts** (after a `stop_service.sh`):
```bash
./start_service.sh --restart
```

The `--restart` flag tells the script that the kv-server has an existing stream ID and needs to re-sync data from the blockchain before the backend is ready. Without it, the script assumes a fresh stream and skips the sync wait.

This starts:
1. **kv-server** (`zgs_kv`) — 0G KV storage node, syncs blockchain
2. **Docker containers** — MongoDB, Elasticsearch, Milvus, Redis
3. **EverMemOS backend** — REST API on `http://localhost:1995`

### Verify everything is running

```bash
# All 6 Docker containers should show "Up" or "healthy"
docker-compose ps

# EverMemOS backend health check
curl http://localhost:1995/health
# → {"status": "healthy", ...}

# kv-server process
pgrep -a zgs_kv
```

---

## Step 3 — Use Claude Code normally

Once started, EverMemOS works automatically in the background:

- **Session start**: recent memories are injected as context into Claude
- **Every prompt**: your message is stored
- **Every response**: Claude's reply is stored
- **Every tool call**: tool name + result is stored

No extra commands needed.

---

## Stop & Restart

```bash
./stop_service.sh
./start_service.sh --restart
```

Stops the backend, Docker containers, and kv-server.
**All stored data is preserved.** The `--restart` flag is required on resume so the script waits for the kv-server to finish re-syncing the existing stream from the blockchain.

---

## Uninstall

```bash
./uninstall.sh
```

**Warning: this permanently deletes all stored memories.**

Specifically removes:
- Docker containers + all volumes (MongoDB, Elasticsearch, Milvus, Redis data)
- `.0g_secrets`, `.env`, `.venv/`
- EverMemOS skills from `~/.claude/skills/`
- EverMemOS hooks from `~/.claude/settings.json`

> After uninstall, if you run `install.sh` again, a new stream ID and encryption key are generated — previous data is not recoverable.

---

## Logs

| What | Command |
|---|---|
| EverMemOS backend | `tail -f $(ls -t logs/evermemos_*.log | head -1)` |
| kv-server | `tail -f $(ls -t 0g_kv_server/kv_*.log \| head -1)` |
| Hook activity | `tail -f ~/.claude/logs/hook_user_prompt.log` |

Quick health check across all components:

```bash
# Backend: messages received and memories extracted
LOG=$(ls -t logs/evermemos_*.log | head -1)
grep "Received memorize request\|Memory request processing completed" "$LOG" | tail -20

# Search calls (what Claude searched for)
grep "Received search request" "$LOG" | tail -10

# Per sender type
grep "sender_name=User"             "$LOG" | wc -l
grep "sender_name=Claude (Response)" "$LOG" | wc -l
grep "sender_name=Claude (Tool)"    "$LOG" | wc -l
```

---

## Typical Workflow

```
install.sh
  └─ fill in .env
       └─ start_service.sh                   ← first time (fresh stream)
            └─ use Claude Code normally
                 └─ stop_service.sh           ← data preserved
                      └─ start_service.sh --restart  ← resume (re-sync chain)
                           └─ ...
                                └─ uninstall.sh  ← removes everything
```
