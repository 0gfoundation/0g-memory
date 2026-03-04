#!/usr/bin/env python3
"""
EverMemOS Configuration Manager

This module handles configuration loading and project exclusion logic,
similar to claude-mem's SettingsDefaultsManager and isProjectExcluded.
"""

import os
import json
import sys
from pathlib import Path


def get_excluded_projects():
    """
    Get list of projects that should be excluded from tracking

    Follows claude-mem's approach:
    1. Check environment variable first
    2. Fall back to config file
    3. Default to empty list

    Returns:
        list: List of project paths to exclude
    """
    # Method 1: From environment variable (comma-separated)
    env_excluded = os.environ.get('EVERMEMOS_EXCLUDED_PROJECTS', '')
    if env_excluded:
        excluded_list = [path.strip() for path in env_excluded.split(',') if path.strip()]
        if excluded_list:
            return excluded_list

    # Method 2: From config file
    config_path = Path.home() / '.evermemos' / 'config.json'
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                excluded = config.get('excluded_projects', [])
                if excluded:
                    return excluded
        except Exception as e:
            print(f"[WARNING] Failed to load config from {config_path}: {e}", file=sys.stderr)

    # Default: no exclusions
    return []


def is_project_excluded(cwd):
    """
    Check if a project should be excluded from tracking

    This replicates claude-mem's isProjectExcluded logic:
    - Check if cwd matches any excluded project path
    - Support both exact matches and parent directory checks

    Args:
        cwd: Current working directory

    Returns:
        bool: True if project should be excluded
    """
    if not cwd:
        return False

    excluded_projects = get_excluded_projects()
    if not excluded_projects:
        return False

    # Normalize cwd path
    try:
        cwd_path = Path(cwd).resolve()
    except Exception as e:
        print(f"[WARNING] Failed to resolve cwd path: {cwd}: {e}", file=sys.stderr)
        return False

    # Check if cwd matches any excluded project
    for excluded in excluded_projects:
        try:
            excluded_path = Path(excluded).resolve()

            # Check if cwd is the excluded path or a subdirectory
            if cwd_path == excluded_path or excluded_path in cwd_path.parents:
                return True
        except Exception as e:
            # Invalid path in config, skip it
            print(f"[WARNING] Invalid excluded project path: {excluded}: {e}", file=sys.stderr)
            continue

    return False


def get_project_group_id(cwd: str = None) -> str:
    """
    Derive group_id from current working directory (full path).

    Format: project_<full_resolved_path>
    Example: project_/home/op/git/EverMemOS

    Priority:
    1. EVERMEMOS_GROUP_ID env var (explicit override)
    2. cwd-derived full path
    3. Fallback default

    Args:
        cwd: Current working directory. If None, uses os.getcwd().

    Returns:
        str: group_id string for this project
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


# Export symbols
__all__ = ['get_excluded_projects', 'is_project_excluded', 'get_project_group_id']
