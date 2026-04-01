#!/usr/bin/env python3
"""
Stop Hook for EverMemOS
Capture Claude's text output after each response (every turn)
"""

import json
import sys
import os
import re
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
logger = get_logger("hook_stop")


def _is_service_available():
    base_url = os.environ.get('API_BASE_URL', 'http://localhost:1995')
    try:
        urllib.request.urlopen(f"{base_url}/health", timeout=10)
        return True
    except Exception:
        return False


def read_hook_input():
    """
    Read hook input from Claude Code

    Expected fields for Stop:
    - session_id: string
    - cwd: string (current working directory)
    - last_assistant_message: string (Claude's final response text)
    """
    # Read from stdin
    if not sys.stdin.isatty():
        try:
            return json.load(sys.stdin)
        except json.JSONDecodeError:
            pass

    # Fallback: build from environment variables
    return {
        'session_id': os.environ.get('CLAUDE_SESSION_ID', 'unknown'),
        'cwd': os.environ.get('CLAUDE_CWD', ''),
        'last_assistant_message': os.environ.get('CLAUDE_LAST_ASSISTANT_MESSAGE', ''),
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

        session_id = hook_data.get('session_id') or hook_data.get('sessionId', 'unknown')
        cwd = hook_data.get('cwd', '')
        claude_output = hook_data.get('last_assistant_message', '')

        logger.debug(f"Stop: sessionId={session_id}, cwd={cwd}, message_len={len(claude_output)}")

        # Get configuration
        config = get_env_config()
        config['group_id'] = get_project_group_id(cwd=cwd, user_id=config['user_id'])

        client = EverMemOSClient(**config)

        # Strip system-reminder tags if present
        if claude_output:
            claude_output = re.sub(r'<system-reminder>[\s\S]*?</system-reminder>', '', claude_output)
            claude_output = re.sub(r'\n{3,}', '\n\n', claude_output).strip()

        if claude_output:
            result = client.store_message(
                content=claude_output,
                role="assistant",
                sender_name="Claude (Response)"
            )
            logger.info(f"Claude output stored successfully: {result.get('message', 'OK')}")
        else:
            logger.debug("No assistant message to store")

        print(json.dumps({"continue": True, "suppressOutput": True}))
        sys.exit(0)

    except Exception as e:
        logger.error(f"Failed to capture Claude output: {e}")
        import traceback
        traceback.print_exc(file=sys.stderr)

        print(json.dumps({"continue": True, "suppressOutput": True}))
        sys.exit(0)


if __name__ == "__main__":
    main()
