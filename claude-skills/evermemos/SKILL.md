---
name: evermemos
description: Search memories using EverMemOS. PROACTIVELY search before answering ANY project-related questions. Use when user asks about past conversations, previous decisions. ALWAYS check history before implementing features, debugging issues, or suggesting solutions. Maintain project continuity across sessions.
argument-hint: "search <query> [method] [top_k]"
allowed-tools: Bash(python3 *)
---

# EverMemOS Memory Integration

## Commands

The script to invoke is always:
```
~/.claude/skills/evermemos/scripts/evermemos_client.py
```

### search

Search memories by query.

```
/evermemos search <query> [method] [top_k]
```

- `method`: `hybrid` (default), `agentic`
- `top_k`: max results (default: 5)

**When to use — ALWAYS trigger when:**
- User asks "What did we discuss about X?" / "Did we fix that bug?" / "What approach did we decide on?"
- Any question containing: "last time", "before", "previously", "earlier", "remember"
- Before implementing features (check past approaches)
- Before debugging (check similar past issues and solutions)
- User mentions specific modules, files, or components → search that component first
- User asks how something works in THIS project

**Execute:**
```bash
python3 "$HOME/.claude/skills/evermemos/scripts/evermemos_client.py" search "<query>" [method] [top_k]
```

---

## Proactive Usage Rules

**Rule 1 — Search first, answer second (default behavior):**

```
User asks a question
    ↓
Is it about THIS project or past conversations?
    YES → SEARCH FIRST
    NO  → Answer directly
```

When in doubt, search. Missing context costs hours; an unnecessary search costs seconds.

**Rule 2 — Multi-angle search for complex questions:**

Don't search once and give up. Search multiple related angles. For example, if the user asks about authentication, then run the below:
```bash
python3 "$HOME/.claude/skills/evermemos/scripts/evermemos_client.py" search "authentication implementation"
python3 "$HOME/.claude/skills/evermemos/scripts/evermemos_client.py" search "auth bug fix"
python3 "$HOME/.claude/skills/evermemos/scripts/evermemos_client.py" search "auth security pattern"
```

**Rule 3 — After getting search results:**

Always incorporate results into your response. Do not search and ignore — past context exists to be used.

---

## Retrieval Methods

Default: always use `hybrid`.

Only use `agentic` when:
- Query is vague or ambiguous (e.g. "that bug we discussed last month")
- `hybrid` returned no useful results
- User explicitly asks for deep or thorough search

---

## Troubleshooting

**Connection error:** Check that EverMemOS is running (`curl http://localhost:1995`) and `EVERMEMOS_BASE_URL` is correct.

**No results:** Try different keywords, switch to `agentic` method, or increase `top_k`. Verify the correct `user_id` and `group_id` are in use.
