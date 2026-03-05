#!/usr/bin/env python3
"""
EverMemOS Configuration Manager
"""

import os
import sys
from pathlib import Path


def get_project_group_id(cwd: str = None) -> str:
    """
    Derive group_id from current working directory (full path).

    Format: project_<full_resolved_path>
    Example: project_/home/op/git/EverMemOS

    Priority:
    1. EVERMEMOS_GROUP_ID env var (explicit override)
    2. cwd-derived full path (must be explicitly passed by caller)
    3. Fallback to "project_default" if cwd is missing or empty
    """
    # 1. Explicit env var override
    explicit = os.environ.get('EVERMEMOS_GROUP_ID')
    if explicit:
        return explicit

    # 2. Derive from cwd (full resolved path)
    # Note: do NOT fall back to os.getcwd() — hooks run in an unpredictable
    # working directory (not the user's project dir), so os.getcwd() would
    # produce a silently wrong group_id. Use "project_default" instead.
    if cwd:
        try:
            resolved = str(Path(cwd).resolve())
            return f"project_{resolved}"
        except Exception as e:
            print(f"[WARNING] Failed to resolve cwd for group_id: {cwd}: {e}", file=sys.stderr)

    # 3. Fallback: cwd unknown, cannot determine project directory
    return "project_default"
