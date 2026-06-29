"use client";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { ChatSessionSummary } from "@/lib/repository-api";
import { Loader2 } from "lucide-react";

interface ChatHistoryPanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;

  sessions: ChatSessionSummary[];
  activeSessionId: string | null;

  loadingSessionId: string | null;
  isLoading: boolean;
  isError: boolean;
  isPending: boolean;

  onSelectSession: (session: ChatSessionSummary) => void;
}

function formatSessionDate(value: string) {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function ChatHistoryPanel({
  open,
  onOpenChange,
  sessions,
  activeSessionId,
  loadingSessionId,
  isLoading,
  isError,
  isPending,
  onSelectSession,
}: ChatHistoryPanelProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-[min(92vw,420px)] border-[#32313f] bg-[#111115] p-0 text-[#f4f0ff] sm:max-w-[420px]"
      >
        <SheetHeader className="border-b border-[#32313f] px-5 py-4">
          <SheetTitle className="font-display text-lg font-bold text-white">
            Chat History
          </SheetTitle>

          <SheetDescription className="text-sm text-[#aaa7b8]">
            {sessions.length
              ? `${sessions.length} sessions for this repository`
              : "Saved sessions for this repository will appear here."}
          </SheetDescription>
        </SheetHeader>

        <div className="min-h-0 flex-1 overflow-auto px-3 pb-4">
          {isLoading ? (
            <div className="flex items-center gap-2 px-2 py-5 text-sm text-[#c9c5d8]">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading chat history...
            </div>
          ) : isError ? (
            <p className="mx-2 mt-4 rounded-md border border-[#6e2635] bg-[#220b12] px-3 py-2 text-sm text-[#ffb7c4]">
              Unable to load chat history.
            </p>
          ) : sessions.length ? (
            <div className="space-y-2 pt-3">
              {sessions.map((session) => {
                const isActive = session.id === activeSessionId;
                const isLoadingSession =
                  loadingSessionId === session.id;

                return (
                  <button
                    key={session.id}
                    type="button"
                    disabled={isPending}
                    onClick={() => onSelectSession(session)}
                    className={`w-full rounded-md border px-3 py-3 text-left transition hover:border-[#5e5a7c] hover:bg-[#1a1a24] ${
                      isActive
                        ? "border-[#bbb7ff] bg-[#202033]"
                        : "border-[#32313f] bg-[#151419]"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <p className="min-w-0 flex-1 truncate font-medium text-white">
                        {session.title?.trim() || "New Chat"}
                      </p>

                      {isLoadingSession && (
                        <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-[#bbb7ff]" />
                      )}
                    </div>

                    <p className="mt-1 text-xs text-[#aaa7b8]">
                      {formatSessionDate(session.created_at)}
                    </p>
                  </button>
                );
              })}
            </div>
          ) : (
            <p className="px-2 py-5 text-sm text-[#aaa7b8]">
              No previous chat sessions found for this repository.
            </p>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}