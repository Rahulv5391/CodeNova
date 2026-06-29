import { api } from "@/lib/api";
import { Repository, TreeNode } from "@/types/repo";

export type ChatMessage = {
  id?: string;
  message_id?: string;
  _id?: string;
  role: "user" | "assistant";
  content: string;
};

export function getChatMessageId(message: ChatMessage) {
  const id = message.id ?? message.message_id ?? message._id;

  return id ? String(id) : null;
}

export type RepositoryWorkspace = {
  repo: Repository;
  tree: TreeNode[];
  chat: {
    session_id: string;
    session_title?: string | null;
    messages: ChatMessage[];
  };
};

export type ChatSessionSummary = {
  id: string;
  repository_id: string;
  title: string;
  created_at: string;
};

export type ChatSessionDetail = ChatSessionSummary & {
  messages: ChatMessage[];
};

type ChatSessionDetailResponse =
  | ChatSessionDetail
  | {
      session: ChatSessionSummary;
      messages: ChatMessage[];
    };

function normalizeChatSessionDetail(
  data: ChatSessionDetailResponse,
): ChatSessionDetail {
  if ("session" in data) {
    return {
      ...data.session,
      messages: Array.isArray(data.messages) ? data.messages : [],
    };
  }

  return {
    ...data,
    messages: Array.isArray(data.messages) ? data.messages : [],
  };
}

export type ChatCommand = {
  name: string;
  command: string;
  title: string;
  description: string;
  usage: string;
  requires_query: boolean;
};

export type ChatModel = {
  id: string;
  label: string;
};

export type ChatModelsResponse = {
  default_model: string;
  models: ChatModel[];
};

export type ChatStreamEvent =
  | { type: "start"; message_id?: string; intent?: string }
  | { type: "delta"; text: string }
  | { type: "sources"; data: unknown }
  | { type: "relations"; data: unknown }
  | { type: "usage"; data: unknown }
  | { type: "done" }
  | { type: string; text?: string; data?: unknown; [key: string]: unknown };

export async function getRepositoryWorkspace(repositoryId: string) {
  const { data } = await api.get<RepositoryWorkspace>(`/repos/${repositoryId}`);

  return data;
}

export async function getChatSessions() {
  const { data } = await api.get<ChatSessionSummary[]>("/chat/sessions");

  return data;
}

export async function getChatSession(sessionId: string) {
  try {
    const { data } = await api.get<ChatSessionDetailResponse>(
      `/sessions/${sessionId}`,
    );

    return normalizeChatSessionDetail(data);
  } catch (error) {
    const status = (error as { response?: { status?: number } }).response
      ?.status;

    if (status !== 404) {
      throw error;
    }

    const { data } = await api.get<ChatSessionDetailResponse>(
      `/chat/sessions/${sessionId}`,
    );

    return normalizeChatSessionDetail(data);
  }
}

export async function getChatCommands() {
  const { data } = await api.get<ChatCommand[]>("/chat/commands");

  return data;
}

export async function getChatModels() {
  const { data } = await api.get<ChatModelsResponse>("/chat/models");

  return data;
}

export async function deleteChatMessages(messageIds: string[]) {
  await api.delete("/chat/messages", {
    data: {
      message_ids: messageIds,
    },
  });
}

export async function sendChatMessage(sessionId: string, question: string) {
  const { data } = await api.post<{
    session_id: string;
    session_title?: string | null;
    message?: ChatMessage;
    usage?: unknown;
  }>(`/chat/sessions/${sessionId}/messages`, { question });

  return data;
}

export async function streamChatMessage(
  sessionId: string,
  question: string,
  model: string | null,
  onEvent: (event: ChatStreamEvent) => void,
) {
  const response = await fetch(
    `${api.defaults.baseURL ?? ""}/chat/sessions/${sessionId}/stream`,
    {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(model ? { question, model } : { question }),
    },
  );

  if (!response.ok) {
    throw new Error("Unable to stream chat response.");
  }

  if (!response.body) {
    throw new Error("Chat stream response did not include a body.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const emitPayload = (payload: string) => {
    if (!payload || payload === "[DONE]" || !payload.startsWith("{")) {
      return;
    }

    onEvent(JSON.parse(payload) as ChatStreamEvent);
  };

  while (true) {
    const { done, value } = await reader.read();

    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      const trimmed = line.trim();

      if (!trimmed) {
        continue;
      }

      const payload = trimmed.startsWith("data:")
        ? trimmed.slice("data:".length).trim()
        : trimmed;

      emitPayload(payload);
    }
  }

  const remaining = `${buffer}${decoder.decode()}`.trim();

  if (remaining && remaining !== "[DONE]") {
    const payload = remaining.startsWith("data:")
      ? remaining.slice("data:".length).trim()
      : remaining;

    emitPayload(payload);
  }
}

export async function createChatSession(repositoryId: string) {
  const { data } = await api.post<{ id: string }>("/chat/sessions", {
    repository_id: repositoryId,
  });

  return data;
}
