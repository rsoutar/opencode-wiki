import fs from "node:fs/promises";
import path from "node:path";

const INTERNAL_ENV = "OPENCODE_MEMORY_INTERNAL";
const STATE_DIRNAME = ".opencode/state";
const MAX_CONTEXT_CHARS = 18000;
const MAX_RECENT_LOG_LINES = 40;
const MAX_SESSION_MESSAGES = 80;

function unwrap(result) {
  return result && typeof result === "object" && "data" in result ? result.data : result;
}

function isoNow() {
  return new Date().toISOString();
}

async function readTextIfExists(filePath) {
  try {
    return await fs.readFile(filePath, "utf8");
  } catch {
    return "";
  }
}

async function ensureDir(dirPath) {
  await fs.mkdir(dirPath, { recursive: true });
}

async function readJson(filePath, fallback) {
  try {
    return JSON.parse(await fs.readFile(filePath, "utf8"));
  } catch {
    return fallback;
  }
}

async function writeJson(filePath, value) {
  await ensureDir(path.dirname(filePath));
  await fs.writeFile(filePath, JSON.stringify(value, null, 2), "utf8");
}

function collectText(parts) {
  return parts
    .filter((part) => part.type === "text" && part.text && !part.synthetic && !part.ignored)
    .map((part) => part.text.trim())
    .filter(Boolean)
    .join("\n\n");
}

function truncate(text, limit) {
  if (text.length <= limit) {
    return text;
  }
  return `${text.slice(0, limit)}\n\n...(truncated)`;
}

async function buildKnowledgeContext(rootDir) {
  const knowledgeIndex = await readTextIfExists(path.join(rootDir, "knowledge", "index.md"));
  const dailyDir = path.join(rootDir, "daily");

  let recentLog = "";
  try {
    const files = (await fs.readdir(dailyDir))
      .filter((name) => name.endsWith(".md"))
      .sort()
      .reverse();
    const latest = files[0];
    if (latest) {
      const lines = (await fs.readFile(path.join(dailyDir, latest), "utf8")).split("\n");
      recentLog = lines.slice(-MAX_RECENT_LOG_LINES).join("\n");
    }
  } catch {
    recentLog = "";
  }

  const context = [
    "## LLM Wiki",
    "",
    knowledgeIndex
      ? `### Knowledge Index\n\n${knowledgeIndex}`
      : "### Knowledge Index\n\nThe wiki is still empty.",
    "",
    recentLog ? `### Recent Daily Log\n\n${recentLog}` : "### Recent Daily Log\n\nNo daily logs yet.",
  ].join("\n");

  return truncate(context, MAX_CONTEXT_CHARS);
}

async function fetchMessages(client, directory, sessionID) {
  const response = await client.session.messages({
    sessionID,
    directory,
    limit: MAX_SESSION_MESSAGES,
  });
  return unwrap(response) ?? [];
}

function findNewMessages(messages, lastMessageID) {
  if (!lastMessageID) {
    return messages;
  }

  const lastIndex = messages.findIndex((message) => message.info.id === lastMessageID);
  if (lastIndex === -1) {
    return messages;
  }

  return messages.slice(lastIndex + 1);
}

function formatTranscript(messages) {
  const turns = [];

  for (const message of messages) {
    const role = message.info.role === "assistant" ? "Assistant" : "User";
    const text = collectText(message.parts ?? []);
    if (!text) {
      continue;
    }
    turns.push(`**${role}:** ${text}`);
  }

  return turns.join("\n\n");
}

async function spawnFlush(rootDir, sessionID, reason, transcript) {
  const stateDir = path.join(rootDir, STATE_DIRNAME);
  await ensureDir(stateDir);
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const transcriptPath = path.join(stateDir, `flush-${sessionID}-${stamp}.md`);
  await fs.writeFile(transcriptPath, transcript, "utf8");

  const child = Bun.spawn(
    [
      "uv",
      "run",
      "--directory",
      rootDir,
      "python",
      path.join(rootDir, "scripts", "flush.py"),
      transcriptPath,
      sessionID,
      reason,
    ],
    {
      cwd: rootDir,
      env: {
        ...process.env,
        [INTERNAL_ENV]: "1",
      },
      stdout: "ignore",
      stderr: "ignore",
    },
  );

  if (typeof child.unref === "function") {
    child.unref();
  }
}

export const LlmWikiPlugin = async ({ client, directory }) => {
  if (process.env[INTERNAL_ENV]) {
    return {};
  }

  const rootDir = directory;
  const stateDir = path.join(rootDir, STATE_DIRNAME);

  async function log(level, message, extra = {}) {
    try {
      await client.app.log({
        body: {
          service: "llm-wiki",
          level,
          message,
          extra,
        },
      });
    } catch {
      // Ignore logging failures so the plugin never breaks chat flow.
    }
  }

  async function maybeFlushSession(sessionID, reason) {
    const sessionStatePath = path.join(stateDir, `${sessionID}.json`);
    const sessionState = await readJson(sessionStatePath, {
      lastMessageID: null,
      lastFlushedAt: null,
      reason: null,
    });

    const messages = await fetchMessages(client, rootDir, sessionID);
    if (!messages.length) {
      return;
    }

    const newMessages = findNewMessages(messages, sessionState.lastMessageID);
    const transcript = formatTranscript(newMessages);
    const newestMessageID = messages[messages.length - 1]?.info?.id ?? null;

    if (!transcript.trim()) {
      if (newestMessageID && newestMessageID !== sessionState.lastMessageID) {
        await writeJson(sessionStatePath, {
          ...sessionState,
          lastMessageID: newestMessageID,
        });
      }
      return;
    }

    await spawnFlush(rootDir, sessionID, reason, truncate(transcript, MAX_CONTEXT_CHARS));
    await writeJson(sessionStatePath, {
      lastMessageID: newestMessageID,
      lastFlushedAt: isoNow(),
      reason,
    });
    await log("info", "Queued memory flush", { sessionID, reason, messageCount: newMessages.length });
  }

  return {
    event: async ({ event }) => {
      if (event.type === "session.idle") {
        await maybeFlushSession(event.properties.sessionID, "session.idle");
      }

      if (event.type === "session.deleted") {
        const statePath = path.join(stateDir, `${event.properties.sessionID}.json`);
        await fs.rm(statePath, { force: true });
      }
    },
    "experimental.chat.system.transform": async (_input, output) => {
      output.system.push(await buildKnowledgeContext(rootDir));
    },
    "experimental.session.compacting": async (input, output) => {
      await maybeFlushSession(input.sessionID, "session.compacting");
      output.context.push(await buildKnowledgeContext(rootDir));
    },
  };
};
