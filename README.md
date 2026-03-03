# EverMemOS — Claude Code Integration

EverMemOS gives Claude Code persistent memory across sessions. Every conversation is stored, indexed, and automatically retrieved on the next session start.

---

## Prerequisites

- Python 3.10+
- Docker 20.10+ (auto-installed if missing)
- [uv](https://astral.sh/uv/) package manager
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

```bash
./start_service.sh
```

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
```

Stops the backend, Docker containers, and kv-server.
**All stored data is preserved.** Running `./start_service.sh` again resumes from where you left off.

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
| EverMemOS backend | `tail -f data/evermemos.log` |
| kv-server | `tail -f 0g_kv_server/kv.log` |
| Hook activity | `tail -f ~/.claude/logs/hook_user_prompt.log` |

Quick health check across all components:

```bash
# Backend: messages received and memories extracted
grep "Received memorize request\|Memory request processing completed" data/evermemos.log | tail -20

# Search calls (what Claude searched for)
grep "Received search request" data/evermemos.log | tail -10

# Per sender type
grep "sender_name=User"            data/evermemos.log | wc -l
grep "sender_name=Claude (Response)" data/evermemos.log | wc -l
grep "sender_name=Claude (Tool)"   data/evermemos.log | wc -l
```

---

## Typical Workflow

```
install.sh
  └─ fill in .env
       └─ start_service.sh
            └─ use Claude Code normally
                 └─ stop_service.sh      ← data preserved
                      └─ start_service.sh ← resume, history still available
                           └─ ...
                                └─ uninstall.sh  ← removes everything
```
