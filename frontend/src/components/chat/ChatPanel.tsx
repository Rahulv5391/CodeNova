"use client";

import { Button } from "@/components/ui/button";
import {
  ChatCommand,
  ChatModel,
  ChatMessage,
  getChatCommands,
  getChatMessageId,
} from "@/lib/repository-api";
import { queryKeys } from "@/lib/query-keys";
import { MessageBlock } from "@/types/chat";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  Bot,
  Check,
  CheckCircle2,
  ChevronDown,
  Clock3,
  HelpCircle,
  History,
  Send,
  Trash2,
  UserRound,
} from "lucide-react";
import { useRouter } from "next/navigation";
import {
  Fragment,
  type ReactNode,
  RefObject,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

interface ChatPanelProps {
  repoId: string;
  title: string;

  messages: ChatMessage[];
  chatReady: boolean;
  message: string;

  messagesContainerRef: RefObject<HTMLDivElement | null>;
  lastMessageRef: RefObject<HTMLDivElement | null>;

  onMessageChange: (value: string) => void;
  onSendMessage: (e: React.SubmitEvent<HTMLFormElement>) => void;

  onNewChat: () => void;
  onOpenHistory: () => void;
  deleteMode: boolean;
  selectedMessageIds: string[];
  onToggleDeleteMode: () => void;
  onToggleMessageSelection: (messageId: string) => void;
  onDeleteSelectedMessages: () => void;
  isDeletingMessages: boolean;
  isSending: boolean;
  models: ChatModel[];
  defaultModelId: string | null;
  selectedModelId: string | null;
  modelsLoading: boolean;
  modelsError: boolean;
  onModelChange: (modelId: string) => void;
}

const EMPTY_COMMANDS: ChatCommand[] = [];

function parseMessageContent(content: string): MessageBlock[] {
  const blocks: MessageBlock[] = [];
  const fenceRegex = /```([a-zA-Z0-9_-]+)?\s*([\s\S]*?)```/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  function pushTextBlocks(text: string) {
    const normalized = text
      .replace(/\r\n/g, "\n")
      .replace(/[ \t]+$/gm, "")
      .replace(/([^\n])(\s+)(#{1,3}\s+)/g, "$1\n$3")
      .replace(/([^\n])(\s+)(\d+\.\s+\*\*)/g, "$1\n$3")
      .replace(/([^\n])(\s+)([-*]\s+\*\*)/g, "$1\n$3")
      .trim();

    if (!normalized) return;

    const lines = normalized.split("\n");
    let paragraph: string[] = [];
    let listItems: string[] = [];
    let orderedList: boolean | null = null;

    function flushParagraph() {
      if (!paragraph.length) return;
      blocks.push({ type: "paragraph", text: paragraph.join(" ").trim() });
      paragraph = [];
    }

    function flushList() {
      if (!listItems.length || orderedList === null) return;
      blocks.push({ type: "list", ordered: orderedList, items: listItems });
      listItems = [];
      orderedList = null;
    }

    for (const line of lines) {
      const trimmed = line.trim();

      if (!trimmed) {
        flushParagraph();
        flushList();
        continue;
      }

      const headingMatch = trimmed.match(/^(#{1,3})\s+(.+)$/);
      if (headingMatch) {
        flushParagraph();
        flushList();
        blocks.push({
          type: "heading",
          level: headingMatch[1].length,
          text: headingMatch[2],
        });
        continue;
      }

      const orderedMatch = trimmed.match(/^\d+\.\s+(.+)$/);
      const bulletMatch = trimmed.match(/^[-*]\s+(.+)$/);

      if (orderedMatch || bulletMatch) {
        const isOrdered = Boolean(orderedMatch);
        flushParagraph();

        if (orderedList !== null && orderedList !== isOrdered) {
          flushList();
        }

        orderedList = isOrdered;
        listItems.push((orderedMatch?.[1] ?? bulletMatch?.[1] ?? "").trim());
        continue;
      }

      if (listItems.length) {
        listItems[listItems.length - 1] =
          `${listItems[listItems.length - 1]} ${trimmed}`;
      } else {
        paragraph.push(trimmed);
      }
    }

    flushParagraph();
    flushList();
  }

  while ((match = fenceRegex.exec(content)) !== null) {
    pushTextBlocks(content.slice(lastIndex, match.index));
    blocks.push({
      type: "code",
      language: match[1],
      code: match[2].trim(),
    });
    lastIndex = fenceRegex.lastIndex;
  }

  pushTextBlocks(content.slice(lastIndex));

  return blocks.length ? blocks : [{ type: "paragraph", text: content }];
}

function renderInlineMarkdown(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
  const tokenRegex =
    /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\((https?:\/\/[^)\s]+)\))/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = tokenRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }

    const token = match[0];

    if (token.startsWith("**")) {
      parts.push(
        <strong key={match.index} className="font-semibold text-[#f4f0ff]">
          {token.slice(2, -2)}
        </strong>,
      );
    } else if (token.startsWith("`")) {
      parts.push(
        <code
          key={match.index}
          className="rounded border border-[#3c394d] bg-[#0b0b11] px-1.5 py-0.5 font-mono text-[0.9em] text-[#b8f7ff]"
        >
          {token.slice(1, -1)}
        </code>,
      );
    } else {
      const linkMatch = token.match(/^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/);
      parts.push(
        <a
          key={match.index}
          href={linkMatch?.[2] ?? "#"}
          target="_blank"
          className="font-medium text-[#9adfff] underline decoration-[#4ea3b7] underline-offset-4 hover:text-white"
        >
          {linkMatch?.[1] ?? token}
        </a>,
      );
    }

    lastIndex = tokenRegex.lastIndex;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts;
}

function FormattedMessage({ content }: { content: string }) {
  const blocks = useMemo(() => parseMessageContent(content), [content]);

  return (
    <div className="space-y-4">
      {blocks.map((block, index) => {
        if (block.type === "heading") {
          const Heading = block.level === 1 ? "h3" : "h4";

          return (
            <Heading
              key={index}
              className="text-base font-bold leading-6 text-white"
            >
              {renderInlineMarkdown(block.text)}
            </Heading>
          );
        }

        if (block.type === "list") {
          const ListTag = block.ordered ? "ol" : "ul";

          return (
            <ListTag
              key={index}
              className={`space-y-3 pl-5 ${
                block.ordered ? "list-decimal" : "list-disc"
              }`}
            >
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex} className="pl-1 leading-7">
                  {renderInlineMarkdown(item)}
                </li>
              ))}
            </ListTag>
          );
        }

        if (block.type === "code") {
          return (
            <div
              key={index}
              className="overflow-hidden rounded-md border border-[#343244] bg-[#09090d]"
            >
              {block.language ? (
                <div className="border-b border-[#343244] px-3 py-2 font-mono text-xs uppercase tracking-[0.16em] text-[#8f8b9c]">
                  {block.language}
                </div>
              ) : null}
              <pre className="overflow-x-auto p-4 text-sm leading-6">
                <code className="font-mono text-[#d8f8ff]">{block.code}</code>
              </pre>
            </div>
          );
        }

        return (
          <p key={index} className="leading-7">
            {renderInlineMarkdown(block.text).map((part, partIndex) => (
              <Fragment key={partIndex}>{part}</Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex gap-4 ${isUser ? "justify-end" : "justify-start"} `}>
      {!isUser ? (
        <div className="mt-1 grid h-9 w-9 shrink-0 place-items-center rounded-md border border-[#3d395d] bg-[#151525] text-[#bbb7ff]">
          <Bot className="h-5 w-5" />
        </div>
      ) : null}
      <div
        className={`max-w-[min(820px,88%)] rounded-md border px-3 py-1 text-base shadow-[0_18px_45px_rgba(0,0,0,0.24)] ${
          isUser
            ? "border-[#4b4960] bg-[#24242c] text-white"
            : "border-[#3d395d] bg-[#151525] text-[#d8d4e6]"
        }`}
      >
        <FormattedMessage content={message.content} />
      </div>
      {isUser && (
        <div className=" grid h-9 w-9 shrink-0 place-items-center rounded-md border border-[#4b4960] bg-[#24242c] text-white">
          <UserRound className="h-5 w-5" />
        </div>
      )}
    </div>
  );
}

function SessionTitle({ title }: { title: string }) {
  const [displayedTitle, setDisplayedTitle] = useState(title);
  const previousTitleRef = useRef(title);

  useEffect(() => {
    const previousTitle = previousTitleRef.current;

    if (title === previousTitle) {
      return;
    }

    previousTitleRef.current = title;

    if (previousTitle !== "New Chat" || title === "New Chat") {
      setDisplayedTitle(title);
      return;
    }

    setDisplayedTitle("");

    let index = 0;
    const intervalId = window.setInterval(() => {
      index += 1;
      setDisplayedTitle(title.slice(0, index));

      if (index >= title.length) {
        window.clearInterval(intervalId);
      }
    }, 34);

    return () => window.clearInterval(intervalId);
  }, [title]);

  return (
    <h3 className="min-h-7 max-w-[min(52vw,620px)] truncate font-display text-lg font-bold text-white transition-opacity duration-200">
      {displayedTitle || "\u00a0"}
    </h3>
  );
}

function CommandList({
  commands,
  emptyMessage,
  onSelectCommand,
}: {
  commands: ChatCommand[];
  emptyMessage: string;
  onSelectCommand?: (command: ChatCommand) => void;
}) {
  if (!commands.length) {
    return <p className="px-3 py-2 text-sm text-[#aaa7b8]">{emptyMessage}</p>;
  }

  return (
    <div className="max-h-[300px] overflow-auto py-1">
      {commands.map((command) => {
        const content = (
          <>
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="font-mono text-xs text-[#9adfff]">
                  {command.command}
                </p>
                <p className="mt-2 text-sm leading-5 text-[#c9c5d8]">
                  {command.description}
                </p>
              </div>
              {command.requires_query ? (
                <span className="shrink-0 rounded border border-[#514d69] px-2 py-0.5 text-[11px] font-medium text-[#c9c5d8]">
                  query
                </span>
              ) : null}
            </div>

            <p className="mt-2 font-mono text-xs text-[#aaa7b8]">
              {command.usage}
            </p>
          </>
        );

        if (!onSelectCommand) {
          return (
            <div
              key={command.name}
              className="border-b border-[#242331] px-3 py-3 last:border-b-0"
            >
              {content}
            </div>
          );
        }

        return (
          <button
            key={command.name}
            type="button"
            className="w-full border-b border-[#242331] px-3 py-3 text-left transition hover:bg-[#171720] focus:bg-[#171720] focus:outline-none last:border-b-0"
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => onSelectCommand(command)}
          >
            {content}
          </button>
        );
      })}
    </div>
  );
}

function ModelList({
  models,
  selectedModelId,
  defaultModelId,
  emptyMessage,
  onSelectModel,
}: {
  models: ChatModel[];
  selectedModelId: string | null;
  defaultModelId: string | null;
  emptyMessage: string;
  onSelectModel: (model: ChatModel) => void;
}) {
  if (!models.length) {
    return <p className="px-3 py-2 text-sm text-[#aaa7b8]">{emptyMessage}</p>;
  }

  return (
    <div className="max-h-[280px] overflow-auto py-1">
      {models.map((model) => {
        const selected = model.id === selectedModelId;

        return (
          <button
            key={model.id}
            type="button"
            className="flex w-full items-start gap-3 border-b border-[#242331] px-3 py-3 text-left transition hover:bg-[#171720] focus:bg-[#171720] focus:outline-none last:border-b-0"
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => onSelectModel(model)}
          >
            <span
              className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded border ${
                selected
                  ? "border-[#9adfff] bg-[#12343e] text-[#9adfff]"
                  : "border-[#4a465e] text-transparent"
              }`}
            >
              <Check className="h-3.5 w-3.5" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-2">
                <span className="truncate text-sm font-semibold text-white">
                  {model.label}
                </span>
                {model.id === defaultModelId ? (
                  <span className="shrink-0 rounded border border-[#514d69] px-2 py-0.5 text-[11px] font-medium text-[#c9c5d8]">
                    default
                  </span>
                ) : null}
              </span>
              <span className="mt-1 block truncate font-mono text-xs text-[#aaa7b8]">
                {model.id}
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

export function ChatPanel({
  repoId,
  title,
  messages,
  chatReady,
  message,
  messagesContainerRef,
  lastMessageRef,
  onMessageChange,
  onSendMessage,
  onNewChat,
  onOpenHistory,
  deleteMode,
  selectedMessageIds,
  onToggleDeleteMode,
  onToggleMessageSelection,
  onDeleteSelectedMessages,
  isDeletingMessages,
  isSending,
  models,
  defaultModelId,
  selectedModelId,
  modelsLoading,
  modelsError,
  onModelChange,
}: ChatPanelProps) {
  const router = useRouter();
  const [showCommandHelp, setShowCommandHelp] = useState(false);
  const [showModelPicker, setShowModelPicker] = useState(false);
  const [commandSuggestionsDismissed, setCommandSuggestionsDismissed] =
    useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const inputAreaRef = useRef<HTMLDivElement>(null);
  const commandQuery = useQuery({
    queryKey: queryKeys.chat.commands,
    queryFn: getChatCommands,
    staleTime: 1000 * 60 * 10,
  });
  const commands = commandQuery.data ?? EMPTY_COMMANDS;
  const trimmedMessage = message.trimStart();
  const slashCommandSearch = trimmedMessage.startsWith("/")
    ? trimmedMessage.slice(1).split(/\s/, 1)[0].toLowerCase()
    : "";
  const showSlashSuggestions =
    chatReady && trimmedMessage.startsWith("/") && !commandSuggestionsDismissed;
  const filteredCommands = useMemo(() => {
    if (!slashCommandSearch) {
      return commands;
    }

    return commands.filter((command) => {
      const commandName = command.command.slice(1).toLowerCase();

      return (
        commandName.startsWith(slashCommandSearch) ||
        command.title.toLowerCase().includes(slashCommandSearch)
      );
    });
  }, [commands, slashCommandSearch]);
  const displayedCommands = showSlashSuggestions ? filteredCommands : commands;
  const commandPopoverOpen =
    (showSlashSuggestions || showCommandHelp) && chatReady && !showModelPicker;
  const commandPopoverTitle = showSlashSuggestions
    ? "Slash Commands"
    : "Available Commands";
  const commandEmptyMessage = commandQuery.isLoading
    ? "Loading commands..."
    : commandQuery.isError
      ? "Unable to load commands."
      : "No commands match your search.";
  const selectedModel =
    models.find((model) => model.id === selectedModelId) ?? null;
  const selectedModelLabel = selectedModel?.label ?? "Model";
  const hasDeletableMessages = messages.some((item) => getChatMessageId(item));
  const modelEmptyMessage = modelsLoading
    ? "Loading models..."
    : modelsError
      ? "Unable to load models."
      : "No models are available.";

  function handleSelectCommand(command: ChatCommand) {
    onMessageChange(`${command.command} `);
    setShowCommandHelp(false);
    setCommandSuggestionsDismissed(false);
    inputRef.current?.focus();
  }

  function handleSelectModel(model: ChatModel) {
    onModelChange(model.id);
    setShowModelPicker(false);
    inputRef.current?.focus();
  }

  useEffect(() => {
    if (!commandPopoverOpen && !showModelPicker) {
      return;
    }

    function closePopoversOnOutsideClick(event: PointerEvent) {
      const target = event.target;

      if (target instanceof Node && inputAreaRef.current?.contains(target)) {
        return;
      }

      setShowCommandHelp(false);
      setShowModelPicker(false);

      if (trimmedMessage.startsWith("/")) {
        setCommandSuggestionsDismissed(true);
      }
    }

    document.addEventListener("pointerdown", closePopoversOnOutsideClick);

    return () => {
      document.removeEventListener("pointerdown", closePopoversOnOutsideClick);
    };
  }, [commandPopoverOpen, showModelPicker, trimmedMessage]);

  return (
    <section className="min-w-0 flex min-h-[calc(100vh-80px)] flex-col bg-[#09090d]">
      {/* Header */}
      <div className="flex justify-between border-b border-[#32313f] px-5 py-3">
        <SessionTitle title={title} />

        <div className="flex items-center gap-4">
          {deleteMode ? (
            <>
              <span className="font-mono text-xs text-[#aaa7b8]">
                {selectedMessageIds.length} selected
              </span>
              <Button
                variant="destructive"
                onClick={onDeleteSelectedMessages}
                disabled={!selectedMessageIds.length || isDeletingMessages}
              >
                <Trash2 />
                Delete
              </Button>
            </>
          ) : null}

          <Button onClick={() => router.push(`/repo/${repoId}/pull_request`)}>
            Review Pull Requests
          </Button>

          <Button onClick={() => router.push(`/repo/${repoId}/docs`)}>
            Generate Docs
          </Button>

          <Button onClick={onNewChat}>New Chat</Button>

          <Button
            size="icon"
            variant={deleteMode ? "destructive" : "default"}
            aria-label="Select messages to delete"
            onClick={onToggleDeleteMode}
            disabled={isSending || isDeletingMessages || !hasDeletableMessages}
          >
            <Trash2 />
          </Button>

          <Button
            size="icon"
            aria-label="Open chat history"
            onClick={onOpenHistory}
            disabled={isDeletingMessages}
          >
            <History />
          </Button>

          <Button onClick={() => router.push("/dashboard")}>
            <ArrowLeft />
          </Button>
        </div>
      </div>

      {/* Messages */}
      <div
        ref={messagesContainerRef}
        className="flex-1 space-y-5 overflow-auto px-28 py-6"
      >
        {messages.length ? (
          messages.map((item, index) => {
            const messageId = getChatMessageId(item);
            const isSelected = messageId
              ? selectedMessageIds.includes(messageId)
              : false;

            return (
            <div
              key={messageId ?? `${item.role}-${index}`}
              ref={
                index ===
                (messages[messages.length - 1]?.role === "user"
                  ? messages.length - 1
                  : messages.length - 2)
                  ? lastMessageRef
                  : null
              }
              className="flex items-start gap-3"
            >
              {deleteMode ? (
                <button
                  type="button"
                  className={`mt-2 grid h-6 w-6 shrink-0 place-items-center rounded border ${
                    messageId
                      ? "cursor-pointer border-[#4a465e] bg-[#111116] text-[#9adfff]"
                      : "border-[#302f3b] bg-[#0d0d12] text-transparent opacity-40"
                  }`}
                  aria-label={
                    messageId
                      ? "Select message for deletion"
                      : "Message cannot be deleted yet"
                  }
                  aria-pressed={isSelected}
                  disabled={!messageId || isDeletingMessages}
                  onClick={() => {
                    if (messageId) {
                      onToggleMessageSelection(messageId);
                    }
                  }}
                >
                  {isSelected ? <Check className="h-4 w-4" /> : null}
                </button>
              ) : null}
              <div className="min-w-0 flex-1">
                <ChatBubble message={item} />
              </div>
            </div>
            );
          })
        ) : (
          <div className="flex h-full min-h-[320px] items-center justify-center text-center">
            <div>
              <div
                className={`mx-auto grid h-14 w-14 place-items-center rounded-full border ${
                  chatReady
                    ? "border-[#1f7a3b] bg-[#0b2c18] text-[#86efac]"
                    : "border-[#444254] bg-[#151419] text-[#8f8b9c]"
                }`}
              >
                {chatReady ? (
                  <CheckCircle2 className="h-7 w-7" />
                ) : (
                  <Clock3 className="h-7 w-7" />
                )}
              </div>

              <p className="mt-4 max-w-md text-lg text-[#c9c5d8]">
                {chatReady
                  ? "This repository is indexed and ready for questions."
                  : "Chat is locked while the repository is being indexed."}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <form className="px-28 py-3" onSubmit={onSendMessage}>
        <div ref={inputAreaRef} className="relative">
          <div
            className={`absolute bottom-full left-0 right-0 z-20 mb-2 overflow-hidden rounded-md border border-[#3b394c] bg-[#111116] shadow-[0_18px_48px_rgba(0,0,0,0.42)] transition-all duration-200 ease-out ${
              commandPopoverOpen
                ? "translate-y-0 opacity-100"
                : "pointer-events-none translate-y-2 opacity-0"
            }`}
          >
              <div className="flex items-center justify-between border-b border-[#282637] px-3 py-2">
                <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#8f8b9c]">
                  {commandPopoverTitle}
                </p>
                <p className="font-mono text-xs text-[#aaa7b8]">
                  {commands.length} available
                </p>
              </div>
              <CommandList
                commands={displayedCommands}
                emptyMessage={commandEmptyMessage}
                onSelectCommand={
                  showSlashSuggestions ? handleSelectCommand : undefined
                }
              />
            </div>

          <div
            className={`absolute bottom-full right-0 z-30 mb-2 w-[min(360px,100%)] overflow-hidden rounded-md border border-[#3b394c] bg-[#111116] shadow-[0_18px_48px_rgba(0,0,0,0.42)] transition-all duration-200 ease-out ${
              showModelPicker && chatReady
                ? "translate-y-0 opacity-100"
                : "pointer-events-none translate-y-2 opacity-0"
            }`}
          >
              <div className="flex items-center justify-between border-b border-[#282637] px-3 py-2">
                <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#8f8b9c]">
                  Model
                </p>
                {selectedModel ? (
                  <p className="max-w-[190px] truncate text-xs text-[#c9c5d8]">
                    {selectedModel.label}
                  </p>
                ) : null}
              </div>
              <ModelList
                models={models}
                selectedModelId={selectedModelId}
                defaultModelId={defaultModelId}
                emptyMessage={modelEmptyMessage}
                onSelectModel={handleSelectModel}
              />
            </div>

          <div
            className={`flex rounded-md border p-3 ${
              chatReady
                ? "border-[#444254] bg-[#0d0d12]"
                : "border-[#32313f] bg-[#111115] opacity-70"
            }`}
          >
            <input
              ref={inputRef}
              className="min-w-0 flex-1 bg-transparent text-md text-[#f4f0ff] outline-none placeholder:text-[#777381]"
              disabled={!chatReady || isSending}
              value={message}
              onPointerDown={() => {
                setShowCommandHelp(false);
                setShowModelPicker(false);

                if (trimmedMessage.startsWith("/")) {
                  setCommandSuggestionsDismissed(true);
                }
              }}
              onChange={(e) => {
                onMessageChange(e.target.value);
                if (e.target.value.trimStart().startsWith("/")) {
                  setShowCommandHelp(false);
                  setShowModelPicker(false);
                  setCommandSuggestionsDismissed(false);
                }
              }}
              placeholder={
                chatReady
                  ? "Ask anything about this repository, or type / for commands..."
                  : "Chat unlocks when repository status is ready"
              }
            />

            <button
              type="button"
              className="mr-2 flex h-8 max-w-[190px] ml-2 shrink-0 items-center gap-2 rounded-md border border-[#3e3b50] px-2 text-sm text-[#c9c5d8] transition hover:border-[#5b5770] hover:text-white disabled:opacity-50"
              aria-label="Select chat model"
              disabled={!chatReady || modelsLoading || modelsError}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => {
                setShowCommandHelp(false);
                setCommandSuggestionsDismissed(true);
                setShowModelPicker((current) => !current);
              }}
            >
              <span className="min-w-0 truncate">{selectedModelLabel}</span>
              <ChevronDown className="h-4 w-4 shrink-0" />
            </button>

            <button
              type="button"
              className="mr-2 grid h-8 w-8 shrink-0 place-items-center rounded-md border border-[#3e3b50] text-[#c9c5d8] transition hover:border-[#5b5770] hover:text-white disabled:opacity-50"
              aria-label="Show slash commands"
              disabled={!chatReady}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => {
                setShowModelPicker(false);
                setCommandSuggestionsDismissed(false);
                setShowCommandHelp((current) => !current);
              }}
            >
              <HelpCircle className="h-4 w-4" />
            </button>

            <button
              className="grid h-8 w-8 shrink-0 place-items-center rounded-md bg-[#bbb7ff] text-[#0b08a8] disabled:opacity-50"
              disabled={!chatReady || !message.trim() || isSending}
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      </form>
    </section>
  );
}
