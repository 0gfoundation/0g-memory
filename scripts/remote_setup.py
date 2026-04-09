#!/usr/bin/env python3
"""
EverMemOS Remote Setup

Registers this machine as a user on a remote EverMemOS server (SERVER_MODE=true),
stores the API key in .evermemos_remote_secrets, and configures Claude Code's
~/.claude/settings.json to use the remote server.

Called automatically by install.sh when MEMORY_REMOTE_URL is set in .env.
Not intended to be run manually.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ok(msg: str):
    print(f"  ✅ {msg}")

def _info(msg: str):
    print(f"  ℹ️  {msg}")

def _warn(msg: str):
    print(f"  ⚠️  {msg}")

def _fail(msg: str):
    print(f"  ❌ {msg}", file=sys.stderr)


def _read_kv_file(path: Path) -> dict:
    """Read a KEY=VALUE file into a dict (ignores blank lines and # comments)."""
    result = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def _write_kv_file(path: Path, data: dict):
    """Write a dict to a KEY=VALUE file."""
    path.write_text(
        "\n".join(f"{k}={v}" for k, v in data.items()) + "\n",
        encoding="utf-8",
    )


# ── Main logic ────────────────────────────────────────────────────────────────

def main():
    project_dir = Path(__file__).resolve().parent.parent

    # ── 1. Read .env ──────────────────────────────────────────────────────────
    env_vars = _read_kv_file(project_dir / ".env")

    remote_url = env_vars.get("MEMORY_REMOTE_URL", "").rstrip("/")
    remote_user_id = env_vars.get("MEMORY_USER_ID", "")
    wallet_key = env_vars.get("ZEROG_WALLET_KEY", "")

    if not remote_url:
        _fail("MEMORY_REMOTE_URL is not set in .env")
        sys.exit(1)
    if not remote_user_id:
        _fail("MEMORY_USER_ID is required when MEMORY_REMOTE_URL is set")
        sys.exit(1)
    if not wallet_key:
        _fail("ZEROG_WALLET_KEY is required for remote registration (used for 0G storage)")
        sys.exit(1)

    # ── 2. Register with remote server (skip if already registered) ──────────────
    secrets_path = project_dir / ".evermemos_remote_secrets"

    existing_secrets = _read_kv_file(secrets_path)
    existing_api_key = existing_secrets.get("EVERMEMOS_REMOTE_API_KEY", "")
    existing_user_id = existing_secrets.get("MEMORY_USER_ID", "")
    existing_remote_url = existing_secrets.get("MEMORY_REMOTE_URL", "")

    if (existing_api_key
            and existing_user_id == remote_user_id
            and (not existing_remote_url or existing_remote_url == remote_url)):
        _info(f"User '{remote_user_id}' already registered on {remote_url} (credentials found in {secrets_path.name}), skipping registration.")
        api_key = existing_api_key
    else:
        _info(f"Registering user '{remote_user_id}' on {remote_url} ...")

        register_url = f"{remote_url}/api/v1/users/register"
        payload = json.dumps({
            "user_id": remote_user_id,
            "zerog_wallet_key": wallet_key,
        }).encode("utf-8")

        req = urllib.request.Request(
            register_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                try:
                    body = json.loads(raw)
                except json.JSONDecodeError:
                    _fail(
                        f"Registration endpoint returned non-JSON response.\n"
                        f"       Raw response: {raw[:200]}\n"
                        f"       Check that {remote_url} is a valid EverMemOS server."
                    )
                    sys.exit(1)
                api_key = body.get("api_key", "")
                if not api_key:
                    _fail(
                        f"Registration response did not contain an api_key.\n"
                        f"       Response: {raw[:200]}"
                    )
                    sys.exit(1)
        except urllib.error.HTTPError as e:
            error_body = ""
            if e.fp:
                try:
                    error_body = e.read().decode("utf-8")
                except Exception:
                    pass
            _fail(f"Registration failed: HTTP {e.code} — {error_body}")
            sys.exit(1)
        except urllib.error.URLError as e:
            _fail(
                f"Cannot reach remote server at {remote_url}\n"
                f"       Reason: {e.reason}\n"
                f"       Check the URL and network connectivity."
            )
            sys.exit(1)

    # ── 3. Store credentials (overwrite) ─────────────────────────────────────
    _write_kv_file(secrets_path, {
        "MEMORY_USER_ID": remote_user_id,
        "MEMORY_REMOTE_URL": remote_url,
        "EVERMEMOS_REMOTE_API_KEY": api_key,
    })
    _ok(f"Credentials saved to {secrets_path.name}")

    # ── 5. Update ~/.claude/settings.json ─────────────────────────────────────
    settings_path = Path.home() / ".claude" / "settings.json"
    settings: dict = {}
    if settings_path.exists():
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            _warn(f"Could not read {settings_path}: {e}, will recreate")
            settings = {}

    if "env" not in settings:
        settings["env"] = {}

    # Force-overwrite (not setdefault) so remote values always take effect.
    settings["env"]["API_BASE_URL"] = remote_url
    settings["env"]["EVERMEMOS_API_KEY"] = api_key
    settings["env"]["MEMORY_USER_ID"] = remote_user_id

    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
            f.write("\n")
        _ok(f"Updated ~/.claude/settings.json (API_BASE_URL={remote_url})")
    except OSError as e:
        _fail(f"Failed to write {settings_path}: {e}")
        sys.exit(1)

    # ── 6. Update OpenCode config (if OpenCode is installed) ──────────────────
    opencode_config_dir = Path.home() / ".config" / "opencode"
    if opencode_config_dir.exists():
        evermemos_config_path = opencode_config_dir / "evermemos.json"
        try:
            with open(evermemos_config_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "baseUrl": remote_url,
                        "userId": remote_user_id,
                        "apiKey": api_key,
                    },
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
                f.write("\n")
            _ok(f"Updated ~/.config/opencode/evermemos.json (baseUrl={remote_url})")
        except OSError as e:
            _warn(f"Failed to write OpenCode config: {e}")
    else:
        _info("OpenCode not detected (~/.config/opencode/ not found), skipping OpenCode config")

    # ── 7. Update OpenClaw config (if OpenClaw is installed) ──────────────────
    openclaw_config_path = Path.home() / ".openclaw" / "openclaw.json"
    if openclaw_config_path.exists():
        try:
            with open(openclaw_config_path, "r", encoding="utf-8") as f:
                oc_config = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            _warn(f"Could not read ~/.openclaw/openclaw.json: {e}, skipping OpenClaw config")
            oc_config = None

        if oc_config is not None:
            plugin_id = "evermemos-openclaw"
            plugins = oc_config.setdefault("plugins", {})
            entries = plugins.setdefault("entries", {})
            plugin_entry = entries.setdefault(plugin_id, {"enabled": True})
            config_block = plugin_entry.setdefault("config", {})
            config_block["apiBaseUrl"] = remote_url
            config_block["userId"] = remote_user_id
            config_block["apiKey"] = api_key
            try:
                tmp = openclaw_config_path.with_suffix(".json.tmp")
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(oc_config, f, indent=2, ensure_ascii=False)
                    f.write("\n")
                tmp.replace(openclaw_config_path)
                _ok(f"Updated ~/.openclaw/openclaw.json (apiBaseUrl={remote_url})")
            except OSError as e:
                _warn(f"Failed to write OpenClaw config: {e}")
    else:
        _info("OpenClaw not detected (~/.openclaw/openclaw.json not found), skipping OpenClaw config")


if __name__ == "__main__":
    main()
