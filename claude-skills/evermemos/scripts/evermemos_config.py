#!/usr/bin/env python3
"""
EverMemOS Configuration Manager
"""

import os
import sys
from pathlib import Path


ASSISTANT_TAG = "claudecode"


def get_project_group_id(cwd: str = None, user_id: str = None) -> str:
    """
    Derive group_id from current working directory, assistant tag, and user_id.

    Format: project_<full_resolved_path>_claudecode_<user_id>
    Example: project_/home/op/git/myproject_claudecode_alice

    The assistant tag ensures memory is isolated from other AI assistants
    (OpenCode, OpenClaw) even when they share the same user_id and project path.

    Priority:
    1. EVERMEMOS_GROUP_ID env var (explicit override)
    2. cwd-derived full path + assistant tag + user_id
    3. Fallback to "project_default" if cwd is missing or empty
    """
    # 1. Explicit env var override
    explicit = os.environ.get('EVERMEMOS_GROUP_ID')
    if explicit:
        return explicit

    # 2. Derive from cwd (full resolved path) + assistant tag + user_id
    # Note: do NOT fall back to os.getcwd() — hooks run in an unpredictable
    # working directory (not the user's project dir), so os.getcwd() would
    # produce a silently wrong group_id. Use "project_default" instead.
    if cwd:
        try:
            resolved = str(Path(cwd).resolve())
            uid = user_id or "default_user"
            return f"project_{resolved}_{ASSISTANT_TAG}_{uid}"
        except Exception as e:
            print(f"[WARNING] Failed to resolve cwd for group_id: {cwd}: {e}", file=sys.stderr)

    # 3. Fallback: cwd unknown, cannot determine project directory
    return "project_default"
