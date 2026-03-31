import type { Plugin, PluginInput } from "@opencode-ai/plugin"
import { appendFileSync, readFileSync } from "fs"
import { homedir } from "os"
import { join } from "path"

// ─── Logging ──────────────────────────────────────────────────────────────────

const LOG_FILE = "/tmp/evermemos_opencode.log"

function log(level: "INFO" | "DEBUG" | "ERROR", component: string, msg: string, data?: unknown): void {
  try {
    const entry = JSON.stringify({
      ts: new Date().toISOString(),
      level,
      component,
      msg,
      ...(data !== undefined ? { data } : {}),
    })
    appendFileSync(LOG_FILE, entry + "\n")
  } catch {
    // Ignore logging errors — never let logging crash the plugin
  }
}

// ─── File-based config (for Scenario C: remote client) ────────────────────────
//
// remote_setup.py writes ~/.config/opencode/evermemos.json when the user runs
// ./install.sh with MEMORY_REMOTE_URL set. The plugin reads it as a fallback
// when env vars are not set in the shell environment.

interface FileConfig {
  baseUrl?: string
  userId?: string
  apiKey?: string
}

let _fileConfig: FileConfig | null = null

function readFileConfig(): FileConfig {
  if (_fileConfig !== null) return _fileConfig
  try {
    const configPath = join(homedir(), ".config", "opencode", "evermemos.json")
    _fileConfig = JSON.parse(readFileSync(configPath, "utf-8")) as FileConfig
  } catch {
    _fileConfig = {}
  }
  return _fileConfig
}

// ─── Config ───────────────────────────────────────────────────────────────────

function getConfig() {
  const fc = readFileConfig()
  return {
    baseUrl: (
      process.env.API_BASE_URL ??
      fc.baseUrl ??
      "http://localhost:1995"
    ).replace(/\/$/, ""),
    userId: process.env.MEMORY_USER_ID ?? fc.userId ?? "opencode_user",
    apiKey: process.env.EVERMEMOS_API_KEY ?? fc.apiKey ?? "",
  }
}

/**
 * Derive a unique group_id from the project directory path + userId.
 * Mirrors evermemos_config.py::get_project_group_id() in the Claude Code integration.
 *
 * Priority:
 *   1. EVERMEMOS_GROUP_ID env var (explicit override)
 *   2. project_<directory>_<userId>
 *   3. "project_default" if directory is empty
 */
function getProjectGroupId(directory: string, userId: string): string {
  const explicit = process.env.EVERMEMOS_GROUP_ID
  if (explicit) return explicit
  if (directory) return `project_${directory}_${userId}`
  return "project_default"
}

// ─── Auth headers ─────────────────────────────────────────────────────────────

function authHeaders(apiKey: string): Record<string, string> {
  if (!apiKey) return {}
  return { Authorization: `Bearer ${apiKey}` }
}

// ─── Health check (with 30-second cache) ─────────────────────────────────────

let _healthCacheTime = 0
let _healthCacheValue = false
const HEALTH_CACHE_TTL_MS = 30_000

async function isServiceAvailable(baseUrl: string): Promise<boolean> {
  const now = Date.now()
  if (now - _healthCacheTime < HEALTH_CACHE_TTL_MS) {
    return _healthCacheValue
  }
  try {
    const res = await fetch(`${baseUrl}/health`, {
      signal: AbortSignal.timeout(2000),
    })
    _healthCacheValue = res.ok
    _healthCacheTime = now
    return _healthCacheValue
  } catch {
    _healthCacheValue = false
    _healthCacheTime = now
    return false
  }
}

// ─── EverMemOS API ────────────────────────────────────────────────────────────

/**
 * Search for relevant memories (GET with query params).
 */
async function apiSearchMemories(
  baseUrl: string,
  userId: string,
  groupId: string,
  apiKey: string,
  query: string,
  method = "hybrid",
  topK = 5,
): Promise<any> {
  const params = new URLSearchParams({
    user_id: userId,
    group_id: groupId,
    retrieve_method: method,
    top_k: String(topK),
    memory_types: "episodic_memory,event_log,foresight",
  })
  if (query) params.set("query", query)
  const res = await fetch(`${baseUrl}/api/v1/memories/search?${params}`, {
    headers: authHeaders(apiKey),
    signal: AbortSignal.timeout(10_000),
  })
  if (!res.ok) throw new Error(`Search failed: HTTP ${res.status}`)
  return res.json()
}

/**
 * Store a conversation message.
 * Mirrors evermemos_client.py::store_message().
 */
async function apiStoreMessage(
  baseUrl: string,
  userId: string,
  groupId: string,
  apiKey: string,
  content: string,
  role: "user" | "assistant",
  senderName: string,
): Promise<void> {
  const body = {
    message_id: `msg_${Date.now()}`,
    create_time: new Date().toISOString(),
    sender: userId,
    sender_name: senderName,
    content,
    role,
    group_id: groupId,
  }
  const res = await fetch(`${baseUrl}/api/v1/memories`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(apiKey) },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(15_000),
  })
  if (!res.ok) throw new Error(`Store failed: HTTP ${res.status}`)
}

/**
 * Fetch recent episodic memories (GET with query params).
 * Mirrors evermemos_client.py::fetch_recent_memories().
 */
async function apiFetchRecentMemories(
  baseUrl: string,
  userId: string,
  groupId: string,
  apiKey: string,
  limit = 50,
): Promise<any> {
  const params = new URLSearchParams({
    user_id: userId,
    group_id: groupId,
    memory_type: "episodic_memory",
    limit: String(limit),
    sort_order: "desc",
  })
  const res = await fetch(`${baseUrl}/api/v1/memories?${params}`, {
    headers: authHeaders(apiKey),
    signal: AbortSignal.timeout(10_000),
  })
  if (!res.ok) throw new Error(`FetchRecent failed: HTTP ${res.status}`)
  return res.json()
}

// ─── Formatters ───────────────────────────────────────────────────────────────

/**
 * Format episodic memories + pending messages for session-level injection.
 * Mirrors hook_session_start.py::format_context_for_claude().
 */
function formatSessionMemories(memories: any[], pendingMessages: any[]): string {
  if (!memories.length && !pendingMessages.length) return ""

  const lines: string[] = ["# 📚 Recent Memory Context\n"]

  if (memories.length > 0) {
    lines.push("## Recent Conversations:\n")
    for (const mem of memories.slice(0, 15)) {
      const ts = mem.timestamp ?? mem.start_time ?? mem.created_at ?? "?"
      const title: string = mem.title ?? mem.subject ?? "Untitled"
      const body: string = mem.episode ?? mem.summary ?? ""
      lines.push(`**[${ts}]** ${title}`)
      if (body) lines.push(`  ${body}\n`)
    }
  }

  if (pendingMessages.length > 0) {
    lines.push("## Recent Messages (Pending):\n")
    for (const msg of pendingMessages.slice(0, 100)) {
      const ts = msg.message_create_time ?? msg.created_at ?? "?"
      const content = String(msg.content ?? "").slice(0, 1000)
      lines.push(`**[${ts}]** ${content}\n`)
    }
  }

  lines.push("\n---")
  return lines.join("\n")
}

/**
 * Format search results for per-message injection.
 * Mirrors evermemos_client.py::format_search_results().
 *
 * The search response has structure:
 *   result.memories = [{group_name: [mem, mem, ...]}, ...]
 */
function formatSearchResults(memoriesGroups: any[], query: string): string {
  // Flatten the nested group structure into a single list
  const allMems: any[] = []
  for (const groupDict of memoriesGroups) {
    if (!groupDict || typeof groupDict !== "object") continue
    for (const groupMems of Object.values(groupDict)) {
      if (!Array.isArray(groupMems)) continue
      allMems.push(...groupMems)
    }
  }
  if (!allMems.length) return ""

  const lines: string[] = [`# 🔍 Relevant Memory Search Results\nQuery: ${query}\n`]
  for (const mem of allMems) {
    const ts = mem.start_time ?? mem.timestamp ?? mem.created_at ?? "?"
    const subject: string = mem.subject ?? ""
    const body: string = mem.episode ?? mem.summary ?? ""
    const content = [subject, body].filter(Boolean).join("\n  ")
    if (content) lines.push(`**[${ts}]** ${content}\n`)
  }
  lines.push("---")
  return lines.join("\n")
}

/**
 * Format a tool call record for storage.
 * Mirrors hook_tool_use.py::format_tool_observation().
 */
function formatToolObservation(tool: string, args: unknown, toolOutput: string): string {
  const lines: string[] = [
    `🔧 Tool Used: ${tool}`,
    `⏰ Time: ${new Date().toISOString()}`,
    "",
  ]
  if (args !== undefined && args !== null) {
    lines.push("📥 Input:")
    const argsStr = JSON.stringify(args, null, 2)
    lines.push(argsStr.length > 2000 ? argsStr.slice(0, 2000) + "..." : argsStr)
    lines.push("")
  }
  if (toolOutput) {
    lines.push("📤 Output:")
    lines.push(toolOutput.length > 2000 ? toolOutput.slice(0, 2000) + "..." : toolOutput)
  }
  return lines.join("\n")
}

// ─── In-memory caches ─────────────────────────────────────────────────────────

// Session-level: loaded once at session.created, cleared at session.deleted
const sessionMemoryCache = new Map<string, string>()

// Per-message: updated each time user sends a message, persists through all
// intermediate LLM calls (including tool calls within the same turn),
// replaced when the next user message arrives
const queryResultCache = new Map<string, string>()

// ─── Plugin ───────────────────────────────────────────────────────────────────

export default (async ({ project, directory }: PluginInput) => {
  log("INFO", "plugin", "EverMemOS plugin initialized", {
    project_id: project.id,
    directory,
  })

  return {
    // ── Session lifecycle ───────────────────────────────────────────────────

    event: async ({ event }: { event: any }) => {
      // ── session.created: load historical memories into cache ──────────────
      if (event.type === "session.created") {
        const sessionID: string = event.properties.info.id
        const cfg = getConfig()
        const groupId = getProjectGroupId(directory, cfg.userId)

        log("INFO", "session.created", "New session, loading memories", { sessionID })

        if (!(await isServiceAvailable(cfg.baseUrl))) {
          log("INFO", "session.created", "EverMemOS not available, skipping memory load")
          return
        }

        let memories: any[] = []
        let pendingMessages: any[] = []

        try {
          const res = await apiFetchRecentMemories(cfg.baseUrl, cfg.userId, groupId, cfg.apiKey, 50)
          memories = res?.result?.memories ?? []
        } catch (e) {
          log("ERROR", "session.created", "apiFetchRecentMemories failed", String(e))
        }

        try {
          // Use empty query to fetch all pending messages (same as Python version)
          const res = await apiSearchMemories(cfg.baseUrl, cfg.userId, groupId, cfg.apiKey, "", "hybrid", 50)
          pendingMessages = res?.result?.pending_messages ?? []
        } catch (e) {
          log("ERROR", "session.created", "fetchPendingMessages failed", String(e))
        }

        const formatted = formatSessionMemories(memories, pendingMessages)
        if (formatted) {
          sessionMemoryCache.set(
            sessionID,
            `<evermemos-context>\n${formatted}\n</evermemos-context>`,
          )
          log("INFO", "session.created", "Session memories cached", {
            memories: memories.length,
            pending: pendingMessages.length,
            injected_content: formatted,
          })
        } else {
          log("INFO", "session.created", "No memories found for this session")
        }
      }

      // ── session.deleted: clean up caches ──────────────────────────────────
      if (event.type === "session.deleted") {
        // Properties may carry sessionID at top level or nested under info
        const sessionID: string =
          event.properties?.sessionID ?? event.properties?.info?.id ?? ""
        sessionMemoryCache.delete(sessionID)
        queryResultCache.delete(sessionID)
        // Invalidate health cache so the next session gets a fresh check
        _healthCacheTime = 0
        log("INFO", "session.deleted", "Caches cleared", { sessionID })
      }

      if (event.type === "session.error") {
        log("ERROR", "session.error", "Session error event", event.properties)
      }
    },

    // ── User message: store + search ────────────────────────────────────────

    "chat.message": async (input: any, output: any) => {
      // Extract user text from output.parts (type === "text" parts)
      const textParts: string[] = (output.parts ?? [])
        .filter((p: any) => p.type === "text")
        .map((p: any) => String(p.text ?? ""))
      const userText = textParts.join("").trim() || "[media prompt]"

      const cfg = getConfig()
      const groupId = getProjectGroupId(directory, cfg.userId)

      log("DEBUG", "chat.message", "User message received", {
        sessionID: input.sessionID,
        source: "user_input",
        content: userText,
      })

      if (!(await isServiceAvailable(cfg.baseUrl))) {
        log("INFO", "chat.message", "EverMemOS not available, skipping")
        return
      }

      // Run store and search concurrently to minimize latency.
      // Both have .catch() so Promise.all won't reject on individual failures.
      const [, searchOutcome] = await Promise.all([
        apiStoreMessage(cfg.baseUrl, cfg.userId, groupId, cfg.apiKey, userText, "user", "User").catch((e) =>
          log("ERROR", "chat.message", "storeMessage failed", String(e)),
        ),
        apiSearchMemories(cfg.baseUrl, cfg.userId, groupId, cfg.apiKey, userText, "hybrid", 5).catch((e) => {
          log("ERROR", "chat.message", "searchMemories failed", String(e))
          return null
        }),
      ])

      if (searchOutcome) {
        const memoriesGroups: any[] = searchOutcome?.result?.memories ?? []
        const formatted = formatSearchResults(memoriesGroups, userText)
        if (formatted) {
          queryResultCache.set(
            input.sessionID,
            `<evermemos-search-results>\n${formatted}\n</evermemos-search-results>`,
          )
          log("DEBUG", "chat.message", "Query cache updated", {
            query: userText,
            groups: memoriesGroups.length,
            search_result: formatted,
          })
        }
      }
    },

    // ── Inject memories into every LLM call ─────────────────────────────────

    "experimental.chat.system.transform": async (input: any, output: any) => {
      const sessionMem = sessionMemoryCache.get(input.sessionID)
      if (sessionMem) output.system.push(sessionMem)

      const queryMem = queryResultCache.get(input.sessionID)
      if (queryMem) output.system.push(queryMem)

      log("DEBUG", "chat.system.transform", "Injection complete", {
        sessionID: input.sessionID,
        session_injected: !!sessionMem,
        query_injected: !!queryMem,
      })
    },

    // ── Record tool calls ────────────────────────────────────────────────────

    "tool.execute.after": async (input: any, output: any) => {
      const cfg = getConfig()
      const groupId = getProjectGroupId(directory, cfg.userId)

      if (!(await isServiceAvailable(cfg.baseUrl))) return

      const observation = formatToolObservation(
        input.tool,
        input.args,
        String(output.output ?? ""),
      )

      // Fire-and-forget: don't block the tool execution pipeline
      apiStoreMessage(
        cfg.baseUrl,
        cfg.userId,
        groupId,
        cfg.apiKey,
        observation,
        "assistant",
        "OpenCode (Tool)",
      ).catch((e) => log("ERROR", "tool.execute.after", "storeMessage failed", String(e)))

      log("DEBUG", "tool.execute.after", "Storing to EverMemOS", {
        source: "tool",
        tool: input.tool,
        content: observation,
      })
    },

    // ── Record AI text responses ─────────────────────────────────────────────

    "experimental.text.complete": async (input: any, output: any) => {
      const text = String(output.text ?? "").trim()
      // Skip trivially short fragments (e.g. single punctuation mid-stream)
      if (text.length < 10) return

      const cfg = getConfig()
      const groupId = getProjectGroupId(directory, cfg.userId)

      if (!(await isServiceAvailable(cfg.baseUrl))) return

      // Fire-and-forget: don't block response rendering
      apiStoreMessage(
        cfg.baseUrl,
        cfg.userId,
        groupId,
        cfg.apiKey,
        text,
        "assistant",
        "OpenCode (Response)",
      ).catch((e) => log("ERROR", "text.complete", "storeMessage failed", String(e)))

      log("DEBUG", "text.complete", "Storing to EverMemOS", {
        source: "opencode_response",
        content: text,
      })
    },
  }
}) satisfies Plugin
