"use client";

import { PullRequest } from "@/types/pull-request";
import {
  getDecisionLabel,
  getDecisionTone,
  getPullRequestRisk,
} from "@/utils/pull-request";
import { GitPullRequest, Sparkles } from "lucide-react";

type PullRequestListProps = {
  pullRequests: PullRequest[];
  selectedNumber?: number;
  onSelect: (pullRequest: PullRequest) => void;
  onPrefetch?: (pullRequest: PullRequest) => void;
};

export function PullRequestList({
  pullRequests,
  selectedNumber,
  onSelect,
  onPrefetch,
}: PullRequestListProps) {
  return (
    <div className="space-y-3">
      {pullRequests.map((pullRequest) => {
        const selected = pullRequest.number === selectedNumber;

        return (
          <button
            key={pullRequest.number}
            type="button"
            className={`w-full rounded-md border p-4 text-left transition ${
              selected
                ? "border-[#8580ff] bg-[#7772ff] text-[#0b0820]"
                : "border-[#32313f] bg-[#0b0b0f] text-[#f4f0ff] hover:border-[#59566d] hover:bg-[#151419]"
            }`}
            onClick={() => onSelect(pullRequest)}
            onFocus={() => onPrefetch?.(pullRequest)}
            onMouseEnter={() => onPrefetch?.(pullRequest)}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="flex items-center gap-2 font-mono text-sm font-bold">
                  <GitPullRequest className="h-4 w-4 shrink-0" />#
                  {pullRequest.number}
                </p>
                <h3 className="mt-2 line-clamp-2 text-base font-semibold">
                  {pullRequest.title}
                </h3>
              </div>
              <span
                className={`shrink-0 rounded px-2 py-1 text-xs font-bold uppercase ${
                  selected
                    ? "bg-[#151047] text-[#d9d6ff]"
                    : pullRequest.state === "open"
                      ? "bg-[#0b2c18] text-[#86efac]"
                      : "bg-[#252334] text-[#c9c5d8]"
                }`}
              >
                {pullRequest.state}
              </span>
            </div>

            <div
              className={`mt-4 grid grid-cols-3 gap-2 text-xs ${
                selected ? "text-[#1c1947]" : "text-[#aaa7b8]"
              }`}
            >
              <span>{pullRequest.files_changed} files</span>
              <span className="text-[#53e38d]">+{pullRequest.additions}</span>
              <span className="text-[#ff9bad]">-{pullRequest.deletions}</span>
            </div>

            <div className="mt-4 flex items-center justify-between gap-3">
              <span
                className={`rounded px-2 py-1 text-xs font-semibold ${
                  selected ? "bg-[#151047] text-[#d9d6ff]" : getDecisionTone(pullRequest.ai_decision)
                }`}
              >
                <Sparkles className="mr-1 inline h-3 w-3" />
                {getDecisionLabel(pullRequest.ai_decision)}
              </span>
              <span
                className={`text-xs font-semibold ${
                  selected ? "text-[#151047]" : "text-[#d8d4e6]"
                }`}
              >
                Risk {getPullRequestRisk(pullRequest)}
              </span>
            </div>
          </button>
        );
      })}
    </div>
  );
}
