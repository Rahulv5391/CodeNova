"use client";

import { MobileHint } from "@/components/AppShell";
import { FileTree } from "@/components/repo/TreeItem";
import { queryKeys } from "@/lib/query-keys";
import {
  ChatModel,
  ChatMessage,
  ChatSessionSummary,
  getChatSession,
  getChatSessions,
  getChatMessageId,
  createChatSession,
  deleteChatMessages,
  getChatModels,
  getRepositoryWorkspace,
  streamChatMessage,
} from "@/lib/repository-api";
import { RepositoryStatus } from "@/types/repo";
import { getStatusLabel } from "@/utils/repo";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  GitBranch,
  Loader2,
} from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { ChatHistoryPanel } from "@/components/chat/ChatHistoryPanel";
import { ChatPanel } from "@/components/chat/ChatPanel";

const EMPTY_MESSAGES: ChatMessage[] = [];
const EMPTY_MODELS: ChatModel[] = [];
const TYPING_INTERVAL_MS = 26;
const MIN_TYPING_CHARS = 1;
const MAX_TYPING_CHARS = 6;
const CHAT_BOTTOM_THRESHOLD_PX = 56;
const terminalRepositoryStates: RepositoryStatus[] = ["ready", "failed"];
const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL;

function getStatusTone(status: RepositoryStatus) {
  if (status === "ready") {
    return "border-[#1f7a3b] bg-[#0b2c18] text-[#86efac]";
  }

  if (status === "failed") {
    return "border-[#7a2636] bg-[#2a1016] text-[#ffb6c0]";
  }

  return "border-[#127d8a] bg-[#082e35] text-[#63e7ff]";
}

export default function RepositoryPage() {
  const params = useParams<{ id: string }>();
  const repoId = params.id;
  const queryClient = useQueryClient();
  const [localSessionId, setLocalSessionId] = useState<string | null>(null);
  const [localSessionTitle, setLocalSessionTitle] = useState<string | null>(
    null,
  );
  const [message, setMessage] = useState("");
  const [localMessages, setLocalMessages] = useState<ChatMessage[] | null>(
    null,
  );
  const [isStreamingMessage, setIsStreamingMessage] = useState(false);
  const [historyPanelOpen, setHistoryPanelOpen] = useState(false);
  const [loadingSessionId, setLoadingSessionId] = useState<string | null>(null);
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null);
  const [deleteMode, setDeleteMode] = useState(false);
  const [selectedMessageIds, setSelectedMessageIds] = useState<string[]>([]);
  const repositoryQuery = useQuery({
    queryKey: queryKeys.repositories.workspace(repoId),
    queryFn: () => getRepositoryWorkspace(repoId),
  });
  const sessionsQuery = useQuery({
    queryKey: queryKeys.chat.sessions,
    queryFn: getChatSessions,
    enabled: historyPanelOpen,
  });
  const modelsQuery = useQuery({
    queryKey: queryKeys.chat.models,
    queryFn: getChatModels,
    staleTime: 1000 * 60 * 10,
  });

  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const lastMessageRef = useRef<HTMLDivElement>(null);
  const shouldAutoScrollRef = useRef(true);

  const repo = repositoryQuery.data?.repo ?? null;
  const tree = repositoryQuery.data?.tree ?? [];
  const sessionId =
    localSessionId ?? repositoryQuery.data?.chat.session_id ?? null;
  const activeSessionQuery = useQuery({
    queryKey: sessionId
      ? queryKeys.chat.detail(sessionId)
      : queryKeys.chat.detail(""),
    queryFn: () => getChatSession(sessionId as string),
    enabled: Boolean(sessionId),
  });
  const sessionTitle =
    localSessionTitle ??
    activeSessionQuery.data?.title ??
    repositoryQuery.data?.chat.session_title ??
    null;
  const messages = useMemo(
    () =>
      localMessages ??
      activeSessionQuery.data?.messages ??
      repositoryQuery.data?.chat.messages ??
      EMPTY_MESSAGES,
    [
      activeSessionQuery.data?.messages,
      localMessages,
      repositoryQuery.data?.chat.messages,
    ],
  );
  const availableMessageIds = useMemo(
    () =>
      new Set(
        messages
          .map((item) => getChatMessageId(item))
          .filter((messageId): messageId is string => Boolean(messageId)),
      ),
    [messages],
  );
  const selectedDeletableMessageIds = useMemo(
    () => selectedMessageIds.filter((messageId) => availableMessageIds.has(messageId)),
    [availableMessageIds, selectedMessageIds],
  );
  const chatModels = modelsQuery.data?.models ?? EMPTY_MODELS;
  const defaultModelId = modelsQuery.data?.default_model ?? null;
  const effectiveSelectedModelId =
    selectedModelId ?? defaultModelId ?? chatModels[0]?.id ?? null;
  const repositorySessionHistory = useMemo(() => {
    const activeRepositoryId = repo?.id ?? repoId;

    return (sessionsQuery.data ?? [])
      .filter((item) => item.repository_id === activeRepositoryId)
      .sort(
        (first, second) =>
          new Date(second.created_at).getTime() -
          new Date(first.created_at).getTime(),
      );
  }, [repo?.id, repoId, sessionsQuery.data]);
  const displayTitle = sessionTitle || "New Chat";
  const chatReady = repo?.status === "ready";
  const progress = Math.max(0, Math.min(100, repo?.progress ?? 0));
  const error = repositoryQuery.isError
    ? "Unable to load this repository."
    : "";

  useEffect(() => {
    const container = messagesContainerRef.current;

    if (!container) {
      return;
    }

    const updateAutoScrollPreference = () => {
      const distanceFromBottom =
        container.scrollHeight - container.scrollTop - container.clientHeight;

      shouldAutoScrollRef.current =
        distanceFromBottom < CHAT_BOTTOM_THRESHOLD_PX;
    };

    const pauseAutoScrollOnUserScroll = (event: WheelEvent) => {
      if (event.deltaY < 0) {
        shouldAutoScrollRef.current = false;
      }
    };

    const pauseAutoScrollOnTouch = () => {
      shouldAutoScrollRef.current = false;
    };

    const pauseAutoScrollOnKeyboard = (event: KeyboardEvent) => {
      if (
        event.key === "ArrowUp" ||
        event.key === "PageUp" ||
        event.key === "Home"
      ) {
        shouldAutoScrollRef.current = false;
      }
    };

    updateAutoScrollPreference();
    container.addEventListener("scroll", updateAutoScrollPreference, {
      passive: true,
    });
    container.addEventListener("wheel", pauseAutoScrollOnUserScroll, {
      passive: true,
    });
    container.addEventListener("touchstart", pauseAutoScrollOnTouch, {
      passive: true,
    });
    container.addEventListener("keydown", pauseAutoScrollOnKeyboard);

    return () => {
      container.removeEventListener("scroll", updateAutoScrollPreference);
      container.removeEventListener("wheel", pauseAutoScrollOnUserScroll);
      container.removeEventListener("touchstart", pauseAutoScrollOnTouch);
      container.removeEventListener("keydown", pauseAutoScrollOnKeyboard);
    };
  }, []);

  useEffect(() => {
    if (!shouldAutoScrollRef.current) {
      return;
    }

    window.requestAnimationFrame(() => {
      const container = messagesContainerRef.current;

      if (!container || !shouldAutoScrollRef.current) {
        return;
      }

      container.scrollTo({
        top: container.scrollHeight,
        behavior: "auto",
      });
    });
  }, [messages]);

  useEffect(() => {
    if (!backendUrl) {
      return;
    }

    const eventSource = new EventSource(
      `${backendUrl}/repos/${repoId}/status/stream`,
      {
        withCredentials: true,
      },
    );

    eventSource.onmessage = (event) => {
      const payload = JSON.parse(event.data);

      if (!payload.repo) {
        return;
      }

      queryClient.setQueryData(
        queryKeys.repositories.workspace(repoId),
        (
          current:
            | Awaited<ReturnType<typeof getRepositoryWorkspace>>
            | undefined,
        ) =>
          current
            ? {
                ...current,
                repo: {
                  ...current.repo,
                  ...payload.repo,
                },
              }
            : current,
      );

      queryClient.setQueryData(
        queryKeys.repositories.all,
        (current: unknown) =>
          Array.isArray(current)
            ? current.map((item) =>
                item?.id === payload.repo.id
                  ? {
                      ...item,
                      ...payload.repo,
                    }
                  : item,
              )
            : current,
      );

      if (
        payload.type === "done" ||
        terminalRepositoryStates.includes(payload.repo.status)
      ) {
        eventSource.close();
        queryClient.invalidateQueries({
          queryKey: queryKeys.repositories.workspace(repoId),
        });
      }
    };

    eventSource.onerror = () => {
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [queryClient, repoId]);

  const newSessionMutation = useMutation({
    mutationFn: createChatSession,
    onSuccess: (data) => {
      setLocalSessionId(data.id);
      setLocalSessionTitle(null);
      setLocalMessages([]);
      queryClient.setQueryData(
        queryKeys.repositories.workspace(repoId),
        (
          current:
            | Awaited<ReturnType<typeof getRepositoryWorkspace>>
            | undefined,
        ) =>
          current
            ? {
                ...current,
                chat: {
                  session_id: data.id,
                  session_title: null,
                  messages: [],
                },
              }
            : current,
      );
      queryClient.invalidateQueries({ queryKey: queryKeys.chat.sessions });
    },
  });

  const loadSessionMutation = useMutation({
    mutationFn: (selectedSession: ChatSessionSummary) =>
      getChatSession(selectedSession.id),
    onMutate: (selectedSession) => {
      setLoadingSessionId(selectedSession.id);
    },
    onSuccess: (data, selectedSession) => {
      const nextMessages = Array.isArray(data.messages) ? data.messages : [];
      const nextSessionId = data.id ?? selectedSession.id;
      const nextSessionTitle =
        data.title?.trim() || selectedSession.title?.trim() || null;

      setLocalSessionId(nextSessionId);
      setLocalSessionTitle(nextSessionTitle);
      setLocalMessages(nextMessages);
      setDeleteMode(false);
      setSelectedMessageIds([]);
      setHistoryPanelOpen(false);
      queryClient.setQueryData(
        queryKeys.repositories.workspace(repoId),
        (
          current:
            | Awaited<ReturnType<typeof getRepositoryWorkspace>>
            | undefined,
        ) =>
          current
            ? {
                ...current,
                chat: {
                  session_id: nextSessionId,
                  session_title: nextSessionTitle,
                  messages: nextMessages,
                },
              }
            : current,
      );
    },
    onSettled: () => {
      setLoadingSessionId(null);
    },
  });

  const deleteMessagesMutation = useMutation({
    mutationFn: deleteChatMessages,
    onSuccess: (_, deletedMessageIds) => {
      const deletedMessageIdSet = new Set(deletedMessageIds);

      setLocalMessages((current) => {
        const currentMessages = current ?? messages;

        return currentMessages.filter(
          (item) => {
            const messageId = getChatMessageId(item);

            return !messageId || !deletedMessageIdSet.has(messageId);
          },
        );
      });
      setSelectedMessageIds([]);
      setDeleteMode(false);
      queryClient.setQueryData(
        queryKeys.repositories.workspace(repoId),
        (
          current:
            | Awaited<ReturnType<typeof getRepositoryWorkspace>>
            | undefined,
        ) =>
          current
            ? {
                ...current,
                chat: {
                  ...current.chat,
                  messages: current.chat.messages.filter(
                    (item) => {
                      const messageId = getChatMessageId(item);

                      return !messageId || !deletedMessageIdSet.has(messageId);
                    },
                  ),
                },
              }
            : current,
      );
      queryClient.invalidateQueries({ queryKey: queryKeys.chat.sessions });
    },
  });

  async function handleSendMessage(e: React.SubmitEvent<HTMLFormElement>) {
    e.preventDefault();

    if (!chatReady || !message.trim() || !sessionId || isStreamingMessage) {
      return;
    }

    const question = message.trim();
    const userMessage: ChatMessage = { role: "user", content: question };
    const assistantMessage: ChatMessage = { role: "assistant", content: "" };
    const nextMessages = [...messages, userMessage, assistantMessage];

    shouldAutoScrollRef.current = true;
    setLocalMessages(nextMessages);
    queryClient.setQueryData(
      queryKeys.repositories.workspace(repoId),
      (
        current: Awaited<ReturnType<typeof getRepositoryWorkspace>> | undefined,
      ) =>
        current
          ? {
              ...current,
              chat: {
                ...current.chat,
                messages: [
                  ...current.chat.messages,
                  userMessage,
                  assistantMessage,
                ],
              },
            }
          : current,
    );
    setMessage("");
    setIsStreamingMessage(true);

    let streamedContent = "";
    let displayedContent = "";
    let typingIntervalId: number | null = null;
    let resolveTypingDrain: (() => void) | null = null;

    const updateAssistantMessage = (content: string) => {
      setLocalMessages((current) => {
        const currentMessages = current ?? nextMessages;
        const updatedMessages = [...currentMessages];
        const assistantIndex = updatedMessages.length - 1;

        updatedMessages[assistantIndex] = {
          role: "assistant",
          content,
        };

        return updatedMessages;
      });

      queryClient.setQueryData(
        queryKeys.repositories.workspace(repoId),
        (
          current:
            | Awaited<ReturnType<typeof getRepositoryWorkspace>>
            | undefined,
        ) => {
          if (!current) {
            return current;
          }

          const updatedMessages = [...current.chat.messages];
          const assistantIndex = updatedMessages.length - 1;

          updatedMessages[assistantIndex] = {
            role: "assistant",
            content,
          };

          return {
            ...current,
            chat: {
              ...current.chat,
              messages: updatedMessages,
            },
          };
        },
      );
    };

    const stopTypingInterval = () => {
      if (typingIntervalId) {
        window.clearInterval(typingIntervalId);
        typingIntervalId = null;
      }
    };

    const resolveDrainIfReady = () => {
      if (displayedContent.length < streamedContent.length) {
        return;
      }

      stopTypingInterval();
      resolveTypingDrain?.();
      resolveTypingDrain = null;
    };

    const startTypingInterval = () => {
      if (typingIntervalId) {
        return;
      }

      typingIntervalId = window.setInterval(() => {
        const remainingChars = streamedContent.length - displayedContent.length;

        if (remainingChars <= 0) {
          resolveDrainIfReady();
          return;
        }

        const charsToReveal = Math.min(
          MAX_TYPING_CHARS,
          Math.max(MIN_TYPING_CHARS, Math.ceil(remainingChars / 36)),
        );

        displayedContent = streamedContent.slice(
          0,
          displayedContent.length + charsToReveal,
        );
        updateAssistantMessage(displayedContent);
        resolveDrainIfReady();
      }, TYPING_INTERVAL_MS);
    };

    const waitForTypingDrain = () =>
      new Promise<void>((resolve) => {
        if (displayedContent.length >= streamedContent.length) {
          resolve();
          return;
        }

        resolveTypingDrain = resolve;
        startTypingInterval();
      });

    try {
      await streamChatMessage(
        sessionId,
        question,
        effectiveSelectedModelId,
        (event) => {
          if (event.type !== "delta") {
            return;
          }

          streamedContent += event.text ?? "";
          startTypingInterval();
        },
      );

      await waitForTypingDrain();

      const updatedSession = await getChatSession(sessionId);
      const nextSessionTitle = updatedSession.title?.trim() || null;
      const persistedMessages = Array.isArray(updatedSession.messages)
        ? updatedSession.messages
        : null;

      if (nextSessionTitle) {
        setLocalSessionTitle(nextSessionTitle);
      }

      if (persistedMessages) {
        setLocalMessages(persistedMessages);
      }

      queryClient.setQueryData(
        queryKeys.repositories.workspace(repoId),
        (
          current:
            | Awaited<ReturnType<typeof getRepositoryWorkspace>>
            | undefined,
        ) =>
          current
            ? {
                ...current,
                chat: {
                  ...current.chat,
                  session_title:
                    nextSessionTitle ?? current.chat.session_title ?? null,
                  messages: persistedMessages ?? current.chat.messages,
                },
              }
            : current,
      );
      queryClient.invalidateQueries({ queryKey: queryKeys.chat.sessions });
    } catch {
      const errorMessage =
        streamedContent ||
        "I couldn't stream the response. Please try sending the message again.";

      streamedContent = errorMessage;
      await waitForTypingDrain();
    } finally {
      stopTypingInterval();
      setIsStreamingMessage(false);
    }
  }

  async function handleNewSesion() {
    if (!repo) return;
    setDeleteMode(false);
    setSelectedMessageIds([]);
    newSessionMutation.mutate(repo.id);
  }

  function handleLoadSession(selectedSession: ChatSessionSummary) {
    setDeleteMode(false);
    setSelectedMessageIds([]);

    if (selectedSession.id === sessionId) {
      setLocalSessionTitle(selectedSession.title?.trim() || null);
      setHistoryPanelOpen(false);
      return;
    }

    setLocalSessionId(selectedSession.id);
    setLocalSessionTitle(selectedSession.title?.trim() || null);
    loadSessionMutation.mutate(selectedSession);
  }

  function handleToggleDeleteMode() {
    setDeleteMode((current) => {
      const nextDeleteMode = !current;

      if (!nextDeleteMode) {
        setSelectedMessageIds([]);
      }

      return nextDeleteMode;
    });
  }

  function handleToggleMessageSelection(messageId: string) {
    setSelectedMessageIds((current) =>
      current.includes(messageId)
        ? current.filter((item) => item !== messageId)
        : [...current, messageId],
    );
  }

  function handleDeleteSelectedMessages() {
    if (!selectedDeletableMessageIds.length || deleteMessagesMutation.isPending) {
      return;
    }

    deleteMessagesMutation.mutate(selectedDeletableMessageIds);
  }

  return (
    <div className="h-screen">
      <MobileHint />
      <section className="grid h-full bg-[#050506] lg:grid-cols-[minmax(280px,0.32fr)_1fr]">
        <aside className="flex flex-col min-h-[360px] border-b border-[#32313f] bg-[#111115] lg:border-b-0 lg:border-r">
          {/* Repository info */}
          <div className="border-b border-[#32313f] p-5">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#8f8b9c]">
              Repository
            </p>
            <h1 className="mt-2 break-words font-display text-2xl font-bold text-white">
              {repo?.full_name ?? "Loading..."}
            </h1>
            {repo?.branch ? (
              <p className="mt-2 flex items-center gap-2 font-mono text-sm text-[#c9c5d8]">
                <GitBranch className="h-4 w-4" />
                {repo.branch}
              </p>
            ) : null}

            {repo ? (
              <div className="mt-4">
                <span
                  className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm font-semibold capitalize ${getStatusTone(repo.status)}`}
                >
                  {repo.status === "ready" ? (
                    <CheckCircle2 className="h-4 w-4" />
                  ) : repo.status === "failed" ? (
                    <AlertTriangle className="h-4 w-4" />
                  ) : (
                    <Clock3 className="h-4 w-4" />
                  )}
                  {getStatusLabel(repo.status)}
                </span>
                {repo.status !== "ready" && repo.status !== "failed" ? (
                  <div className="mt-4">
                    <div className="h-2 overflow-hidden rounded bg-[#252334]">
                      <div
                        className="h-full bg-[#63e7ff] transition-all"
                        style={{ width: `${progress}%` }}
                      />
                    </div>
                    <p className="mt-2 font-mono text-xs text-[#aaa7b8]">
                      {progress}% indexed
                    </p>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          {/* File tree */}
          <div className="overflow-auto p-4">
            <p className="mb-3 text-xs font-bold uppercase tracking-[0.18em] text-[#8f8b9c]">
              Files
            </p>
            {repositoryQuery.isLoading ? (
              <div className="flex items-center gap-2 text-[#c9c5d8]">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading tree...
              </div>
            ) : error ? (
              <p className="rounded-md border border-[#6e2635] bg-[#220b12] px-3 py-2 text-sm text-[#ffb7c4]">
                {error}
              </p>
            ) : tree.length ? (
              <FileTree nodes={tree} repo={repo} />
            ) : (
              <p className="text-sm text-[#aaa7b8]">
                File tree will appear once repository cloning starts.
              </p>
            )}
          </div>
        </aside>

        {/* Chat Panel */}
        <ChatPanel
          repoId={repoId}
          title={displayTitle}
          messages={messages}
          chatReady={chatReady}
          message={message}
          messagesContainerRef={messagesContainerRef}
          lastMessageRef={lastMessageRef}
          onMessageChange={setMessage}
          onSendMessage={handleSendMessage}
          onNewChat={handleNewSesion}
          onOpenHistory={() => setHistoryPanelOpen(true)}
          deleteMode={deleteMode}
          selectedMessageIds={selectedDeletableMessageIds}
          onToggleDeleteMode={handleToggleDeleteMode}
          onToggleMessageSelection={handleToggleMessageSelection}
          onDeleteSelectedMessages={handleDeleteSelectedMessages}
          isDeletingMessages={deleteMessagesMutation.isPending}
          isSending={isStreamingMessage}
          models={chatModels}
          defaultModelId={defaultModelId}
          selectedModelId={effectiveSelectedModelId}
          modelsLoading={modelsQuery.isLoading}
          modelsError={modelsQuery.isError}
          onModelChange={setSelectedModelId}
        />
      </section>

      <ChatHistoryPanel
        open={historyPanelOpen}
        onOpenChange={setHistoryPanelOpen}
        sessions={repositorySessionHistory}
        activeSessionId={sessionId}
        loadingSessionId={loadingSessionId}
        isLoading={sessionsQuery.isLoading}
        isError={sessionsQuery.isError}
        isPending={loadSessionMutation.isPending}
        onSelectSession={handleLoadSession}
      />
    </div>
  );
}
