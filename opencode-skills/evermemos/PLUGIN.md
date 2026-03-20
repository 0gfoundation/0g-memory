# EverMemOS Plugin for OpenCode

This plugin integrates [EverMemOS](https://github.com/0gfoundation/0g-memory) with OpenCode, providing persistent memory across all your coding sessions.

## What it does

| Hook | Action |
|------|--------|
| Session start | Loads your recent conversation history and injects it into the system prompt |
| User message | Stores your message; searches related memories and injects them into the prompt |
| Tool calls | Records every tool invocation and its output |
| AI responses | Records every response from the AI |

## Requirements

- EverMemOS backend running at `http://localhost:1995` (start with `./start_service.sh`)
- Bun runtime (used by OpenCode to load plugins)

## Configuration

The plugin uses sensible defaults and works out of the box. To override, set these environment variables in your shell profile (`~/.bashrc` or `~/.zshrc`):

| Variable | Default | Description |
|----------|---------|-------------|
| `API_BASE_URL` | `http://localhost:1995` | EverMemOS backend URL |
| `EVERMEMOS_USER_ID` | `opencode_user` | Your user identity |
| `EVERMEMOS_GROUP_ID` | _(auto-derived)_ | Project group ID — auto-derived from project path if not set |

## Logs

Debug logs are written to `/tmp/evermemos_opencode.log`.

```bash
tail -f /tmp/evermemos_opencode.log
```
