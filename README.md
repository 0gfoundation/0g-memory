# Forever Persistent AI Agent Memory with 0G Storage

This project gives your AI agent memory that lasts forever. Every conversation — every prompt, response, and tool call — is automatically captured and retrieved in future sessions, with no extra effort from you. As a first example, we integrate with AI coding assistants so that your coding agent remembers past decisions, ongoing work, and tool call results across sessions.

Unlike memory systems that rely on local storage, your memories here are stored on the [0G decentralized storage network](https://docs.0g.ai/concepts/storage), encrypted with a key only you hold, and persisted on-chain. Your memory survives hardware failures and is never held by any central server.

Supported clients: **Claude Code**, **OpenCode**, and **OpenClaw**. `install.sh` detects which are installed and sets up the integration automatically.

---

## How it works

Three layers work together to deliver forever-persistent memory:

**1. Automatic capture via client integration**
`install.sh` registers hooks or plugins into your AI coding assistant. From that point on, every prompt you send, every response, and every tool call result is silently captured — no commands needed. For Claude Code and OpenCode, recent memories are injected at the start of each new session automatically. For all supported clients, mid-session semantic search retrieves relevant past context before each reply.

**2. Structured memory extraction via EverMemOS**
Raw conversation data is processed by [EverMemOS](https://github.com/EverMind-AI/EverMemOS/), an open-source memory system that extracts structured episodic memories, indexes them across MongoDB, Elasticsearch, Milvus, and Redis, and supports keyword, vector, hybrid, and agentic retrieval. Memories are namespaced so different projects or sessions don't mix.

**3. Decentralized persistence via 0G storage**
This is what makes memory truly permanent. The memory system writes every memory to the [0G decentralized network](https://docs.0g.ai/concepts/storage) via the 0G storage SDK. Every memory is encrypted with a key generated at install time and stored only on your machine — no one else can read it. A local `zgs_kv` node runs as a read cache, syncing your memory stream from the blockchain so reads stay fast. Because data lives on-chain, it survives local hardware failures — when you restart on a new machine, the kv-server re-syncs your full history from the blockchain and restores everything.

---

## Quick Start

> **Running your own local instance (Scenario A)?** Follow the steps below.
> **Connecting to a remote EverMemOS server (Scenario C)?** Skip to [Appendix E](#appendix-e-scenario-c--remote-client-setup).

### Prerequisites

| Requirement | Ubuntu | macOS |
|---|---|---|
| OS | Ubuntu 20.04+ | macOS 12+ |
| [Claude Code](https://claude.ai/code), [OpenCode](https://opencode.ai), and/or [OpenClaw](https://openclaw.ai) | at least one must be installed | at least one must be installed |
| Python 3.8+ ¹ | typically pre-installed | typically pre-installed |
| [Homebrew](https://brew.sh) | — | [Appendix A](#appendix-a-installing-homebrew-on-macos) |
| Docker 20.10+ | auto-installed if missing | [Appendix B](#appendix-b-installing-docker-on-macos) |
| [uv](https://astral.sh/uv/) | auto-installed if missing | auto-installed via brew if missing |
| 0G testnet wallet ² | [Appendix C](#appendix-c-getting-your-zerog_wallet_key) | [Appendix C](#appendix-c-getting-your-zerog_wallet_key) |
| RAM / Disk | 4 GB RAM, 10 GB free disk | 4 GB RAM, 10 GB free disk |

> ¹ Python 3.8+ is required only to run the installer. The application itself requires Python 3.12, which **uv downloads and manages automatically** — you do not need to install 3.12 yourself.
>
> ² Getting testnet tokens requires emailing the 0G admin and may take **hours to 1–2 days**. **Start this first** before proceeding — see [Appendix C](#appendix-c-getting-your-zerog_wallet_key) for step-by-step instructions. You can complete the rest of the setup while you wait.

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

> **First run only:** Docker will pull ~4 GB of images (Elasticsearch, MongoDB, Milvus, Redis). This can take **5–15 minutes** depending on your connection. The terminal will show download progress — it is not hanging.

```bash
./start_service.sh
```

When startup completes successfully, you will see:

```
============================================================
  ✅ EverMemOS is ready!

  API:      http://localhost:1995
  Logs:     logs/evermemos_<timestamp>.log
============================================================
```

> If Claude Code, OpenCode, or OpenClaw is already running, **restart it** now so the hooks/plugins registered by `install.sh` take effect. For OpenClaw, run `openclaw gateway restart`.

### 4. Verify Memory Works — A 2-Minute Test

The memory backend runs silently in the background. The fastest way to confirm it is working is to plant a few facts and ask your assistant to recall them.

> **OpenClaw users:** memory is scoped per session, so you will verify recall within the **same session** — no restart needed. Send Step A, wait for the reply, then proceed to Step B.

#### Step A — Seed session: tell your assistant specific facts

Open your AI coding assistant and send this message (copy it exactly):

```
I want to record a few project decisions for later:
1. We chose PostgreSQL over MySQL because we need JSONB support for our metadata schema.
2. The auth bug was caused by JWT expiry being set in seconds instead of milliseconds.
3. The API design is RESTful — we explicitly ruled out GraphQL after the team review.
Please confirm you've noted these.
```

Your assistant will acknowledge. You do not need to do anything else — everything is stored automatically.

#### Step B — Verify recall

> **Note:** the verification method differs by client.

**Claude Code / OpenCode:**

Type `/exit` to quit, then reopen your assistant in the **same project directory**. This starts a fresh session. Then send these questions one at a time:

```
What database did we choose, and why?
```
```
What was the root cause of the auth bug?
```
```
What API style did we settle on?
```

**Expected results:**

| Question | Expected answer |
|---|---|
| Database choice | PostgreSQL — needed JSONB support for metadata schema |
| Auth bug | JWT expiry was set in seconds instead of milliseconds |
| API style | RESTful — GraphQL was ruled out after the team review |

If your assistant answers correctly, memory is working.

---

**OpenClaw:**

Cross-session memory retrieval is not currently supported — each session has its own isolated memory space. Instead, verify mid-session search within the **same session** where you sent Step A. Send a follow-up question referencing the facts you planted:

```
What database did we choose, and why?
```

Your assistant should retrieve the answer from memory and include it in the reply. If it does, memory is working.

---

If your assistant says it has no memory of prior conversations, check [Verify everything is running](#verify-everything-is-running) in the Advanced Usage section.

### 5. Stop & Resume

When you are done for the day:

```bash
./stop_service.sh
```

When you come back and want to resume:

```bash
./start_service.sh --restart
```

> `--restart` tells the script to wait for the kv-server to re-sync your memory stream from the blockchain before starting the backend. This can take **a few minutes** if your history is large.

### 6. Uninstall

```bash
./uninstall.sh
```

> **Warning:** this permanently deletes all stored memories. Running `install.sh` again generates a new stream ID — **previous memories are not recoverable**.

### Typical workflow

```
install.sh
  └─ fill in .env
       └─ start_service.sh                        ← first time (fresh stream)
            └─ use your AI coding assistant normally
                 └─ stop_service.sh               ← data preserved
                      └─ start_service.sh --restart   ← resume (re-sync chain)
                           └─ ...
                                └─ uninstall.sh   ← removes everything
```

---

## Advanced Usage

### How the memory system works

The memory backend intercepts every message you send and every reply your assistant gives, stores them as structured memories, and makes those memories available in future sessions — automatically, without any extra commands.

There are two mechanisms at play:

**Passive storage** — every prompt you submit, every assistant response, and every tool call result is captured and sent to the memory backend. Nothing is lost, and nothing requires action on your part.

**Active retrieval** — at the start of each new session, recent memories are fetched and injected directly into the assistant's context. Mid-session, whenever you reference past events or ask about something discussed before, the assistant searches the memory store and incorporates the results before replying.

The practical effect: your assistant carries context across sessions the same way a colleague does — it remembers past decisions, ongoing work, and the reasoning behind choices, even after you close and reopen it.

**Example — decisions that survive across sessions:**

You tell your assistant in one session:

> *"We chose PostgreSQL over MySQL because we need JSONB support for our metadata schema. Also, the API will be RESTful — we ruled out GraphQL after the team review."*

You close your assistant and open it the next day. In the new session:

> *"What database are we using and why?"*
>
> Assistant: *"PostgreSQL — you chose it over MySQL specifically for JSONB support in your metadata schema. You also noted the API design is RESTful; GraphQL was ruled out after the team review."*

The assistant did not guess. It retrieved the exact reasoning you recorded.

**Example — picking up mid-project without re-explaining:**

> *"Continue where we left off with the auth module."*
>
> Your assistant automatically searches your memory for prior auth discussions — past decisions, bugs fixed, approaches considered — and resumes from that point without you having to re-explain the context.

This is the core value: the longer you use your AI coding assistant, the richer the memory store becomes, and the less time you spend re-establishing context at the start of each session.

### How memory works during a session

| Moment | Claude Code / OpenCode | OpenClaw |
|--------|----------------------|----------|
| Session start | Recent memories are fetched and injected into the assistant's context | — (OpenClaw maintains its own session history in the context window) |
| Every prompt you send | Your message is stored | Your message is stored |
| Every assistant reply | The response is stored | The response is stored |
| Every tool call | Tool name and result are stored | Tool name and result are stored |
| Each prompt (mid-session) | The assistant searches memory and injects relevant results | The assistant searches memory and injects relevant results |

### What `install.sh` does

`install.sh` sets up everything automatically:

- **Installs Python dependencies** into `.venv/` — the Python packages EverMemOS needs to run.
- **Installs Claude Code skills and hooks** (if Claude Code is installed) — copies skills into `~/.claude/skills/` and registers hooks in `~/.claude/settings.json`. Hooks capture every prompt, response, and tool call automatically.
- **Installs OpenCode plugin** (if OpenCode is installed) — copies the plugin into `~/.config/opencode/plugins/` and registers it in `~/.config/opencode/opencode.json`.
- **Installs OpenClaw plugin** (if OpenClaw is installed) — links the plugin via `openclaw plugins install --link` and registers it in `~/.openclaw/openclaw.json`. Run `openclaw gateway restart` after installation to activate it.
- **Generates `.0g_secrets`** — creates a stream ID and encryption key for the 0G KV storage layer. Think of the stream ID as a unique address for your personal memory store on the 0G decentralized network, and the encryption key as the password that protects it. These are generated once and reused across restarts.
- **Downloads `zgs_kv`** — installs the 0G KV server binary into `0g_kv_server/`. This is a lightweight node that connects your machine to the 0G storage network, allowing EverMemOS to persist memories on-chain.

### What `start_service.sh` starts

Three things start in order:

1. **kv-server** (`zgs_kv`) — the 0G KV storage node. It syncs your stream from the blockchain so your memories are available locally.
2. **Docker containers** — MongoDB, Elasticsearch, Milvus, and Redis. These are the databases that power memory indexing and search.
3. **EverMemOS backend** — a REST API on `http://localhost:1995` that your AI coding assistant talks to for storing and retrieving memories.

### Why `--restart` is required on resume

When you stop and restart EverMemOS, the kv-server needs to re-sync your existing memory stream from the 0G blockchain before the backend can safely read from it. The `--restart` flag tells the start script to wait for that sync to complete. Depending on the size of your history, this can take anywhere from a few seconds to several minutes. On a first-time start (fresh stream, nothing to sync), the flag is not needed.

### Verify everything is running

Run these from the `0g-memory` project directory:

```bash
# Expect 6 containers: MongoDB, Elasticsearch, Redis, and Milvus
# (Milvus spawns 3 sub-containers: standalone, etcd, and minio)
docker compose ps

# EverMemOS backend health check
curl http://localhost:1995/health
# → {"status": "healthy", ...}

# kv-server process
pgrep -a zgs_kv
# If running, outputs the PID and binary path, e.g.:
#   12345 /home/user/0g-memory/0g_kv_server/zgs_kv --config ...
# No output means the kv-server is not running.
```

### Logs

All log commands below must be run from the `0g-memory` project directory.

| Component | Command |
|-----------|---------|
| EverMemOS backend | `tail -f $(ls -t logs/evermemos_*.log \| head -1)` |
| kv-server | `tail -f $(ls -t 0g_kv_server/kv_*.log \| head -1)` |
| Claude Code hook activity | `tail -f ~/.claude/logs/hook_user_prompt.log` |
| OpenCode plugin activity | `tail -f /tmp/evermemos_opencode.log` |
| OpenClaw plugin activity | `tail -f /tmp/evermemos_openclaw.log` |

To confirm the 2-minute test worked, run these after completing both the seed session and the recall session. You should see storage entries from the seed session and search entries from the recall session:

```bash
LOG=$(ls -t logs/evermemos_*.log | head -1)

# Messages stored in the seed session
grep "Memory request processing completed" "$LOG" | tail -5

# Search calls triggered in the recall session
grep "Received search request" "$LOG" | tail -5
```

Quick health check across all components:

```bash
LOG=$(ls -t logs/evermemos_*.log | head -1)

# Messages received and memories extracted
grep "Received memorize request\|Memory request processing completed" "$LOG" | tail -20

# Search calls triggered by the assistant
grep "Received search request" "$LOG" | tail -10

# Activity by sender type — Claude Code
grep "sender_name=User"              "$LOG" | wc -l
grep "sender_name=Claude (Response)" "$LOG" | wc -l
grep "sender_name=Claude (Tool)"     "$LOG" | wc -l

# Activity by sender type — OpenCode
grep "sender_name=OpenCode (Response)" "$LOG" | wc -l
grep "sender_name=OpenCode (Tool)"     "$LOG" | wc -l

# Activity by sender type — OpenClaw
grep "sender_name=OpenClaw (Response)" "$LOG" | wc -l
grep "sender_name=OpenClaw (Tool)"     "$LOG" | wc -l
```

### Uninstall — what gets removed

```bash
./uninstall.sh
```

Permanently removes:
- Docker containers and all volumes (MongoDB, Elasticsearch, Milvus, Redis data)
- `.0g_secrets`, `.env`, `.venv/`
- EverMemOS skills from `~/.claude/skills/` and hooks from `~/.claude/settings.json`
- EverMemOS plugin from `~/.config/opencode/plugins/` and entry from `~/.config/opencode/opencode.json`
- EverMemOS plugin entry from `~/.openclaw/openclaw.json`

> After uninstalling, running `install.sh` again generates a new stream ID and encryption key — **previous memories are not recoverable**.

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

`ZEROG_WALLET_KEY` is the 64-character hex private key of an EVM wallet. It is used by this memory system when calling the 0G storage SDK to write your encrypted memories to the [0G decentralized storage network](https://docs.0g.ai/concepts/storage). This project uses the **0G Galileo Testnet**, so you need a wallet funded with free testnet tokens.

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

Contact the 0G admin (xinyu@0g.ai) and include your wallet address. They will send testnet tokens to it.

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

### Appendix E: Scenario C — Remote Client Setup

Use this appendix if someone else is hosting an EverMemOS server and you want to connect your AI coding assistant (Claude Code, OpenCode, or OpenClaw) to it — without running any local services yourself.

#### Prerequisites

| Requirement | Notes |
|---|---|
| Claude Code, OpenCode, and/or OpenClaw | at least one must be installed |
| Python 3.8+ | typically pre-installed |
| Remote server URL | provided by the server administrator |
| `ZEROG_WALLET_KEY` | see [Appendix C](#appendix-c-getting-your-zerog_wallet_key) — your key is sent to the server at registration and used to write your memories to the 0G network on your behalf |

> **Note on `ZEROG_WALLET_KEY`:** even though you are not running a local service, your wallet key is required. The remote server stores it and uses it to write your encrypted memories to the 0G decentralized network — each user owns their own private 0G stream.

#### Step 1 — Clone the repository

```bash
git clone https://github.com/0gfoundation/0g-memory.git
cd 0g-memory
```

#### Step 2 — Edit `.env`

Copy the template and fill in three values:

```bash
cp env.template.0g.example .env
```

Open `.env` and set:

```bash
EVERMEMOS_REMOTE_URL=http://<server-ip>:<port>    # provided by the server admin
EVERMEMOS_USER_ID=<your-chosen-username>           # must be unique on that server
ZEROG_WALLET_KEY=<your-64-char-hex-private-key>   # see Appendix C
```

Leave everything else at defaults.

#### Step 3 — Run the installer

```bash
./install.sh
```

Because `EVERMEMOS_REMOTE_URL` is set, `install.sh` automatically:

1. Installs the AI assistant integration only (no Docker, no local service needed)
2. Registers your username on the remote server and receives an API key
3. Stores credentials in `.evermemos_remote_secrets`
4. Configures your AI assistant to use the remote server and authenticate with the API key:
   - **Claude Code** — updates `~/.claude/settings.json` with `EVERMEMOS_BASE_URL`, `EVERMEMOS_USER_ID`, and `EVERMEMOS_API_KEY`
   - **OpenCode** — writes `~/.config/opencode/evermemos.json` with `baseUrl`, `userId`, and `apiKey`
   - **OpenClaw** — updates `~/.openclaw/openclaw.json` with `apiBaseUrl`, `userId`, and `apiKey`

**OpenClaw only:** run `openclaw gateway restart` after the installer finishes to activate the plugin.

#### Step 4 — Verify

Start your AI coding assistant. Follow the same [2-minute test](#4-verify-memory-works--a-2-minute-test) from the Quick Start to confirm memory is working.

- **Claude Code / OpenCode:** follow the "Claude Code / OpenCode" instructions in Step B (type `/exit`, reopen, ask questions).
- **OpenClaw:** follow the "OpenClaw" instructions in Step B (verify within the same session).

#### Notes

- You do **not** need to run `./start_service.sh` — there is no local service to start.
- To uninstall, run `./uninstall.sh`. This removes the local integration and credentials but does **not** delete your memories from the remote server.
- If registration fails with "user already exists", contact the server admin to reset your API key, or manually create `.evermemos_remote_secrets` with your credentials.
