#!/usr/bin/env python3
"""
PostToolUse Hook for EverMemOS
Record tool usage to EverMemOS for operation history
"""

import json
import sys
import os
import urllib.request
from datetime import datetime

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
logger = get_logger("hook_tool_use")


def _is_service_available():
    base_url = os.environ.get('API_BASE_URL', 'http://localhost:1995')
    try:
        urllib.request.urlopen(f"{base_url}/health", timeout=1)
        return True
    except Exception:
        return False


def read_hook_input():
    """
    Read hook input from Claude Code

    Expected fields for PostToolUse:
    - sessionId: string
    - toolName: string (name of the tool used)
    - toolInput: any (input to the tool)
    - toolResponse: any (output from the tool)
    - cwd: string (current working directory)
    """
    # Read from stdin
    if not sys.stdin.isatty():
        try:
            return json.load(sys.stdin)
        except json.JSONDecodeError:
            pass

    # Fallback: build from environment variables
    return {
        'sessionId': os.environ.get('CLAUDE_SESSION_ID', 'unknown'),
        'toolName': os.environ.get('CLAUDE_TOOL_NAME', ''),
        'toolInput': os.environ.get('CLAUDE_TOOL_INPUT', ''),
        'toolResponse': os.environ.get('CLAUDE_TOOL_RESPONSE', ''),
        'cwd': os.environ.get('CLAUDE_CWD', ''),
    }


def get_env_config():
    """Get EverMemOS configuration from environment variables"""
    return {
        'base_url': os.environ.get('API_BASE_URL', 'http://localhost:1995'),
        'user_id': os.environ.get('EVERMEMOS_USER_ID', 'claude_code_user'),
    }


MAX_INPUT_LENGTH = 10000
MAX_RESPONSE_LENGTH = 100000


def truncate_text(text, max_length=500):
    """Truncate text to max_length characters"""
    if not text:
        return ""

    text_str = str(text)
    if len(text_str) <= max_length:
        return text_str

    return text_str[:max_length] + f"... (truncated, total length: {len(text_str)})"


def format_tool_observation(tool_name, tool_input, tool_response):
    """
    Format tool usage into observation message

    Returns a structured, human-readable message about tool usage
    """
    lines = []

    # Header
    lines.append(f"🔧 Tool Used: {tool_name}")
    lines.append(f"⏰ Time: {datetime.now().isoformat()}")
    lines.append("")

    # Input section
    if tool_input:
        lines.append("📥 Input:")
        # Handle both dict and string formats
        if isinstance(tool_input, dict):
            input_str = json.dumps(tool_input, indent=2, ensure_ascii=False)
            if len(input_str) > MAX_INPUT_LENGTH:
                input_str = input_str[:MAX_INPUT_LENGTH] + "..."
        elif isinstance(tool_input, str):
            try:
                input_obj = json.loads(tool_input)
                input_str = json.dumps(input_obj, indent=2, ensure_ascii=False)
                if len(input_str) > MAX_INPUT_LENGTH:
                    input_str = input_str[:MAX_INPUT_LENGTH] + "..."
            except:
                input_str = truncate_text(tool_input, max_length=MAX_INPUT_LENGTH)
        else:
            input_str = truncate_text(str(tool_input), max_length=MAX_INPUT_LENGTH)
        lines.append(input_str)
        lines.append("")

    # Response section
    if tool_response:
        lines.append("📤 Response:")
        # Handle both dict and string formats
        if isinstance(tool_response, dict):
            # For dict, extract stdout or convert to JSON
            if 'stdout' in tool_response:
                response_str = truncate_text(tool_response['stdout'], max_length=MAX_RESPONSE_LENGTH)
            else:
                response_str = json.dumps(tool_response, indent=2, ensure_ascii=False)
                if len(response_str) > MAX_RESPONSE_LENGTH:
                    response_str = response_str[:MAX_RESPONSE_LENGTH] + "..."
        elif isinstance(tool_response, str):
            try:
                response_obj = json.loads(tool_response)
                response_str = json.dumps(response_obj, indent=2, ensure_ascii=False)
                if len(response_str) > MAX_RESPONSE_LENGTH:
                    response_str = response_str[:MAX_RESPONSE_LENGTH] + "..."
            except:
                response_str = truncate_text(tool_response, max_length=MAX_RESPONSE_LENGTH)
        else:
            response_str = truncate_text(str(tool_response), max_length=MAX_RESPONSE_LENGTH)
        lines.append(response_str)

    return "\n".join(lines)


def main():
    """Main execution"""
    if not _is_service_available():
        print(json.dumps({"continue": True, "suppressOutput": True}))
        sys.exit(0)

    try:
        # Read hook input
        hook_data = read_hook_input()

        # Claude Code uses snake_case for parameter names
        session_id = hook_data.get('session_id') or hook_data.get('sessionId', 'unknown')
        tool_name = hook_data.get('tool_name') or hook_data.get('toolName', '')
        tool_input = hook_data.get('tool_input') or hook_data.get('toolInput', '')
        tool_response = hook_data.get('tool_response') or hook_data.get('toolResponse', '')
        cwd = hook_data.get('cwd', '')

        # Debug: log received data
        logger.debug(f"PostToolUse: sessionId={session_id}, tool={tool_name}, cwd={cwd}")
        logger.info(f"Hook data keys: {list(hook_data.keys())}")

        # Skip if no tool name (matches claude-mem validation)
        if not tool_name:
            logger.debug("Skipping: no tool name")
            output = {"continue": True, "suppressOutput": True}
            print(json.dumps(output))
            sys.exit(0)

        # Get configuration
        config = get_env_config()
        config['group_id'] = get_project_group_id(cwd=cwd, user_id=config['user_id'])

        logger.debug(f"Using config: {config}")

        client = EverMemOSClient(**config)

        # Format tool observation
        observation_message = format_tool_observation(tool_name, tool_input, tool_response)

        logger.debug(f"Storing tool observation to EverMemOS... (length: {len(observation_message)} chars)")

        result = client.store_message(
            content=observation_message,
            role="assistant",
            sender_name="Claude (Tool)"
        )

        # Log success
        logger.debug(f"Tool observation stored successfully: {result.get('message', 'OK')}")

        # Return success
        output = {"continue": True, "suppressOutput": True}
        print(json.dumps(output))
        sys.exit(0)

    except Exception as e:
        # Log error but don't block tool execution
        logger.error(f"Failed to store tool observation: {e}")
        import traceback
        traceback.print_exc(file=sys.stderr)

        # Return success anyway (graceful failure)
        output = {"continue": True, "suppressOutput": True}
        print(json.dumps(output))
        sys.exit(0)


if __name__ == "__main__":
    main()
