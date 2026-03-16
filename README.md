# EverMemOS — Claude Code Integration

EverMemOS gives Claude Code persistent memory across sessions. Every conversation is stored, indexed, and automatically retrieved on the next session start.

Memories are stored on the [0G decentralized storage network](https://0g.ai) — encrypted with a key only you hold, persisted on-chain so data survives hardware failures, and never held by any central server.

---

## Quick Start

### Prerequisites

| | Linux | macOS |
|---|---|---|
| OS | Ubuntu / Debian / RHEL / CentOS | macOS 12+ |
| Python 3.8+ | typically pre-installed | typically pre-installed |
| [Homebrew](https://brew.sh) | — | [Appendix A](#appendix-a-installing-homebrew-on-macos) |
| Docker 20.10+ | auto-installed if missing | [Appendix B](#appendix-b-installing-docker-on-macos) |
| [uv](https://astral.sh/uv/) | auto-installed if missing | auto-installed via brew if missing |
| RAM / Disk | 4 GB RAM, 10 GB free disk | 4 GB RAM, 10 GB free disk |

> **Windows users:** use WSL2 and follow the Linux path.

### 1. Install

```bash
git clone https://github.com/EverMind-AI/EverMemOS.git
cd EverMemOS
./install.sh
```

### 2. Configure

`install.sh` creates a `.env` file from the template. Open it and fill in your API keys:

```bash
LLM_API_KEY=...           # any OpenAI-compatible provider (OpenRouter, DeepSeek, xAI, etc.)
VECTORIZE_API_KEY=...     # embedding service key (e.g. DeepInfra)
RERANK_API_KEY=...        # rerank service key (e.g. DeepInfra)
ZEROG_WALLET_KEY=...      # 0G-funded EVM wallet private key
```

> `LLM_BASE_URL` and `LLM_MODEL` in `.env` let you point to any OpenAI-compatible endpoint. The defaults work with [OpenRouter](https://openrouter.ai).

### 3. Start

```bash
./start_service.sh
```

> If Claude Code is already running, **restart it** now so the newly registered hooks take effect.

### 4. Use Claude Code normally

EverMemOS runs silently in the background — no extra commands needed. You get:

- **Cross-session memory** — Claude remembers past conversations even after restarting
- **Auto-injected context** — relevant memories are automatically added to Claude's context at the start of each session
- **Automatic storage** — every message you send, every Claude reply, and every tool call result is stored without any action on your part
- **Automatic search** — when you reference past events or ask about something discussed before, Claude automatically searches your memory store and incorporates the results

### 5. Stop & Resume

```bash
./stop_service.sh
./start_service.sh --restart   # always use --restart when resuming
```

> `--restart` tells the script to wait for the kv-server to re-sync your memory stream from the blockchain before starting the backend. This can take **a few minutes** if your history is large.

### 6. Uninstall

```bash
./uninstall.sh   # WARNING: permanently deletes all stored memories
```

---

## What It Looks Like in Practice

**Session 1** — you tell Claude something:

> *"I've decided to use PostgreSQL for the new project. We also agreed the API should be RESTful, not GraphQL."*

Claude stores this automatically. You close Claude Code and come back the next day.

**Session 2** — a fresh session, but Claude remembers:

> *"What database did we decide on for the new project?"*
>
> Claude: *"You decided on PostgreSQL. You also noted the API should be RESTful rather than GraphQL."*

**Another example** — referencing past work mid-session:

> *"Continue where we left off with the auth module."*
>
> Claude automatically searches your memory, finds the previous discussion about the auth module, and picks up from there — without you having to re-explain the context.

---

## Advanced Usage

### What `install.sh` does

`install.sh` sets up everything automatically:

- **Installs Python dependencies** into `.venv/` — the Python packages EverMemOS needs to run.
- **Installs Claude Code skills** — copies a small script into `~/.claude/skills/`. Claude Code looks in this folder for "skills": tools it can call during a conversation. The EverMemOS skill lets Claude search your memory store on demand.
- **Registers hooks** — adds entries to `~/.claude/settings.json`. Hooks are shell commands that Claude Code automatically runs at specific moments (e.g. when you submit a prompt, when a session starts). EverMemOS uses hooks to store every message you send and every reply Claude gives, so nothing is lost.
- **Generates `.0g_secrets`** — creates a stream ID and encryption key for the 0G KV storage layer. Think of the stream ID as a unique address for your personal memory store on the 0G decentralized network, and the encryption key as the password that protects it. These are generated once and reused across restarts.
- **Downloads `zgs_kv`** — installs the 0G KV server binary into `0g_kv_server/`. This is a lightweight node that connects your machine to the 0G storage network, allowing EverMemOS to persist memories on-chain.

### What `start_service.sh` starts

Three things start in order:

1. **kv-server** (`zgs_kv`) — the 0G KV storage node. It syncs your stream from the blockchain so your memories are available locally.
2. **Docker containers** — MongoDB, Elasticsearch, Milvus, and Redis. These are the databases that power memory indexing and search.
3. **EverMemOS backend** — a REST API on `http://localhost:1995` that Claude Code talks to for storing and retrieving memories.

### Why `--restart` is required on resume

When you stop and restart EverMemOS, the kv-server needs to re-sync your existing memory stream from the 0G blockchain before the backend can safely read from it. The `--restart` flag tells the start script to wait for that sync to complete. Depending on the size of your history, this can take anywhere from a few seconds to several minutes. On a first-time start (fresh stream, nothing to sync), the flag is not needed.

### How memory works during a Claude Code session

| Moment | What happens |
|--------|-------------|
| Session start | Recent memories are fetched and injected into Claude's context |
| Every prompt you send | Your message is stored |
| Every Claude reply | Claude's response is stored |
| Every tool call | Tool name and result are stored |
| Question references past context | Claude automatically searches memory and incorporates the results |

### Verify everything is running

```bash
# All 6 Docker containers should show "Up" or "healthy"
docker compose ps

# EverMemOS backend health check
curl http://localhost:1995/health
# → {"status": "healthy", ...}

# kv-server process
pgrep -a zgs_kv
```

### Logs

| Component | Command |
|-----------|---------|
| EverMemOS backend | `tail -f $(ls -t logs/evermemos_*.log \| head -1)` |
| kv-server | `tail -f $(ls -t 0g_kv_server/kv_*.log \| head -1)` |
| Hook activity | `tail -f ~/.claude/logs/hook_user_prompt.log` |

Quick health check across all components:

```bash
LOG=$(ls -t logs/evermemos_*.log | head -1)

# Messages received and memories extracted
grep "Received memorize request\|Memory request processing completed" "$LOG" | tail -20

# Search calls (what Claude searched for)
grep "Received search request" "$LOG" | tail -10

# Activity by sender type
grep "sender_name=User"              "$LOG" | wc -l
grep "sender_name=Claude (Response)" "$LOG" | wc -l
grep "sender_name=Claude (Tool)"     "$LOG" | wc -l
```

### Uninstall — what gets removed

```bash
./uninstall.sh
```

Permanently removes:
- Docker containers and all volumes (MongoDB, Elasticsearch, Milvus, Redis data)
- `.0g_secrets`, `.env`, `.venv/`
- EverMemOS skills from `~/.claude/skills/`
- EverMemOS hooks from `~/.claude/settings.json`

> After uninstalling, running `install.sh` again generates a new stream ID and encryption key — **previous memories are not recoverable**.

### Typical workflow

```
install.sh
  └─ fill in .env
       └─ start_service.sh                        ← first time (fresh stream)
            └─ use Claude Code normally
                 └─ stop_service.sh               ← data preserved
                      └─ start_service.sh --restart   ← resume (re-sync chain)
                           └─ ...
                                └─ uninstall.sh   ← removes everything
```

---

## Appendix: macOS Dependency Installation

### Appendix A: Installing Homebrew on macOS

[Homebrew](https://brew.sh) is the standard package manager for macOS. It is required for the `install.sh` script to auto-install `uv` on macOS.

```bash
# 1. Install Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. Add Homebrew to your shell profile (Apple Silicon Macs)
echo >> ~/.zprofile
echo 'eval "$(/opt/homebrew/bin/brew shellenv zsh)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv zsh)"
```

> **Intel Macs:** Homebrew installs to `/usr/local/bin`, which is already in PATH. Step 2 is not needed.

Verify the installation:

```bash
brew --version
```

### Appendix B: Installing Docker on macOS

Docker Desktop for macOS includes both Docker Engine and Docker Compose.

```bash
# Install Docker Desktop via Homebrew (recommended)
brew install --cask docker

# Launch Docker Desktop
open -a Docker
```

Wait for the Docker whale icon to appear in the menu bar and show **"Docker Desktop is running"** before proceeding.
