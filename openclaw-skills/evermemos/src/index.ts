import type { OpenClawPluginApi } from "openclaw/plugin-sdk/core"
import { appendFileSync } from "fs"

// ─── Logging ──────────────────────────────────────────────────────────────────

const LOG_FILE = "/tmp/evermemos_openclaw.log"

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
    // Never let logging crash the plugin
  }
}

// ─── Config ───────────────────────────────────────────────────────────────────

interface PluginConfig {
  baseUrl: string
  userId: string
  apiKey: string
  searchTopK: number
}

function resolveConfig(pluginConfig: Record<string, unknown> | undefined): PluginConfig {
  return {
    baseUrl: String(pluginConfig?.apiBaseUrl ?? process.env.API_BASE_URL ?? "http://localhost:1995").replace(/\/$/, ""),
    userId: String(pluginConfig?.userId ?? process.env.MEMORY_USER_ID ?? "default_user"),
    apiKey: String(pluginConfig?.apiKey ?? process.env.EVERMEMOS_API_KEY ?? ""),
    searchTopK: Number(pluginConfig?.searchTopK ?? 5),
  }
}

function authHeaders(apiKey: string): Record<string, string> {
  if (!apiKey) return {}
  return { Authorization: `Bearer ${apiKey}` }
}

/**
 * Derive a unique group_id for EverMemOS namespace isolation.
 *
 * The "openclaw" tag ensures memory is isolated from other AI assistants
 * (Claude Code, OpenCode) even when they share the same userId and project path.
 *
 * Priority:
 *   1. EVERMEMOS_GROUP_ID env var (explicit override)
 *   2. session_<sessionKey>_openclaw_<userId>   (e.g. "main", "tui-xxx") — preferred
 *   3. project_<workspaceDir>_openclaw_<userId> (fallback when sessionKey unavailable)
 *   4. channel_<channelId>_openclaw_<userId>    (fallback when workspaceDir also unavailable)
 *   5. project_openclaw_<userId>                (last resort)
 *
 * sessionKey is the preferred identifier because OpenClaw sessions all share the
 * same default workspaceDir, making it a poor isolation key.  workspaceDir and
 * channelId are kept as fallbacks for channels that do not expose sessionKey.
 */
function deriveGroupId(opts: {
  sessionKey?: string
  workspaceDir?: string
  channelId?: string
  userId: string
}): string {
  const explicit = process.env.EVERMEMOS_GROUP_ID
  if (explicit) return explicit
  if (opts.sessionKey) return `session_${opts.sessionKey}_openclaw_${opts.userId}`
  if (opts.workspaceDir) return `project_${opts.workspaceDir}_openclaw_${opts.userId}`
  if (opts.channelId) return `channel_${opts.channelId}_openclaw_${opts.userId}`
  return `project_openclaw_${opts.userId}`
}

// ─── Health check (30-second cache) ──────────────────────────────────────────

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

async function apiSearchMemories(
  baseUrl: string,
  userId: string,
  groupId: string,
  apiKey: string,
  query: string,
  topK = 5,
): Promise<any> {
  const params = new URLSearchParams({
    user_id: userId,
    group_id: groupId,
    retrieve_method: "hybrid",
    top_k: String(topK),
    memory_types: "episodic_memory,event_log,foresight",
  })
  if (query) params.set("query", query)
  const res = await fetch(`${baseUrl}/api/v1/memories/search?${params}`, {
    headers: authHeaders(apiKey),
    signal: AbortSignal.timeout(40_000),
  })
  if (!res.ok) throw new Error(`Search failed: HTTP ${res.status}`)
  return res.json()
}

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
    message_id: `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
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


function formatSearchResults(memoriesGroups: any[], query: string): string {
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

function formatToolObservation(toolName: string, params: unknown, result: unknown): string {
  const lines: string[] = [
    `🔧 Tool Used: ${toolName}`,
    `⏰ Time: ${new Date().toISOString()}`,
    "",
  ]
  if (params !== undefined && params !== null) {
    lines.push("📥 Input:")
    const paramsStr = JSON.stringify(params, null, 2)
    lines.push(paramsStr.length > 20000 ? paramsStr.slice(0, 20000) + "..." : paramsStr)
    lines.push("")
  }
  const resultStr = result !== undefined && result !== null
    ? (typeof result === "string" ? result : JSON.stringify(result, null, 2))
    : ""
  if (resultStr) {
    lines.push("📤 Output:")
    lines.push(resultStr.length > 20000 ? resultStr.slice(0, 20000) + "..." : resultStr)
  }
  return lines.join("\n")
}

// ─── In-memory caches ─────────────────────────────────────────────────────────

// sessionId → groupId: set at before_prompt_build, used by llm_output + after_tool_call
const groupIdBySession = new Map<string, string>()

// channelId → groupId: used in session_end to identify which channel caches to clean up
const groupIdByChannel = new Map<string, string>()

// channelId → formatted search results: written by before_prompt_build, read on the next turn
const queryResultCache = new Map<string, string>()

// channelId → raw user message content buffered by message_received.
// Flushed (stored + searched) in before_prompt_build where the correct groupId is known.
const pendingUserMessage = new Map<string, string>()

// ─── Plugin ───────────────────────────────────────────────────────────────────

export default {
  id: "evermemos-openclaw",
  name: "EverMemOS",
  description: "Persistent memory integration via EverMemOS + 0G chain storage",

  register(api: OpenClawPluginApi) {
    // ── before_prompt_build: store user message + per-message search + inject ──
    api.on("before_prompt_build", async (event, ctx) => {
      const cfg = resolveConfig(api.pluginConfig)
      const sessionId = ctx.sessionId
      const channelId = ctx.channelId

      // Derive and cache the authoritative group_id.
      // This is the only place where group_id is derived; all other hooks read from these caches.
      const groupId = deriveGroupId({
        sessionKey: ctx.sessionKey ?? undefined,
        workspaceDir: ctx.workspaceDir,
        channelId: channelId ?? undefined,
        userId: cfg.userId,
      })
      if (sessionId) groupIdBySession.set(sessionId, groupId)
      if (channelId) groupIdByChannel.set(channelId, groupId)

      // Peek at the buffered user message — do NOT delete yet.
      // Deletion is deferred until we confirm the service is available so that
      // a temporarily-unavailable backend does not silently drop the message.
      // When unavailable, the message stays in pendingUserMessage and will be
      // retried on the next before_prompt_build (or overwritten by a newer
      // message_received, which is acceptable).
      const pendingContent = channelId ? pendingUserMessage.get(channelId) : undefined

      // Single health check for this hook invocation
      const available = await isServiceAvailable(cfg.baseUrl)

      // ── Store user message + search memories with correct groupId ─────────────
      // OpenClaw maintains its own session history, so recent-memory injection is
      // unnecessary here (unlike Claude Code / OpenCode where each launch is a fresh
      // process).  Only per-message semantic search is injected.
      //
      // Consume (delete) the pending message only when we are actually going to store it.
      // If the service is unavailable, leave it in the map so the next turn can retry.
      const needsStoreSearch = pendingContent !== undefined && available
      if (needsStoreSearch && channelId) pendingUserMessage.delete(channelId)

      if (needsStoreSearch) {
        const [, searchOutcome] = await Promise.allSettled([
          apiStoreMessage(cfg.baseUrl, cfg.userId, groupId, cfg.apiKey, pendingContent!, "user", "User").catch((e) =>
            log("ERROR", "before_prompt_build", "storeMessage(user) failed", String(e)),
          ),
          apiSearchMemories(cfg.baseUrl, cfg.userId, groupId, cfg.apiKey, pendingContent!, cfg.searchTopK).catch(
            (e) => {
              log("ERROR", "before_prompt_build", "searchMemories failed", String(e))
              return null
            },
          ),
        ])
        if (searchOutcome.status === "fulfilled" && searchOutcome.value) {
          const memoriesGroups: any[] = (searchOutcome.value as any)?.result?.memories ?? []
          const formatted = formatSearchResults(memoriesGroups, pendingContent!)
          if (channelId) {
            if (formatted) {
              queryResultCache.set(channelId, formatted)
            } else {
              queryResultCache.delete(channelId)
            }
          }
          log("DEBUG", "before_prompt_build", "Query cache updated", {
            channelId,
            groupId,
            groups: memoriesGroups.length,
            cleared: !formatted,
          })
        } else if (channelId) {
          queryResultCache.delete(channelId)
          log("DEBUG", "before_prompt_build", "Query cache cleared (search failed)", {
            channelId,
            groupId,
          })
        }
      }

      const queryMem = channelId ? queryResultCache.get(channelId) : undefined

      log("DEBUG", "before_prompt_build", "Injection summary", {
        sessionId,
        channelId,
        groupId,
        user_query: pendingContent ?? null,
        query_injected: !!queryMem,
        injected_text: queryMem ?? "",
      })

      if (!queryMem) return

      return { prependContext: `<evermemos-search-results>\n${queryMem}\n</evermemos-search-results>` }
    })

    // ── message_received: buffer user message for before_prompt_build ────────
    // We intentionally do NOT call EverMemOS here because sessionKey is not
    // available in PluginHookMessageContext.  Storing here would use a less accurate
    // group_id fallback instead of the sessionKey-based group_id, breaking
    // per-session namespace isolation (especially on the very first message).
    // The actual store + search happens in before_prompt_build where sessionKey
    // is available via PluginHookAgentContext.
    api.on("message_received", (event, ctx) => {
      const content = event.content?.trim() || "[media message]"
      const channelId = ctx.channelId
      // Overwrite any previous pending message — only the latest matters
      pendingUserMessage.set(channelId, content)
      log("DEBUG", "message_received", "User message buffered for before_prompt_build", {
        channelId,
        content: content.slice(0, 200),
      })
    })

    // ── llm_output: store assistant responses ─────────────────────────────────
    api.on("llm_output", async (event, ctx) => {
      const cfg = resolveConfig(api.pluginConfig)
      const sessionId = event.sessionId
      const texts = event.assistantTexts ?? []

      // Combine all text parts; skip trivially short fragments
      const fullText = texts.join("").trim()
      if (fullText.length < 10) return

      const groupId = sessionId ? groupIdBySession.get(sessionId) : undefined
      if (!groupId) {
        log("DEBUG", "llm_output", "No groupId for session, skipping", { sessionId })
        return
      }

      if (!(await isServiceAvailable(cfg.baseUrl))) return

      // Fire-and-forget: don't block response rendering
      apiStoreMessage(cfg.baseUrl, cfg.userId, groupId, cfg.apiKey, fullText, "assistant", "OpenClaw (Response)").catch(
        (e) => log("ERROR", "llm_output", "storeMessage failed", String(e)),
      )

      log("DEBUG", "llm_output", "Storing assistant response", {
        sessionId,
        groupId,
        length: fullText.length,
        content: fullText,
      })
    })

    // ── after_tool_call: record tool usage ────────────────────────────────────
    api.on("after_tool_call", async (event, ctx) => {
      const cfg = resolveConfig(api.pluginConfig)
      const sessionId = ctx.sessionId
      const groupId = sessionId ? groupIdBySession.get(sessionId) : undefined

      if (!groupId) {
        log("DEBUG", "after_tool_call", "No groupId for session, skipping", { sessionId, toolName: event.toolName })
        return
      }

      if (!(await isServiceAvailable(cfg.baseUrl))) return

      const observation = formatToolObservation(event.toolName, event.params, event.result)

      // Fire-and-forget: don't block the tool pipeline
      apiStoreMessage(cfg.baseUrl, cfg.userId, groupId, cfg.apiKey, observation, "assistant", "OpenClaw (Tool)").catch(
        (e) => log("ERROR", "after_tool_call", "storeMessage failed", String(e)),
      )

      log("DEBUG", "after_tool_call", "Storing tool call", {
        sessionId,
        groupId,
        tool: event.toolName,
        content: observation,
      })
    })

    // ── session_end: clean up all caches for this session ─────────────────────
    api.on("session_end", async (event, ctx) => {
      const sessionId = ctx.sessionId
      const groupId = groupIdBySession.get(sessionId)
      groupIdBySession.delete(sessionId)
      if (!groupId) return
      // Clean up only the channel caches belonging to this session's groupId.
      // channelId is not available in session_end, so we scan groupIdByChannel.
      for (const [channelId, gid] of groupIdByChannel) {
        if (gid === groupId) {
          groupIdByChannel.delete(channelId)
          queryResultCache.delete(channelId)
          pendingUserMessage.delete(channelId)
        }
      }
      // Invalidate health cache to get a fresh check on the next session
      _healthCacheTime = 0
      log("INFO", "session_end", "Session caches cleared", { sessionId })
    })

    log("INFO", "plugin", "EverMemOS OpenClaw plugin registered", {
      baseUrl: resolveConfig(api.pluginConfig).baseUrl,
    })
  },
}
