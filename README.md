# EverMemOS — Claude Code Integration

EverMemOS gives Claude Code persistent memory across sessions. Every conversation is stored, indexed, and automatically retrieved on the next session start.

Memories are stored on the [0G decentralized storage network](https://0g.ai) — encrypted with a key only you hold, persisted on-chain so data survives hardware failures, and never held by any central server.

---

## Quick Start

### Prerequisites

| | Ubuntu | macOS |
|---|---|---|
| OS | Ubuntu 20.04+ | macOS 12+ |
| Python 3.8+ ¹ | typically pre-installed | typically pre-installed |
| [Homebrew](https://brew.sh) | — | [Appendix A](#appendix-a-installing-homebrew-on-macos) |
| Docker 20.10+ | auto-installed if missing | [Appendix B](#appendix-b-installing-docker-on-macos) |
| [uv](https://astral.sh/uv/) | auto-installed if missing | auto-installed via brew if missing |
| RAM / Disk | 4 GB RAM, 10 GB free disk | 4 GB RAM, 10 GB free disk |

> ¹ Python 3.8+ is required only to run the installer. The application itself requires Python 3.12, which **uv downloads and manages automatically** — you do not need to install 3.12 yourself.

### 1. Install

```bash
git clone https://github.com/0gfoundation/0g-memory.git
cd 0g-memory
./install.sh
```

### 2. Configure

`install.sh` creates a `.env` file from the template. Open it and fill in your API keys:

```bash
LLM_API_KEY=...           # any OpenAI-compatible provider (OpenRouter, DeepSeek, xAI, etc.)
VECTORIZE_API_KEY=...     # embedding service key — if using OpenAI (default), same as LLM_API_KEY
RERANK_API_KEY=...        # rerank service key — requires a rerank-capable provider (default: DeepInfra)
ZEROG_WALLET_KEY=...      # EVM wallet private key funded with 0G testnet tokens (see Appendix C)
```

> **Note on `RERANK_API_KEY`:** OpenAI does not provide a reranking API. The default rerank provider is **[DeepInfra](https://deepinfra.com)** — sign up, copy your API key, and paste it here. The default model is `Qwen/Qwen3-Reranker-4B`. `RERANK_BASE_URL` and `RERANK_MODEL` in `.env` let you point to any compatible rerank endpoint (e.g. a self-hosted vLLM instance).

> `LLM_BASE_URL` and `LLM_MODEL` in `.env` let you point to any OpenAI-compatible endpoint. The defaults use **OpenAI directly** (`gpt-4o-mini`). To switch to [OpenRouter](https://openrouter.ai) or another provider, update `LLM_BASE_URL`, `LLM_MODEL`, and `LLM_API_KEY` accordingly.

### 3. Start

```bash
./start_service.sh
```

> **First run only:** Docker will pull ~4 GB of images (Elasticsearch, MongoDB, Milvus, Redis). This can take **5–15 minutes** depending on your connection. The terminal will show download progress — it is not hanging.

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

## Appendix: Setup Guides

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

### Appendix C: Getting Your `ZEROG_WALLET_KEY`

`ZEROG_WALLET_KEY` is the 64-character hex private key of an EVM wallet. EverMemOS uses it to write your encrypted memories to the [0G decentralized storage network](https://0g.ai). This project uses the **0G Galileo Testnet**, so you need a wallet funded with free testnet tokens.

#### Step 1 — Get a wallet (MetaMask)

If you do not have MetaMask installed, download it from [metamask.io](https://metamask.io) and create a new wallet.

#### Step 2 — Add the 0G Galileo Testnet to MetaMask

In MetaMask, go to **Settings → Networks → Add a network** and enter:

| Field | Value |
|-------|-------|
| Network name | 0G-Galileo-Testnet |
| RPC URL | `https://evmrpc-galileo.0g.ai` |
| Chain ID | `16602` |
| Currency symbol | `0G` |
| Block explorer | `https://chainscan-galileo.0g.ai` |

#### Step 3 — Get free testnet tokens

Ask the 0G admin to send testnet tokens to your wallet address.

#### Step 4 — Export the private key from MetaMask

1. Open MetaMask and click your **Account** icon (top right)
2. Click the **⋮** menu to the right of your account name → **Account Details**
3. Click **Show private key**
4. Enter your MetaMask password to confirm
5. Select a network (e.g. **0G-Galileo-Testnet**)
6. Click the **copy icon** on the right to copy the 64-character hex key

Paste that value into `.env`:

```bash
ZEROG_WALLET_KEY=<your 64-character hex private key here>
```

> ⚠️ **Security reminder:** never share your private key, never commit it to version control. Anyone with this key has full control of the wallet.
