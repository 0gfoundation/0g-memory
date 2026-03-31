#!/usr/bin/env python3
"""
SessionEnd Hook for EverMemOS
Generate session summary when Claude Code session terminates (only once)
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
logger = get_logger("hook_session_end")


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

    Expected fields for SessionEnd:
    - session_id: string
    - cwd: string (current working directory)
    - reason: string (why the session ended)
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
        'reason': os.environ.get('CLAUDE_SESSION_END_REASON', 'other'),
    }


def get_env_config():
    """Get EverMemOS configuration from environment variables"""
    return {
        'base_url': os.environ.get('API_BASE_URL', 'http://localhost:1995'),
        'user_id': os.environ.get('MEMORY_USER_ID', 'claude_code_user'),
    }


def generate_session_summary(session_id, reason, client):
    """
    Generate a summary of the entire session
    """
    try:
        response = client.search_memories("", method="hybrid", top_k=100)
        result = response.get('result', {})

        memories_groups = result.get('memories', [])
        pending_messages = result.get('pending_messages', [])

        all_memories = []
        for group_dict in memories_groups:
            for group_name, group_memories in group_dict.items():
                all_memories.extend(group_memories)

        user_messages = 0
        claude_responses = 0
        tool_observations = 0
        system_messages = 0

        for msg in pending_messages:
            sender_name = msg.get('sender_name', '')
            if 'Tool' in sender_name:
                tool_observations += 1
            elif 'Claude (Response)' in sender_name:
                claude_responses += 1
            elif 'System' in sender_name:
                system_messages += 1
            else:
                user_messages += 1

        conversation_turns = min(user_messages, claude_responses)

        first_time = None
        last_time = None

        if pending_messages:
            times = [msg.get('message_create_time', '') for msg in pending_messages if msg.get('message_create_time')]
            if times:
                times_sorted = sorted(times)
                first_time = times_sorted[0]
                last_time = times_sorted[-1]

        duration_str = "Unknown"
        if first_time and last_time:
            try:
                from dateutil import parser
                start = parser.parse(first_time)
                end = parser.parse(last_time)
                duration = end - start
                hours = int(duration.total_seconds() // 3600)
                minutes = int((duration.total_seconds() % 3600) // 60)
                seconds = int(duration.total_seconds() % 60)
                if hours > 0:
                    duration_str = f"{hours}h {minutes}m {seconds}s"
                elif minutes > 0:
                    duration_str = f"{minutes}m {seconds}s"
                else:
                    duration_str = f"{seconds}s"
            except:
                duration_str = "Unable to calculate"

        lines = []
        lines.append("📊 Session Complete")
        lines.append("=" * 60)
        lines.append(f"Session ID: {session_id}")
        lines.append(f"End Time: {datetime.now().isoformat()}")
        lines.append(f"End Reason: {reason}")
        lines.append("")

        lines.append("💬 Conversation Statistics:")
        lines.append(f"  • Total Conversation Turns: {conversation_turns}")
        lines.append(f"  • User Messages: {user_messages}")
        lines.append(f"  • Claude Responses: {claude_responses}")
        lines.append(f"  • Tool Observations: {tool_observations}")
        lines.append(f"  • System Messages: {system_messages}")
        lines.append(f"  • Total Messages: {len(pending_messages)}")
        lines.append("")

        lines.append("📚 Memory Statistics:")
        lines.append(f"  • Episodic Memories: {len(all_memories)}")
        lines.append(f"  • Pending Messages: {len(pending_messages)}")
        lines.append("")

        if first_time and last_time:
            lines.append("⏰ Session Duration:")
            lines.append(f"  • Started: {first_time}")
            lines.append(f"  • Ended: {last_time}")
            lines.append(f"  • Duration: {duration_str}")
            lines.append("")

        lines.append("✅ Session ended successfully")

        return "\n".join(lines)

    except Exception as e:
        logger.warning(f"Failed to generate detailed summary: {e}")
        return f"📊 Session Complete\n\nSession ID: {session_id}\nEnd Time: {datetime.now().isoformat()}\nEnd Reason: {reason}\n\n⚠️ Summary generation encountered an error, but session ended successfully."


def main():
    """Main execution"""
    if not _is_service_available():
        print(json.dumps({"continue": True, "suppressOutput": True}))
        sys.exit(0)

    try:
        hook_data = read_hook_input()

        session_id = hook_data.get('session_id') or hook_data.get('sessionId', 'unknown')
        cwd = hook_data.get('cwd', '')
        reason = hook_data.get('reason', 'other')

        logger.debug(f"SessionEnd: sessionId={session_id}, cwd={cwd}, reason={reason}")

        config = get_env_config()
        config['group_id'] = get_project_group_id(cwd=cwd, user_id=config['user_id'])

        client = EverMemOSClient(**config)

        summary = generate_session_summary(session_id, reason, client)

        logger.info(f"Session summary:\n{summary}")

        print(json.dumps({"continue": True, "suppressOutput": True}))
        sys.exit(0)

    except Exception as e:
        logger.error(f"Failed to generate/store session summary: {e}")
        import traceback
        traceback.print_exc(file=sys.stderr)

        print(json.dumps({"continue": True, "suppressOutput": True}))
        sys.exit(0)


if __name__ == "__main__":
    main()
