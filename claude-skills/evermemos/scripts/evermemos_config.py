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
    2. cwd-derived full path
    3. Fallback default
    """
    # 1. Explicit env var override
    explicit = os.environ.get('EVERMEMOS_GROUP_ID')
    if explicit:
        return explicit

    # 2. Derive from cwd (full resolved path)
    if cwd is None:
        cwd = os.getcwd()

    if cwd:
        try:
            resolved = str(Path(cwd).resolve())
            return f"project_{resolved}"
        except Exception as e:
            print(f"[WARNING] Failed to resolve cwd for group_id: {cwd}: {e}", file=sys.stderr)

    # 3. Fallback
    return "project_default"
