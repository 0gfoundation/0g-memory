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
    from evermemos_config import is_project_excluded
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
    base_url = os.environ.get('EVERMEMOS_BASE_URL', 'http://localhost:1995')
    try:
        urllib.request.urlopen(f"{base_url}/health", timeout=1)
        return True
    except Exception:
        return False


def read_hook_input():
    """
    Read hook input from Claude Code

    Expected fields for SessionEnd:
    - sessionId: string
    - cwd: string (current working directory)
    - reason: string (why the session ended)
    """
    # Method 1: Try environment variable first
    hook_input_env = os.environ.get('CLAUDE_HOOK_INPUT')
    if hook_input_env:
        try:
            return json.loads(hook_input_env)
        except json.JSONDecodeError:
            pass

    # Method 2: Try reading from stdin
    if not sys.stdin.isatty():
        try:
            return json.load(sys.stdin)
        except json.JSONDecodeError:
            pass

    # Method 3: Build from individual environment variables
    return {
        'sessionId': os.environ.get('CLAUDE_SESSION_ID', 'unknown'),
        'cwd': os.environ.get('CLAUDE_CWD', os.getcwd()),
        'reason': os.environ.get('CLAUDE_SESSION_END_REASON', 'other'),
    }


def get_env_config():
    """Get EverMemOS configuration from environment variables"""
    return {
        'base_url': os.environ.get('EVERMEMOS_BASE_URL', 'http://localhost:1995'),
        'user_id': os.environ.get('EVERMEMOS_USER_ID', 'claude_code_user'),
        'group_id': os.environ.get('EVERMEMOS_GROUP_ID', 'session_2026'),
    }


def generate_session_summary(session_id, reason, client):
    """
    Generate a summary of the entire session

    Args:
        session_id: Session identifier
        reason: Why the session ended
        client: EverMemOSClient instance

    Returns:
        str: Summary text
    """
    try:
        # Fetch all messages from this session via search API
        # Use empty query to get all messages (max 100 due to API limit)
        response = client.search_memories("", method="hybrid", top_k=100)
        result = response.get('result', {})

        # Get episodic memories and pending messages
        memories_groups = result.get('memories', [])
        pending_messages = result.get('pending_messages', [])

        # Extract memories from groups
        all_memories = []
        for group_dict in memories_groups:
            for group_name, group_memories in group_dict.items():
                all_memories.extend(group_memories)

        # Count different types of messages
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

        # Calculate conversation turns (user input + Claude response pairs)
        conversation_turns = min(user_messages, claude_responses)

        # Get time span
        first_time = None
        last_time = None

        if pending_messages:
            times = [msg.get('message_create_time', '') for msg in pending_messages if msg.get('message_create_time')]
            if times:
                times_sorted = sorted(times)
                first_time = times_sorted[0]
                last_time = times_sorted[-1]

        # Calculate session duration
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

        # Generate summary
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
        # If summary generation fails, return a simple summary
        logger.warning(f"Failed to generate detailed summary: {e}")
        return f"📊 Session Complete\n\nSession ID: {session_id}\nEnd Time: {datetime.now().isoformat()}\nEnd Reason: {reason}\n\n⚠️ Summary generation encountered an error, but session ended successfully."


def find_transcript_path(session_id):
    """Find transcript file path for given session_id"""
    try:
        claude_dir = os.path.expanduser('~/.claude/projects')

        for root, dirs, files in os.walk(claude_dir):
            for file in files:
                if file.startswith(session_id) and file.endswith('.jsonl'):
                    return os.path.join(root, file)

        return None
    except Exception as e:
        logger.warning(f"Failed to find transcript: {e}")
        return None


def extract_all_assistant_messages(transcript_path):
    """
    Extract ALL assistant messages with text content from transcript

    Returns:
        list: List of tuples (timestamp, message_text)
    """
    if not transcript_path or not os.path.exists(transcript_path):
        return []

    messages = []

    try:
        with open(transcript_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()

        if not content:
            return []

        lines = content.split('\n')

        for line in lines:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if entry.get('type') != 'assistant':
                continue

            timestamp = entry.get('timestamp', '')
            msg_content = entry.get('message', {}).get('content')

            if not msg_content:
                continue

            text = ''
            if isinstance(msg_content, str):
                text = msg_content
            elif isinstance(msg_content, list):
                text_parts = []
                for item in msg_content:
                    if isinstance(item, dict) and item.get('type') == 'text':
                        text_parts.append(item.get('text', ''))
                text = '\n'.join(text_parts)

            # Strip system-reminder tags
            if text:
                import re
                text = re.sub(r'<system-reminder>[\s\S]*?</system-reminder>', '', text)
                text = re.sub(r'\n{3,}', '\n\n', text).strip()

            if text and len(text) > 20:  # Only include substantial messages
                messages.append((timestamp, text))

        return messages

    except Exception as e:
        logger.warning(f"Failed to extract all messages: {e}")
        return []


def batch_store_missing_messages(messages, client, existing_pending):
    """
    Store messages that are not already in EverMemOS

    Args:
        messages: List of (timestamp, text) tuples
        client: EverMemOSClient instance
        existing_pending: Existing pending messages from EverMemOS

    Returns:
        int: Number of new messages stored
    """
    # Build set of existing message content (first 100 chars as fingerprint)
    existing_fingerprints = set()
    for msg in existing_pending:
        content = msg.get('content', '')
        fingerprint = content[:100] if len(content) >= 100 else content
        existing_fingerprints.add(fingerprint)

    stored_count = 0

    for timestamp, text in messages:
        # Check if this message is already stored
        fingerprint = text[:100] if len(text) >= 100 else text

        if fingerprint in existing_fingerprints:
            logger.debug(f"Skipping duplicate message: {timestamp}")
            continue

        # Store new message
        try:
            result = client.store_message(
                content=text,
                role="user",
                sender_name="Claude (Response)"
            )
            logger.debug(f"Stored missing message from {timestamp} ({len(text)} chars):\n{'='*60}\n{text}\n{'='*60}")
            stored_count += 1

            # Add to existing fingerprints to avoid duplicates
            existing_fingerprints.add(fingerprint)

        except Exception as e:
            logger.warning(f"Failed to store message: {e}")

    return stored_count


def main():
    """Main execution"""
    if not _is_service_available():
        print(json.dumps({"continue": True, "suppressOutput": True}))
        sys.exit(0)

    try:
        # Read hook input
        hook_data = read_hook_input()

        session_id = hook_data.get('sessionId', 'unknown')
        cwd = hook_data.get('cwd', '')
        reason = hook_data.get('reason', 'other')
        transcript_path = hook_data.get('transcript_path')

        # Debug: log received data
        logger.debug(f"SessionEnd: sessionId={session_id}, cwd={cwd}, reason={reason}")

        # Check if project is excluded from tracking (matches claude-mem behavior)
        if is_project_excluded(cwd):
            logger.debug(f"Project excluded from tracking: {cwd}")
            output = {"continue": True, "suppressOutput": True}
            print(json.dumps(output))
            sys.exit(0)

        # Get configuration
        config = get_env_config()

        # Use session_id as group_id to organize by session
        if os.environ.get('EVERMEMOS_GROUP_ID') is None:
            config['group_id'] = f"session_{session_id}"

        logger.debug(f"Using config: {config}")

        client = EverMemOSClient(**config)

        # OPTION 3: Batch process all assistant messages from transcript
        logger.debug("=== OPTION 3: Batch processing transcript ===")

        if not transcript_path:
            transcript_path = find_transcript_path(session_id)
            logger.debug(f"Found transcript path: {transcript_path}")

        if transcript_path:
            # Extract all assistant messages
            logger.debug("Extracting all assistant messages from transcript...")
            all_messages = extract_all_assistant_messages(transcript_path)
            logger.debug(f"Found {len(all_messages)} assistant messages with text")

            if all_messages:
                # Get existing pending messages to avoid duplicates
                try:
                    response = client.search_memories("", method="hybrid", top_k=200)
                    existing_pending = response.get('result', {}).get('pending_messages', [])
                    logger.debug(f"Found {len(existing_pending)} existing pending messages")
                except Exception as e:
                    logger.warning(f"Failed to fetch existing messages: {e}")
                    existing_pending = []

                # Batch store missing messages
                stored_count = batch_store_missing_messages(all_messages, client, existing_pending)
                logger.debug(f"Stored {stored_count} new messages (skipped {len(all_messages) - stored_count} duplicates)")
        else:
            logger.debug("No transcript path available for batch processing")

        # Generate complete session summary
        logger.debug("Generating complete session summary...")
        summary = generate_session_summary(session_id, reason, client)

        logger.debug(f"Storing session summary to EverMemOS... (length: {len(summary)} chars)")

        # Store summary as user message with special sender name
        # Use role="user" because EverMemOS only includes user messages in pending_messages
        result = client.store_message(
            content=summary,
            role="user",
            sender_name="System (Session Complete)"
        )

        # Log success
        logger.debug(f"Session summary stored successfully: {result.get('message', 'OK')}")

        # Return success
        output = {"continue": True, "suppressOutput": True}
        print(json.dumps(output))
        sys.exit(0)

    except Exception as e:
        # Log error but don't block session end
        logger.error(f"Failed to generate/store session summary: {e}")
        import traceback
        traceback.print_exc(file=sys.stderr)

        # Return success anyway (graceful failure)
        output = {"continue": True, "suppressOutput": True}
        print(json.dumps(output))
        sys.exit(0)


if __name__ == "__main__":
    main()
