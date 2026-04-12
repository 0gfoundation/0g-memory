#!/usr/bin/env python3
"""
UserPromptSubmit Hook for EverMemOS
Automatically store user messages to EverMemOS
"""

import json
import sys
import os
import urllib.request

# Add current directory to path to import evermemos_client
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from evermemos_client import EverMemOSClient
    from evermemos_config import get_project_group_id
    from evermemos_logger import get_logger
except ImportError as e:
    # If import fails, exit gracefully
    print(json.dumps({
        "continue": True,
        "suppressOutput": True
    }))
    sys.exit(0)

# Global logger instance
logger = get_logger("hook_user_prompt")


def _is_service_available():
    base_url = os.environ.get('API_BASE_URL', 'http://localhost:1995')
    url = f"{base_url}/health"
    proxy_configured = any(os.environ.get(k) for k in ('http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY'))

    for bypass_proxy in (False, True):
        try:
            if bypass_proxy:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                opener.open(url, timeout=10)
            else:
                urllib.request.urlopen(url, timeout=10)
            return True
        except urllib.error.HTTPError as e:
            if e.code == 502 and not bypass_proxy and proxy_configured:
                continue
            return False
        except urllib.error.URLError:
            if not bypass_proxy and proxy_configured:
                continue
            return False
        except Exception:
            return False
    return False


def read_hook_input():
    """
    Read hook input from Claude Code

    Claude Code provides hook data in two ways:
    1. Environment variable: CLAUDE_HOOK_INPUT (JSON string)
    2. stdin: JSON object

    Expected fields for UserPromptSubmit:
    - session_id: string
    - prompt: string (user's input)
    - cwd: string (current working directory)
    - hook_event_name: string
    """
    # Read from stdin
    if not sys.stdin.isatty():
        try:
            return json.load(sys.stdin)
        except json.JSONDecodeError:
            pass

    # Fallback: build from environment variables
    # Claude Code may also pass data as separate env vars
    return {
        'session_id': os.environ.get('CLAUDE_SESSION_ID', 'unknown'),
        'prompt': os.environ.get('CLAUDE_USER_PROMPT', ''),
        'cwd': os.environ.get('CLAUDE_CWD', ''),
    }


def get_env_config():
    """Get EverMemOS configuration from environment variables"""
    return {
        'base_url': os.environ.get('API_BASE_URL', 'http://localhost:1995'),
        'user_id': os.environ.get('MEMORY_USER_ID', 'default_user'),
    }


def main():
    """Main execution"""
    if not _is_service_available():
        print(json.dumps({"continue": True, "suppressOutput": True}))
        sys.exit(0)

    try:
        # Read hook input
        hook_data = read_hook_input()

        session_id = hook_data.get('session_id', 'unknown')
        prompt = hook_data.get('prompt', '')
        cwd = hook_data.get('cwd', '')
        platform = hook_data.get('platform', 'claude-code')

        # Debug: log received data
        logger.debug(f"UserPrompt: platform={platform}, sessionId={session_id}, prompt_length={len(prompt)}, cwd={cwd}")

        # Handle image-only prompts (matches claude-mem behavior)
        # Use placeholder to preserve session tracking instead of skipping
        if not prompt or not prompt.strip():
            prompt = '[media prompt]'
            logger.debug(f"Empty prompt detected, using placeholder: {prompt}")

        # Get configuration
        config = get_env_config()
        config['group_id'] = get_project_group_id(cwd=cwd, user_id=config['user_id'])

        logger.debug(f"Using config: {config}")

        client = EverMemOSClient(**config)

        # Store user message
        logger.debug("Storing message to EverMemOS...")
        result = client.store_message(
            content=prompt,
            role="user",
            sender_name="User"
        )

        # Log success
        logger.debug(f"Message stored successfully: {result.get('message', 'OK')}")

        # Return success
        output = {"continue": True, "suppressOutput": True}
        print(json.dumps(output))
        sys.exit(0)

    except Exception as e:
        # Log error but don't block user prompt
        logger.error(f"Failed to store user message: {e}")
        import traceback
        traceback.print_exc(file=sys.stderr)

        # Return success anyway (graceful failure)
        output = {"continue": True, "suppressOutput": True}
        print(json.dumps(output))
        sys.exit(0)


if __name__ == "__main__":
    main()
