"use client";

import DecisionPanel from "@/components/pull-request/DecisionPanel";
import {
  PRDecisionRequest,
  PullRequest,
  PullRequestReview,
} from "@/types/pull-request";
import {
  formatConfidence,
  getDecisionLabel,
  getDecisionTone,
  getRiskTone,
} from "@/utils/pull-request";
import {
  GitMerge,
  Loader2,
  Sparkles,
  X,
} from "lucide-react";
import {
  Fragment,
  useMemo,
  type ReactNode,
} from "react";

type PullRequestReviewPanelProps = {
  pullRequest: PullRequest | null;
  review: PullRequestReview | null;
  open: boolean;
  decisionOpen: boolean;
  isReviewing: boolean;
  isApproving: boolean;
  onClose: () => void;
  onDecisionOpenChange: (open: boolean) => void;
  onReview: () => void;
  onDecision: (decision: PRDecisionRequest) => void;
};

type MarkdownBlock =
  | { type: "heading"; text: string; level: number }
  | { type: "paragraph"; text: string }
  | { type: "list"; ordered: boolean; items: string[] }
  | { type: "code"; code: string; language?: string };

export function PullRequestReviewPanel({
  pullRequest,
  review,
  open,
  decisionOpen,
  isReviewing,
  isApproving,
  onClose,
  onDecisionOpenChange,
  onReview,
  onDecision,
}: PullRequestReviewPanelProps) {
  function handleClose() {
    onDecisionOpenChange(false);
    onClose();
  }

  return (
    <aside
      className={`fixed inset-y-0 right-0 z-50 w-full border-l border-[#32313f] bg-[#0b0b0f] shadow-[0_0_80px_rgba(0,0,0,0.55)] transition-transform duration-300 md:w-[78vw] ${
        open ? "translate-x-0" : "translate-x-full"
      }`}
    >
      <div className="relative flex h-full flex-col overflow-hidden">
        <div className="flex items-start justify-between gap-4 border-b border-[#32313f] bg-[#111115] p-5">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#aaa7b8]">
              AI Review
            </p>
            <h2 className="mt-2 font-display text-2xl font-bold text-white">
              {pullRequest ? `#${pullRequest.number}` : "Pull request"}
            </h2>
          </div>
          <button
            type="button"
            className="grid h-9 w-9 place-items-center rounded-md border border-[#444254] text-[#d8d4e6] transition hover:bg-[#1b1a20] hover:text-white"
            onClick={handleClose}
            aria-label="Close AI review panel"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-auto p-5">
          {!review ? (
            <div className="rounded-md border border-[#32313f] bg-[#121216] p-6">
              <Sparkles className="h-8 w-8 text-[#c5c1ff]" />
              <h3 className="mt-4 font-display text-2xl font-bold text-white">
                Generate AI suggestions
              </h3>
              <p className="mt-3 leading-7 text-[#d8d4e6]">
                Run the reviewer to get the decision, confidence, risk flags,
                impact analysis, code review, and optimization notes.
              </p>
              <button
                type="button"
                disabled={!pullRequest || isReviewing}
                className="mt-6 flex h-12 w-full items-center justify-center gap-2 rounded-md bg-[#bbb7ff] font-semibold text-[#0b08a8] transition hover:bg-[#d1ceff] disabled:cursor-not-allowed disabled:opacity-60"
                onClick={onReview}
              >
                {isReviewing ? (
                  <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                  <Sparkles className="h-5 w-5" />
                )}
                {isReviewing ? "Reviewing..." : "Get AI Suggestions"}
              </button>
            </div>
          ) : (
            <>
              <section className="rounded-md border border-[#32313f] bg-[#121216] p-5">
                <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#aaa7b8]">
                  AI Recommendation
                </p>
                <div className="mt-4 flex items-end justify-between gap-4">
                  <h3
                    className={`font-display text-4xl font-bold ${
                      review.ai_decision === "approve"
                        ? "text-[#5df08c]"
                        : review.ai_decision === "reject"
                          ? "text-[#ff9bad]"
                          : "text-[#ffcf8a]"
                    }`}
                  >
                    {getDecisionLabel(review.ai_decision)}
                  </h3>
                  <span
                    className={`rounded px-3 py-1 text-md font-bold ${getDecisionTone(review.ai_decision)}`}
                  >
                    {formatConfidence(review.confidence_score)}
                  </span>
                </div>
                <div className="mt-5 h-2 overflow-hidden rounded bg-[#252334]">
                  <div
                    className="h-full bg-[#bbb7ff]"
                    style={{
                      width: `${Math.round((review.confidence_score ?? 0) * 100)}%`,
                    }}
                  />
                </div>
                <p className="mt-5 text-md leading-6 text-[#d8d4e6]">
                  <strong className="text-white">Decision Reason:</strong>{" "}
                  {review.ai_decision_reason}
                </p>
              </section>

              <section className="grid gap-3 sm:grid-cols-3">
                <Metric label="Risk" value={review.impact_analysis.breaking_change_risk} />
                <Metric
                  label="Affected functions"
                  value={review.impact_analysis.total_affected_functions}
                />
                <Metric label="Tokens" value={review.total_tokens} />
              </section>

              <ReviewText title="Summary" body={review.summary} />
              <ReviewText title="Code Review" body={review.code_review} />
              <ReviewText
                title="Optimization"
                body={review.optimization_suggestions}
              />

              {review.risk_flags.length ? (
                <section className="rounded-md border border-[#73542a] bg-[#261909] p-5">
                  <h3 className="font-semibold text-[#ffcf8a]">Risk Flags</h3>
                  <ul className="mt-3 list-disc space-y-2 pl-5 text-md text-[#ffe0ad]">
                    {review.risk_flags.map((flag) => (
                      <li key={flag}>{flag}</li>
                    ))}
                  </ul>
                </section>
              ) : null}
            </>
          )}
        </div>

        <div className="border-t border-[#32313f] bg-[#111115] p-5">
          <button
            type="button"
            disabled={!pullRequest}
            className="flex h-12 w-full items-center justify-center gap-2 rounded-md bg-[#bbb7ff] font-semibold text-[#0b08a8] transition hover:bg-[#d1ceff] disabled:cursor-not-allowed disabled:opacity-50"
            onClick={() => onDecisionOpenChange(true)}
          >
            <GitMerge className="h-5 w-5" />
            Approve / Reject
          </button>
        </div>

        <DecisionPanel
          pullRequest={pullRequest}
          decisionOpen={decisionOpen}
          isApproving={isApproving}
          onDecisionOpenChange={onDecisionOpenChange}
          onDecision={onDecision}
        />
      </div>
    </aside>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  const valueText = String(value);

  return (
    <div className="rounded-md border border-[#32313f] bg-[#121216] p-4">
      <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#aaa7b8]">
        {label}
      </p>
      <p className={`mt-2 text-xl font-semibold ${getRiskTone(valueText)}`}>
        {valueText}
      </p>
    </div>
  );
}

function ReviewText({ title, body }: { title: string; body: string }) {
  return (
    <section className="rounded-md border border-[#32313f] bg-[#121216] p-5">
      <h3 className="font-display text-xl font-bold text-white">{title}</h3>
      <div className="mt-4 text-md leading-7 text-[#d8d4e6]">
        <MarkdownReview content={body} />
      </div>
    </section>
  );
}

function MarkdownReview({ content }: { content: string }) {
  const blocks = useMemo(() => parseMarkdown(content), [content]);

  return (
    <div className="space-y-4">
      {blocks.map((block, index) => {
        if (block.type === "heading") {
          return (
            <h4
              key={index}
              className={`font-bold text-white ${
                block.level <= 3 ? "text-base" : "text-md"
              }`}
            >
              {renderInlineMarkdown(block.text)}
            </h4>
          );
        }

        if (block.type === "list") {
          const ListTag = block.ordered ? "ol" : "ul";

          return (
            <ListTag
              key={index}
              className={`space-y-2 pl-5 ${
                block.ordered ? "list-decimal" : "list-disc"
              }`}
            >
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex} className="pl-1">
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
              <pre className="overflow-x-auto p-4 text-md leading-6">
                <code className="font-mono text-[#d8f8ff]">{block.code}</code>
              </pre>
            </div>
          );
        }

        return (
          <p key={index}>
            {renderInlineMarkdown(block.text).map((part, partIndex) => (
              <Fragment key={partIndex}>{part}</Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}

function parseMarkdown(content: string): MarkdownBlock[] {
  const blocks: MarkdownBlock[] = [];
  const fenceRegex = /```([a-zA-Z0-9_-]+)?\s*([\s\S]*?)```/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  function pushTextBlocks(text: string) {
    const normalized = text.replace(/\r\n/g, "\n").trim();

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

      const headingMatch = trimmed.match(/^(#{1,6})\s+(.+)$/);
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
  const tokenRegex = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = tokenRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }

    const token = match[0];

    if (token.startsWith("**")) {
      parts.push(
        <strong key={match.index} className="font-semibold text-white">
          {token.slice(2, -2)}
        </strong>,
      );
    } else {
      parts.push(
        <code
          key={match.index}
          className="rounded border border-[#3c394d] bg-[#0b0b11] px-1.5 py-0.5 font-mono text-[0.9em] text-[#b8f7ff]"
        >
          {token.slice(1, -1)}
        </code>,
      );
    }

    lastIndex = tokenRegex.lastIndex;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts;
}
