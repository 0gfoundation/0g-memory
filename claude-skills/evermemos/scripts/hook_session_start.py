#!/usr/bin/env python3
"""
SessionStart Hook for EverMemOS
Load recent memory context when Claude Code session starts
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
    # If import fails, print error and exit gracefully
    print(json.dumps({
        "continue": True,
        "suppressOutput": True,
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": ""
        }
    }), file=sys.stderr)
    sys.exit(0)

# Global logger instance
logger = get_logger("hook_session_start")


def _is_service_available():
    base_url = os.environ.get('EVERMEMOS_BASE_URL', 'http://localhost:1995')
    try:
        urllib.request.urlopen(f"{base_url}/health", timeout=1)
        return True
    except Exception:
        return False


def get_env_config():
    """Get configuration from environment variables"""
    return {
        'base_url': os.environ.get('EVERMEMOS_BASE_URL', 'http://localhost:1995'),
        'user_id': os.environ.get('EVERMEMOS_USER_ID', 'claude_code_user'),
    }


def format_context_for_claude(memories, pending_messages):
    """Format memories into context string for Claude"""
    if not memories and not pending_messages:
        return ""

    lines = ["# 📚 Recent Memory Context\n"]

    # Add recent episodic memories
    if memories:
        lines.append("## Recent Conversations:\n")
        for mem in memories[:15]:  # Last 15 memories for richer context
            # Use priority: timestamp > start_time > created_at (all UTC)
            timestamp = mem.get('timestamp') or mem.get('start_time') or mem.get('created_at', 'Unknown time')
            title = mem.get('title', mem.get('subject', 'Untitled'))
            full_text = mem.get('episode', '') or mem.get('summary', '')

            lines.append(f"**[{timestamp}]** {title}")
            if full_text:
                lines.append(f"  {full_text}\n")

    # Add pending messages (not yet extracted into episodic memories)
    if pending_messages:
        lines.append("## Recent Messages (Pending):\n")
        for msg in pending_messages[:100]:  # Last 100 pending
            timestamp = msg.get('message_create_time', msg.get('created_at', 'Unknown time'))
            content = msg.get('content', '')
            # Truncate long content
            if len(content) > 1000:
                content = content[:1000] + "..."
            lines.append(f"**[{timestamp}]** {content}\n")

    lines.append("\n---\n")

    return "\n".join(lines)


def read_hook_input():
    """Read cwd from Claude Code hook input"""
    if not sys.stdin.isatty():
        try:
            return json.load(sys.stdin)
        except json.JSONDecodeError:
            pass
    return {'cwd': os.environ.get('CLAUDE_CWD', os.getcwd())}


def main():
    """Main execution"""
    if not _is_service_available():
        print(json.dumps({"continue": True, "suppressOutput": True, "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ""}}))
        sys.exit(0)

    try:
        # Read cwd from hook input, derive group_id from project directory
        hook_data = read_hook_input()
        cwd = hook_data.get('cwd', os.getcwd())

        config = get_env_config()
        config['group_id'] = get_project_group_id(cwd=cwd)
        client = EverMemOSClient(**config)

        # Fetch recent episodic memories (increased from 10 to 50 for richer context)
        try:
            recent_response = client.fetch_recent_memories(limit=50)
            memories = recent_response.get('result', {}).get('memories', [])
        except Exception as e:
            # If fetch fails, use empty list
            logger.warning(f"Failed to fetch recent memories: {e}")
            memories = []

        # Fetch pending messages via search API (increased from 10 to 50)
        try:
            search_response = client.search_memories("", method="hybrid", top_k=50)
            result = search_response.get('result', {})
            pending_messages = result.get('pending_messages', [])
        except Exception as e:
            # If search fails, use empty list
            logger.warning(f"Failed to fetch pending messages: {e}")
            pending_messages = []

        # Format context
        context = format_context_for_claude(memories, pending_messages)

        # Return hook output in Claude Code format
        output = {
            "continue": True,
            "suppressOutput": True,
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context
            }
        }

        print(json.dumps(output))
        sys.exit(0)

    except Exception as e:
        # On error, return empty context gracefully
        error_output = {
            "continue": True,
            "suppressOutput": True,
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": ""
            }
        }
        print(json.dumps(error_output))
        logger.error(f"Error loading context: {e}")
        sys.exit(0)  # Don't block session start on error


if __name__ == "__main__":
    main()
