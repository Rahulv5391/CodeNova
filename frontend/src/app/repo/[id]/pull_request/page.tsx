
"use client";

import AppShell, { MobileHint } from "@/components/AppShell";
import DecisionPanel from "@/components/pull-request/DecisionPanel";
import { PullRequestDiff } from "@/components/pull-request/PullRequestDiff";
import { PullRequestEmptyState } from "@/components/pull-request/PullRequestEmptyState";
import { PullRequestList } from "@/components/pull-request/PullRequestList";
import { PullRequestReviewPanel } from "@/components/pull-request/PullRequestReviewPanel";
import { PullRequestStats } from "@/components/pull-request/PullRequestStats";
import { PullRequestSummary } from "@/components/pull-request/PullRequestSummary";
import { queryKeys } from "@/lib/query-keys";
import {
  decidePullRequest,
  getPullRequestDetail,
  getPullRequestRepository,
  getPullRequests,
  reviewPullRequest,
} from "@/lib/pull-request-api";
import {
  PRDecisionRequest,
  PullRequest,
  PullRequestReview,
} from "@/types/pull-request";
import { getStatusLabel } from "@/utils/repo";
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  GitMerge,
  GitBranch,
  GitPullRequestArrow,
  Loader2,
  RefreshCcw,
  Sparkles,
} from "lucide-react";
import { useParams } from "next/navigation";
import { useState } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { toast } from "sonner";

async function fetchPullRequestWorkspace(repoId: string) {
  const [repository, pullRequestItems] = await Promise.all([
    getPullRequestRepository(repoId),
    getPullRequests(repoId),
  ]);
  return { repository, pullRequestItems };
}

export default function PullRequestPage() {
  const params = useParams<{ id: string }>();
  const repoId = params.id;
  const queryClient = useQueryClient();
  const [review, setReview] = useState<PullRequestReview | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [decisionPanelOpen, setDecisionPanelOpen] = useState(false);
  const [reviewDecisionPanelOpen, setReviewDecisionPanelOpen] = useState(false);
  const [selectedPullRequestNumber, setSelectedPullRequestNumber] = useState<
    number | null
  >(null);

  const workspaceQuery = useQuery({
    queryKey: queryKeys.pullRequests.workspace(repoId),
    queryFn: () => fetchPullRequestWorkspace(repoId),
  });

  const repo = workspaceQuery.data?.repository ?? null;
  const pullRequests = workspaceQuery.data?.pullRequestItems ?? [];
  const selectedListItem =
    pullRequests.find((item) => item.number === selectedPullRequestNumber) ??
    null;

  const selectedPullRequestQuery = useQuery({
    queryKey:
      selectedPullRequestNumber === null
        ? ["pull-requests", repoId, "none"]
        : queryKeys.pullRequests.detail(repoId, selectedPullRequestNumber),
    queryFn: () => getPullRequestDetail(repoId, selectedPullRequestNumber ?? 0),
    enabled: selectedPullRequestNumber !== null,
    placeholderData: selectedListItem ?? undefined,
  });

  const selectedPullRequest =
    selectedPullRequestQuery.data ?? selectedListItem ?? null;
  const isLoading = workspaceQuery.isLoading;
  const error = workspaceQuery.isError
    ? "Unable to load pull requests for this repository."
    : "";
  const isSelectedPullRequestLoading =
    selectedPullRequestNumber !== null &&
    selectedPullRequestQuery.isFetching &&
    !selectedPullRequestQuery.data?.files?.length;

  const reviewMutation = useMutation({
    mutationFn: (prNumber: number) => reviewPullRequest(repoId, prNumber),
    onSuccess: (reviewData, prNumber) => {
      queryClient.setQueryData(
        queryKeys.pullRequests.review(repoId, prNumber),
        reviewData,
      );
      setReview(reviewData);
      toast.success("AI review is ready.");
    },
    onError: () => {
      toast.error("Unable to generate AI suggestions.");
    },
  });

  const decisionMutation = useMutation({
    mutationFn: ({
      prNumber,
      decision,
    }: {
      prNumber: number;
      decision: PRDecisionRequest;
    }) => decidePullRequest(repoId, prNumber, decision),
    onSuccess: (approval, variables) => {
      const updatedPullRequest = (item: PullRequest) =>
        item.number === variables.prNumber
          ? {
              ...item,
              human_decision: approval.human_decision,
              merged: approval.github_action?.merge?.merged ?? item.merged,
              state: approval.github_action?.merge?.merged
                ? "merged"
                : variables.decision.action === "reject"
                  ? "closed"
                  : item.state,
            }
          : item;

      queryClient.setQueryData<
        Awaited<ReturnType<typeof fetchPullRequestWorkspace>>
      >(queryKeys.pullRequests.workspace(repoId), (current) =>
        current
          ? {
              ...current,
              pullRequestItems: current.pullRequestItems.map(updatedPullRequest),
            }
          : current,
      );

      queryClient.setQueryData<PullRequest>(
        queryKeys.pullRequests.detail(repoId, variables.prNumber),
        (current) => (current ? updatedPullRequest(current) : current),
      );

      toast.success(
        approval.github_action?.merge?.message ??
          `Pull request ${approval.human_decision}.`,
      );
      setDecisionPanelOpen(false);
      setReviewDecisionPanelOpen(false);
    },
    onError: () => {
      toast.error("Unable to apply this pull request decision.");
    },
  });

  async function handleReview() {
    if (!selectedPullRequest || reviewMutation.isPending) return;

    setPanelOpen(true);
    reviewMutation.mutate(selectedPullRequest.number);
  }

  async function handleDecision(decision: PRDecisionRequest) {
    if (!selectedPullRequest || decisionMutation.isPending) return;

    decisionMutation.mutate({
      prNumber: selectedPullRequest.number,
      decision,
    });
  }

  function handleSelect(pullRequest: PullRequest) {
    const cachedReview = queryClient.getQueryData<PullRequestReview>(
      queryKeys.pullRequests.review(repoId, pullRequest.number),
    );

    setReview(cachedReview ?? null);
    setSelectedPullRequestNumber(pullRequest.number);
  }

  function prefetchPullRequest(pullRequest: PullRequest) {
    queryClient.prefetchQuery({
      queryKey: queryKeys.pullRequests.detail(repoId, pullRequest.number),
      queryFn: () => getPullRequestDetail(repoId, pullRequest.number),
    });
  }

  function openReviewPanel() {
    setPanelOpen(true);
  }

  function openDecisionPanel() {
    setDecisionPanelOpen(true);
  }

  function closeReviewPanel() {
    setReviewDecisionPanelOpen(false);
    setPanelOpen(false);
  }

  return (
    <AppShell active="Dashboard">
      <MobileHint />
      <section className="min-h-[calc(100vh-80px)] bg-[#050506] px-5 py-8 text-[#f4f0ff] nexus-grid md:px-10 lg:px-12">
        <div className="mx-auto max-w-[1500px]">
          <header className="flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
            <div>
              <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.18em] text-[#aaa7b8]">
                <GitPullRequestArrow className="h-4 w-4 text-[#bbb7ff]" />
                Pull request intelligence
              </p>
              <h1 className="mt-3 font-display text-4xl font-bold text-white md:text-5xl">
                {repo?.full_name ?? "Repository pull requests"}
              </h1>
              <div className="mt-4 flex flex-wrap items-center gap-3 text-sm text-[#d8d4e6]">
                {repo?.branch ? (
                  <span className="inline-flex items-center gap-2 rounded-md border border-[#32313f] bg-[#121216] px-3 py-2">
                    <GitBranch className="h-4 w-4 text-[#63e7ff]" />
                    {repo.branch}
                  </span>
                ) : null}
                {repo?.status ? (
                  <span className="inline-flex items-center gap-2 rounded-md border border-[#32313f] bg-[#121216] px-3 py-2">
                    <CheckCircle2 className="h-4 w-4 text-[#86efac]" />
                    {getStatusLabel(repo.status)}
                  </span>
                ) : null}
              </div>
            </div>

            <div className="flex flex-wrap gap-3">
              <button
                className="inline-flex h-11 cursor-pointer items-center justify-center gap-2 rounded-md border border-[#444254] bg-[#121216] px-4 text-sm font-semibold text-[#d8d4e6] transition hover:bg-[#1b1a20] hover:text-white"
                onClick={() => workspaceQuery.refetch()}
                disabled={workspaceQuery.isFetching}
              >
                {workspaceQuery.isFetching ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCcw className="h-4 w-4" />
                )}
                Refresh
              </button>
              <button
                className="inline-flex cursor-pointer h-11 items-center justify-center gap-2 rounded-md bg-[#bbb7ff] px-4 text-sm font-bold text-[#0b08a8] shadow-[0_18px_40px_rgba(126,121,255,0.24)] transition hover:bg-[#d1ceff] disabled:cursor-not-allowed disabled:opacity-50"
                onClick={openReviewPanel}
                disabled={!selectedPullRequest}
              >
                <Sparkles className="h-4 w-4" />
                AI Suggestions
              </button>
            </div>
          </header>

          <div className="mt-8 grid gap-6 xl:grid-cols-[330px_1fr]">
            <aside className="space-y-5">
              <section className="rounded-md border border-[#32313f] bg-[#121216] p-5">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#aaa7b8]">
                      Active pull requests
                    </p>
                    <p className="mt-2 text-sm text-[#d8d4e6]">
                      Select a PR to inspect files and request AI review.
                    </p>
                  </div>
                  <Bot className="h-5 w-5 text-[#bbb7ff]" />
                </div>
              </section>

              {isLoading ? (
                <LoadingPanel label="Loading pull requests..." />
              ) : pullRequests.length ? (
                <PullRequestList
                  pullRequests={pullRequests}
                  selectedNumber={selectedPullRequest?.number}
                  onSelect={handleSelect}
                  onPrefetch={prefetchPullRequest}
                />
              ) : (
                <PullRequestEmptyState message="No pull requests were returned for this repository yet." />
              )}
            </aside>

            <main className="min-w-0 space-y-6">
              {error ? (
                <div className="rounded-md border border-[#7a2636] bg-[#2a1016] p-5 text-[#ffb6c0]">
                  <AlertTriangle className="mr-2 inline h-5 w-5" />
                  {error}
                </div>
              ) : null}

              {isLoading ? (
                <LoadingPanel label="Preparing pull request workspace..." />
              ) : isSelectedPullRequestLoading ? (
                <LoadingPanel label="Loading pull request details..." />
              ) : selectedPullRequest ? (
                <>
                  <PullRequestStats pullRequests={pullRequests} />
                  <PullRequestSummary pullRequest={selectedPullRequest} />

                  <section className="rounded-md border border-[#32313f] bg-[#121216] p-5">
                    <div className="flex flex-col justify-between gap-4 border-b border-[#32313f] pb-5 md:flex-row md:items-center">
                      <div>
                        <h2 className="font-display text-2xl font-bold text-white">
                          Changed files
                        </h2>
                        <p className="mt-2 text-sm text-[#aaa7b8]">
                          Reviewing diff for PR #{selectedPullRequest.number}.
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-3">
                        <button
                          type="button"
                          className="inline-flex h-10 cursor-pointer items-center justify-center gap-2 rounded-md border border-[#3d395d] bg-[#151525] px-3 text-sm font-semibold text-[#c5c1ff] transition hover:bg-[#1d1d2d] hover:text-white"
                          onClick={handleReview}
                          disabled={reviewMutation.isPending}
                        >
                          {reviewMutation.isPending ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Sparkles className="h-4 w-4" />
                          )}
                          Get AI Suggestions
                        </button>
                        <button
                          type="button"
                          className="inline-flex h-10 cursor-pointer items-center justify-center gap-2 rounded-md bg-[#bbb7ff] px-3 text-sm font-bold text-[#0b08a8] transition hover:bg-[#d1ceff]"
                          onClick={openDecisionPanel}
                        >
                          <GitMerge className="h-4 w-4" />
                          Approve / Reject
                        </button>
                      </div>
                    </div>
                    <div className="mt-5">
                      <PullRequestDiff files={selectedPullRequest.files} />
                    </div>
                  </section>
                </>
              ) : (
                <PullRequestEmptyState message="Choose a repository with pull requests to start reviewing code changes." />
              )}
            </main>
          </div>
        </div>
      </section>


      <PullRequestReviewPanel
        pullRequest={selectedPullRequest}
        review={review}
        open={panelOpen}
        decisionOpen={reviewDecisionPanelOpen}
        isReviewing={reviewMutation.isPending}
        isApproving={decisionMutation.isPending}
        onClose={closeReviewPanel}
        onDecisionOpenChange={setReviewDecisionPanelOpen}
        onReview={handleReview}
        onDecision={handleDecision}
      />
      <div
        className={`fixed inset-0 z-50 overflow-hidden ${
          decisionPanelOpen ? "" : "pointer-events-none"
        }`}
      >
        <DecisionPanel
          pullRequest={selectedPullRequest}
          decisionOpen={decisionPanelOpen}
          isApproving={decisionMutation.isPending}
          onDecisionOpenChange={setDecisionPanelOpen}
          onDecision={handleDecision}
        />
      </div>
    </AppShell>
  );
}

function LoadingPanel({ label }: { label: string }) {
  return (
    <div className="flex min-h-36 items-center justify-center rounded-md border border-[#32313f] bg-[#121216] text-sm text-[#c9c5d8]">
      <Loader2 className="mr-2 h-4 w-4 animate-spin text-[#bbb7ff]" />
      {label}
    </div>
  );
}
