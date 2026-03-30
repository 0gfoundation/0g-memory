#!/usr/bin/env python3
"""
EverMemOS Remote Setup

Registers this machine as a user on a remote EverMemOS server (SERVER_MODE=true),
stores the API key in .evermemos_remote_secrets, and configures Claude Code's
~/.claude/settings.json to use the remote server.

Called automatically by install.sh when EVERMEMOS_REMOTE_URL is set in .env.
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

    remote_url = env_vars.get("EVERMEMOS_REMOTE_URL", "").rstrip("/")
    remote_user_id = env_vars.get("EVERMEMOS_USER_ID", "")
    wallet_key = env_vars.get("ZEROG_WALLET_KEY", "")

    if not remote_url:
        _fail("EVERMEMOS_REMOTE_URL is not set in .env")
        sys.exit(1)
    if not remote_user_id:
        _fail("EVERMEMOS_USER_ID is required when EVERMEMOS_REMOTE_URL is set")
        sys.exit(1)
    if not wallet_key:
        _fail("ZEROG_WALLET_KEY is required for remote registration (used for 0G storage)")
        sys.exit(1)

    # ── 2. Check .evermemos_remote_secrets ────────────────────────────────────
    secrets_path = project_dir / ".evermemos_remote_secrets"
    secrets = _read_kv_file(secrets_path)
    api_key = secrets.get("EVERMEMOS_REMOTE_API_KEY", "")

    if api_key:
        _info(f"Credentials already stored in {secrets_path.name}, skipping registration")
        stored_user_id = secrets.get("EVERMEMOS_USER_ID", remote_user_id)
        if stored_user_id != remote_user_id:
            _warn(
                f"EVERMEMOS_USER_ID in .env ({remote_user_id}) differs from "
                f"stored user ({stored_user_id}). Using stored user."
            )
            remote_user_id = stored_user_id
    else:
        # ── 3. Register with remote server ────────────────────────────────────
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
            if e.code == 409:
                _fail(
                    f"User '{remote_user_id}' already exists on the remote server, "
                    f"but no local credentials were found.\n"
                    f"       Contact the server admin to reset your API key, then:\n"
                    f"       1. Re-run ./install.sh  (it will retry registration)\n"
                    f"       OR manually create .evermemos_remote_secrets with:\n"
                    f"          EVERMEMOS_USER_ID={remote_user_id}\n"
                    f"          EVERMEMOS_REMOTE_API_KEY=<your_api_key>"
                )
            else:
                _fail(f"Registration failed: HTTP {e.code} — {error_body}")
            sys.exit(1)
        except urllib.error.URLError as e:
            _fail(
                f"Cannot reach remote server at {remote_url}\n"
                f"       Reason: {e.reason}\n"
                f"       Check the URL and network connectivity."
            )
            sys.exit(1)

        # ── 4. Store credentials ──────────────────────────────────────────────
        _write_kv_file(secrets_path, {
            "EVERMEMOS_USER_ID": remote_user_id,
            "EVERMEMOS_REMOTE_API_KEY": api_key,
        })
        _ok(f"Registered successfully. Credentials saved to {secrets_path.name}")

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
    settings["env"]["EVERMEMOS_BASE_URL"] = remote_url
    settings["env"]["API_BASE_URL"] = remote_url          # backward compat
    settings["env"]["EVERMEMOS_API_KEY"] = api_key
    settings["env"]["EVERMEMOS_USER_ID"] = remote_user_id

    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
            f.write("\n")
        _ok(f"Updated ~/.claude/settings.json (EVERMEMOS_BASE_URL={remote_url})")
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


if __name__ == "__main__":
    main()
