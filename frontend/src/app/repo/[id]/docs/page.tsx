"use client";

import AppShell, { MobileHint } from "@/components/AppShell";
import { DocHistory } from "@/components/docs/DocHistory";
import { DocumentationViewer } from "@/components/docs/DocumentationViewer";
import { PillarCard } from "@/components/docs/PillarCard";
import { RepositorySummary } from "@/components/docs/RespositorySummary";
import {
  generateDocumentation,
  getDocDetail,
  getDocsHistory,
  getDocTopics,
} from "@/lib/docs-api";
import { queryKeys } from "@/lib/query-keys";
import { DocDetail, DocHistoryItem } from "@/types/doc";
import { Braces, FileCode2, Loader2, ScrollText, Sparkles } from "lucide-react";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { getPullRequestRepository } from "@/lib/pull-request-api";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

const EMPTY_PILLARS: Awaited<ReturnType<typeof getDocTopics>> = [];

export default function DocumentationPage() {
  const params = useParams<{ id: string }>();
  const repoId = params.id;
  const [selectedPillars, setSelectedPillars] = useState<string[]>([]);
  const [format, setFormat] = useState<"Markdown" | "JSON">("Markdown");
  const [context, setContext] = useState("");
  const [selectedDoc, setSelectedDoc] = useState<DocDetail | null>(null);
  const [docError, setDocError] = useState("");
  const [viewerOpen, setViewerOpen] = useState(false);
  const queryClient = useQueryClient();

  const repoQuery = useQuery({
    queryKey: queryKeys.repositories.detail(repoId),
    queryFn: () => getPullRequestRepository(repoId),
  });

  const historyQuery = useQuery({
    queryKey: queryKeys.docs.history(repoId),
    queryFn: () => getDocsHistory(repoId),
  });

  const topicsQuery = useQuery({
    queryKey: queryKeys.docs.topics,
    queryFn: getDocTopics,
  });

  const pillars = topicsQuery.data ?? EMPTY_PILLARS;
  const history = historyQuery.data ?? [];
  const selectedTitles = pillars
    .filter((pillar) => selectedPillars.includes(pillar.id))
    .map((pillar) => pillar.id);

  const generateMutation = useMutation({
    mutationFn: () =>
      generateDocumentation({
        repositoryId: repoId,
        topics: selectedTitles,
        userContext: context,
        format,
      }),
    onSuccess: (data) => {
      queryClient.setQueryData<DocHistoryItem[]>(
        queryKeys.docs.history(repoId),
        (current = []) => [
          {
            id: data.doc_id,
            topics: data.topics_requested,
            created_at: new Intl.DateTimeFormat("en-GB", {
              day: "2-digit",
              month: "short",
              year: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            }).format(data.created_at),
            format: data.format,
            status: data.status,
          },
          ...current,
        ],
      );
    },
  });

  const docDetailMutation = useMutation({
    mutationFn: getDocDetail,
    onMutate: () => {
      setViewerOpen(true);
      setSelectedDoc(null);
      setDocError("");
    },
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.docs.detail(data.id), data);
      setSelectedDoc(data);
    },
    onError: () => {
      setDocError("Unable to load this documentation.");
    },
  });

  const topicTitleMap = useMemo(
    () =>
      Object.fromEntries(
        pillars.map((pillar) => [pillar.id, pillar.title]),
      ) as Record<string, string>,
    [pillars],
  );

  function togglePillar(id: string) {
    setSelectedPillars((current) =>
      current.includes(id)
        ? current.filter((pillarId) => pillarId !== id)
        : [...current, id],
    );
  }

  function toggleAll() {
    setSelectedPillars((current) =>
      current.length === pillars.length
        ? []
        : pillars.map((pillar) => pillar.id),
    );
  }

  async function handleGenerate() {
    if (!selectedTitles.length || generateMutation.isPending) return;

    generateMutation.mutate();
  }

  async function handleViewDocument(docId: string) {
    const cachedDoc = queryClient.getQueryData<DocDetail>(
      queryKeys.docs.detail(docId),
    );

    if (cachedDoc) {
      setViewerOpen(true);
      setDocError("");
      setSelectedDoc(cachedDoc);
      return;
    }

    docDetailMutation.mutate(docId);
  }

  return (
    <AppShell active="Dashboard">
      <MobileHint />
      <section className="px-5 py-8 md:px-12 lg:px-14">
        <div className="mx-auto max-w-7xl">
          <RepositorySummary
            repo={repoQuery.data ?? null}
            isLoading={repoQuery.isLoading}
            error={
              repoQuery.isError ? "Unable to load this repository." : ""
            }
          />

          <div className="mt-9 flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
            <div>
              <h1 className="font-display text-3xl font-bold text-white">
                Knowledge Pillars
              </h1>
              <p className="mt-2 text-sm text-[#d8d4e6]">
                Select the architectural domains for CodeNova to synthesize.
              </p>
            </div>
            <button
              type="button"
              className="self-start rounded-md px-2 py-1 text-sm font-medium text-[#c5c1ff] transition hover:bg-[#1b1a20] hover:text-white sm:self-auto"
              onClick={toggleAll}
            >
              {selectedPillars.length === pillars.length
                ? "Clear All"
                : "Select All"}
            </button>
          </div>

          <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {pillars.map((pillar) => (
              <PillarCard
                key={pillar.id}
                pillar={pillar}
                selected={selectedPillars.includes(pillar.id)}
                onToggle={() => togglePillar(pillar.id)}
              />
            ))}
          </div>

          <div className="mt-9 grid gap-6 lg:grid-cols-[1fr_390px]">
            <AdditionalContext value={context} onChange={setContext} />
            <OutputConfiguration
              format={format}
              isGenerating={generateMutation.isPending}
              selectedCount={selectedPillars.length}
              onGenerate={handleGenerate}
              onFormatChange={setFormat}
            />
          </div>

          <DocHistory
            history={history}
            topictitleMap={topicTitleMap}
            onViewDocument={handleViewDocument}
          />
        </div>
      </section>
      <DocumentationViewer
        doc={selectedDoc}
        error={docError}
        isLoading={docDetailMutation.isPending}
        open={viewerOpen}
        onOpenChange={setViewerOpen}
      />
    </AppShell>
  );
}

function AdditionalContext({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <section className="rounded-md border border-[#32313f] bg-[#08080b] p-6">
      <div className="flex items-center justify-between gap-4">
        <h2 className="flex items-center gap-3 font-display text-lg font-bold text-white">
          <ScrollText className="h-5 w-5 text-[#c5c1ff]" />
          Additional Context
        </h2>
        <span className="font-mono text-sm text-[#d8d4e6]">
          {value.length} / 2000 chars
        </span>
      </div>
      <textarea
        className="mt-5 min-h-44 w-full resize-y rounded-md border border-[#444254] bg-[#0d0d12] p-4 text-sm leading-7 text-[#f4f0ff] outline-none transition placeholder:text-[#777381] focus:border-[#b8b2ff]"
        maxLength={2000}
        placeholder="e.g. Focus on the new auth middleware in /src. Explain the interaction between the edge workers and the main API."
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </section>
  );
}

function OutputConfiguration({
  format,
  isGenerating,
  selectedCount,
  onFormatChange,
  onGenerate,
}: {
  format: "Markdown" | "JSON";
  isGenerating: boolean;
  selectedCount: number;
  onFormatChange: (format: "Markdown" | "JSON") => void;
  onGenerate: () => void;
}) {
  return (
    <aside className="rounded-md border border-[#32313f] bg-[#08080b] p-6">
      <h2 className="font-display text-lg font-bold text-white">
        Output Configuration
      </h2>
      <p className="mt-6 text-xs font-bold uppercase tracking-[0.16em] text-[#aaa7b8]">
        Format
      </p>
      <div className="mt-3 grid grid-cols-2 rounded-md border border-[#444254] bg-[#0d0d12] p-1">
        {(["Markdown", "JSON"] as const).map((item) => (
          <button
            key={item}
            type="button"
            className={`flex h-10 items-center justify-center gap-2 rounded-sm text-sm transition ${
              format === item
                ? "bg-[#bbb7ff] font-semibold text-[#0b08a8]"
                : "text-[#d8d4e6] hover:bg-[#1b1a20] hover:text-white"
            }`}
            onClick={() => onFormatChange(item)}
          >
            {item === "Markdown" ? (
              <FileCode2 className="h-4 w-4" />
            ) : (
              <Braces className="h-4 w-4" />
            )}
            {item}
          </button>
        ))}
      </div>
      <div className="my-6 h-px bg-[#32313f]" />
      <button
        type="button"
        disabled={!selectedCount || isGenerating}
        className="flex h-14 w-full items-center justify-center gap-3 rounded-md bg-[#bbb7ff] px-4 font-semibold text-[#0b08a8] shadow-[0_16px_34px_rgba(126,121,255,0.22)] transition hover:bg-[#d1ceff] disabled:cursor-not-allowed disabled:opacity-55"
        onClick={onGenerate}
      >
        {isGenerating ? (
          <Loader2 className="h-5 w-5 animate-spin" />
        ) : (
          <Sparkles className="h-5 w-5" />
        )}
        {isGenerating ? "Generating..." : "Generate Documentation"}
      </button>
      <p className="mt-4 text-center text-xs text-[#c9c5d8]">
        Synthetic reasoning may take 15-30 seconds.
      </p>
    </aside>
  );
}
