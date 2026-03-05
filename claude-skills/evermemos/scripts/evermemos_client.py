#!/usr/bin/env python3
"""
EverMemOS API Client for Claude Code

This script provides a command-line interface to interact with EverMemOS API.
"""

import json
import sys
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
import urllib.request
import urllib.parse
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evermemos_config import get_project_group_id
from evermemos_logger import get_logger

logger = get_logger("evermemos_client")


class EverMemOSClient:
    """Client for interacting with EverMemOS API"""

    def __init__(
        self,
        base_url: str = "http://localhost:1995",
        user_id: str = "claude_code_user",
        group_id: str = "project_default",
    ):
        self.base_url = base_url.rstrip("/")
        self.user_id = user_id
        self.group_id = group_id

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Make HTTP request to EverMemOS API"""
        url = f"{self.base_url}{endpoint}"

        # Add query parameters
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        # Prepare request
        headers = {"Content-Type": "application/json"}
        body = json.dumps(data).encode("utf-8") if data else None

        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else "No error details"
            raise Exception(
                f"HTTP {e.code} Error: {e.reason}\nDetails: {error_body}"
            )
        except urllib.error.URLError as e:
            raise Exception(f"Connection Error: {e.reason}")
        except Exception as e:
            raise Exception(f"Request failed: {str(e)}")

    def search_memories(
        self,
        query: str,
        method: str = "hybrid",
        top_k: int = 5,
        memory_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Search for relevant memories

        Args:
            query: Search query text
            method: Retrieval method (keyword, vector, hybrid, rrf, agentic)
            top_k: Maximum number of results
            memory_types: List of memory types to search

        Returns:
            Search results with memories
        """
        if memory_types is None:
            memory_types = ["episodic_memory", "event_log", "foresight"]

        data = {
            "query": query,
            "user_id": self.user_id,
            "group_id": self.group_id,
            "retrieve_method": method,
            "top_k": top_k,
            "memory_types": memory_types,
        }

        logger.debug(f"search_memories data: {data}")
        return self._make_request("GET", "/api/v1/memories/search", data=data)

    def store_message(
        self,
        content: str,
        role: str = "user",
        sender_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Store a conversation message

        Args:
            content: Message content
            role: Message role (user or assistant)
            sender_name: Display name of sender

        Returns:
            Storage result
        """
        message_id = f"msg_{int(datetime.now().timestamp() * 1000)}"

        if sender_name is None:
            sender_name = "User" if role == "user" else "Claude"

        data = {
            "message_id": message_id,
            "create_time": datetime.now().isoformat(),
            "sender": self.user_id if role == "user" else "assistant",
            "sender_name": sender_name,
            "content": content,
            "role": role,
            "group_id": self.group_id,
        }

        return self._make_request("POST", "/api/v1/memories", data=data)

    def fetch_recent_memories(
        self, limit: int = 10, memory_type: str = "episodic_memory"
    ) -> Dict[str, Any]:
        """
        Fetch recent conversation history

        Args:
            limit: Number of recent memories to fetch
            memory_type: Type of memories to fetch

        Returns:
            Recent memories
        """
        params = {
            "user_id": self.user_id,
            "group_id": self.group_id,
            "memory_type": memory_type,
            "limit": str(limit),
            "sort_order": "desc",
        }

        return self._make_request("GET", "/api/v1/memories", params=params)


def format_search_results(response: Dict[str, Any]) -> str:
    """Format search results for display"""
    result = response.get("result", {})
    memories = result.get("memories", [])

    if not memories:
        return "❌ No relevant memories found."

    output = ["✅ Found relevant memories:\n"]

    for group_dict in memories:
        # Each group is a dict with group_id as key
        for group_name, group_memories in group_dict.items():
            output.append(f"📁 {group_name}")

            for mem in group_memories:
                # Use original message time: start_time > timestamp > created_at (all UTC)
                timestamp = mem.get("start_time") or mem.get("timestamp") or mem.get("created_at", "Unknown time")
                subject = mem.get("subject", "")
                summary = mem.get("summary", "")
                episode = mem.get("episode", "")

                # Use subject as title, show summary or episode
                content = f"{subject}\n{summary or episode}" if subject or summary or episode else "No content"

                output.append(f"  ⏰ [{timestamp}]")
                output.append(f"  💬 {content}")
                output.append("")  # Empty line

    return "\n".join(output)


def format_recent_memories(response: Dict[str, Any], pending_response: Dict[str, Any] = None) -> str:
    """Format recent memories for display, including pending messages"""
    result = response.get("result", {})
    memories = result.get("memories", [])

    # Collect all items (memories + pending messages)
    all_items = []

    # Add episodic memories
    for mem in memories:
        # Prioritize start_time as it contains the actual message time, not the query time
        timestamp = mem.get("start_time") or mem.get("timestamp") or mem.get("created_at", "Unknown time")
        title = mem.get("title", "")
        summary = mem.get("summary", "")
        content = f"{title}\n{summary}" if title or summary else "No content"

        all_items.append({
            "timestamp": timestamp,
            "content": content,
            "type": "memory"
        })

    # Add pending messages from search response (if provided)
    if pending_response:
        pending_result = pending_response.get("result", {})
        pending_messages = pending_result.get("pending_messages", [])

        for msg in pending_messages:
            # Use message_create_time as the primary timestamp for pending messages
            timestamp = msg.get("message_create_time") or msg.get("created_at", "Unknown time")
            content = msg.get("content", "No content")

            all_items.append({
                "timestamp": timestamp,
                "content": content,
                "type": "pending"
            })

    if not all_items:
        return "❌ No recent memories or messages found."

    # Sort by timestamp (most recent first)
    try:
        all_items.sort(key=lambda x: x["timestamp"], reverse=True)
    except:
        pass  # If sorting fails, keep original order

    output = ["✅ Recent conversation history:\n"]

    for item in all_items:
        timestamp = item["timestamp"]
        content = item["content"]
        item_type = item["type"]

        # Add type indicator for pending messages
        type_indicator = " 🔄 [Pending]" if item_type == "pending" else ""

        output.append(f"⏰ [{timestamp}]{type_indicator}")
        output.append(f"💬 {content}\n")

    return "\n".join(output)


def main():
    """Main CLI interface"""
    if len(sys.argv) < 2:
        logger.info(
            """Usage:
  evermemos_client.py search <query> [method] [top_k]
  evermemos_client.py store <content> [role]
  evermemos_client.py recent [limit]

Commands:
  search   - Search for relevant memories
  store    - Store a message in memory
  recent   - Fetch recent conversation history

Environment Variables:
  EVERMEMOS_BASE_URL - API base URL (default: http://localhost:1995)
  EVERMEMOS_USER_ID  - User ID (default: claude_code_user)
  EVERMEMOS_GROUP_ID - Override group ID (auto-derived from cwd by default)

Examples:
  evermemos_client.py search "API design patterns"
  evermemos_client.py search "bug fix" hybrid 10
  evermemos_client.py store "Fixed authentication bug" assistant
  evermemos_client.py recent 20
"""
        )
        sys.exit(1)

    # Initialize client, derive group_id from cwd if not explicitly set
    client = EverMemOSClient(
        base_url=os.environ.get("EVERMEMOS_BASE_URL", "http://localhost:1995"),
        user_id=os.environ.get("EVERMEMOS_USER_ID", "claude_code_user"),
        group_id=get_project_group_id(cwd=os.getcwd()),
    )

    command = sys.argv[1].lower()

    try:
        if command == "search":
            if len(sys.argv) < 3:
                logger.error("❌ Error: Missing search query")
                sys.exit(1)

            query = sys.argv[2]
            method = sys.argv[3] if len(sys.argv) > 3 else "hybrid"
            top_k = int(sys.argv[4]) if len(sys.argv) > 4 else 5

            logger.info(f"🔍 Searching memories for: '{query}'")
            logger.info(f"   Method: {method}, Top K: {top_k}\n")

            response = client.search_memories(query, method, top_k)
            logger.info(format_search_results(response))

        elif command == "store":
            if len(sys.argv) < 3:
                logger.error("❌ Error: Missing message content")
                sys.exit(1)

            content = sys.argv[2]
            role = sys.argv[3] if len(sys.argv) > 3 else "user"

            logger.info(f"💾 Storing message as '{role}'...")

            response = client.store_message(content, role)
            result = response.get("result", {})
            count = result.get("count", 0)

            logger.info(f"✅ Message stored successfully")
            logger.info(f"   Extracted {count} memories")

        elif command == "recent":
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10

            logger.info(f"📜 Fetching {limit} recent memories...\n")

            # Fetch recent episodic memories
            response = client.fetch_recent_memories(limit)

            # Also fetch pending messages via search API
            # Use a broad search to capture pending messages
            try:
                pending_response = client.search_memories("", "hybrid", limit)
            except:
                pending_response = None  # If search fails, continue without pending

            logger.info(format_recent_memories(response, pending_response))

        else:
            logger.error(f"❌ Unknown command: {command}")
            logger.info("   Valid commands: search, store, recent")
            sys.exit(1)

    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
