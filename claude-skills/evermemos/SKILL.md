---
name: evermemos
description: Search and store memories using EverMemOS. PROACTIVELY search before answering ANY project-related questions. Use when user asks about past conversations, previous decisions, or when important information should be remembered. ALWAYS check history before implementing features, debugging issues, or suggesting solutions. Automatically store important decisions, bugs, and patterns. Maintain project continuity across sessions.
argument-hint: "[search|store|recent] [query/content]"
allowed-tools: Bash(python3 *)
---

# EverMemOS Memory Integration

## Commands

### search

Search memories by query.

```
/evermemos search <query> [method] [top_k]
```

- `method`: `keyword`, `vector`, `hybrid` (default), `rrf`, `agentic`
- `top_k`: max results (default: 5)

### store

Store structured summaries, conclusions, or AI-generated insights.

```
/evermemos store <content> [role]
```

- `role`: `user` or `assistant` (default: `assistant`)

**Important:** Raw user messages are already auto-saved by the UserPromptSubmit hook. Use `store` only for structured summaries — not raw messages.

```
# Good: structured insight
/evermemos store "Bug: async_streaming_bulk fails with timeout >30s. Fix: use sync_bulk for large batches." assistant

# Bad: duplicates auto-saved user message
/evermemos store "Remember that we use hybrid retrieval" user
```

### recent

Fetch recent conversation history.

```
/evermemos recent [limit]
```

- `limit`: number of memories to fetch (default: 10)

---

## Usage Rules

**Rule 1 — Search first:** Before answering ANY project-related question, search for relevant history. When in doubt, search. Missing context costs more than an unnecessary search.

**Rule 2 — Store structured insights:** When you discover a bug, reach a decision, or establish a pattern, store a structured summary as `assistant` role. Do not store raw user messages (already auto-saved).

---

## Configuration

```bash
export EVERMEMOS_BASE_URL="http://localhost:1995"   # API endpoint
export EVERMEMOS_USER_ID="claude_code_user"         # User identifier
# group_id is auto-derived from the current working directory:
#   Format: project_<full_path>  e.g. project_/home/op/git/EverMemOS
# Override only when needed:
# export EVERMEMOS_GROUP_ID="project_/some/specific/path"
```

---

## Retrieval Methods

- `keyword`: exact text match, fast
- `vector`: semantic similarity, understands meaning
- `hybrid`: keyword + vector combined (recommended default)
- `rrf`: Reciprocal Rank Fusion, advanced ranking
- `agentic`: AI-powered intelligent retrieval

---

## Troubleshooting

**Connection error:** Check that EverMemOS is running (`curl http://localhost:1995`) and `EVERMEMOS_BASE_URL` is correct.

**No results:** Try different keywords, switch to `hybrid` or `vector` method, or increase `top_k`. Verify the correct `user_id` and `group_id` are in use.

**Permission error:** Ensure Python 3 is installed (`python3 --version`) and the script is executable (`chmod +x ~/.claude/skills/evermemos/scripts/evermemos_client.py`).
