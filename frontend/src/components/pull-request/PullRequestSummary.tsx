"use client";

import { PullRequest } from "@/types/pull-request";
import { formatPullRequestDate } from "@/utils/pull-request";
import {
  CalendarClock,
  ExternalLink,
  GitBranch,
  GitCommitHorizontal,
  UserRound,
} from "lucide-react";
import Link from "next/link";

type PullRequestSummaryProps = {
  pullRequest: PullRequest;
};

export function PullRequestSummary({ pullRequest }: PullRequestSummaryProps) {
  return (
    <section className="rounded-md border border-[#32313f] bg-[#08080b] p-6">
      <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-start">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-display text-3xl font-bold text-white">
              {pullRequest.title}
            </h1>
            <span className="rounded bg-[#0b2c18] px-3 py-1 text-xs font-bold uppercase text-[#86efac]">
              {pullRequest.state}
            </span>
          </div>
          <p className="mt-3 text-sm leading-7 text-[#d8d4e6]">
            {pullRequest.body || "No pull request description provided."}
          </p>
        </div>

        <Link
          href={pullRequest.url}
          target="_blank"
          className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-md border border-[#444254] px-3 text-sm font-semibold text-[#d8d4e6] transition hover:bg-[#1b1a20] hover:text-white"
        >
          <ExternalLink className="h-4 w-4" />
          GitHub
        </Link>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Info icon={<UserRound className="h-4 w-4" />} label="Author" value={pullRequest.author} />
        <Info
          icon={<GitBranch className="h-4 w-4" />}
          label="Branches"
          value={`${pullRequest.head_branch} -> ${pullRequest.base_branch}`}
        />
        <Info
          icon={<GitCommitHorizontal className="h-4 w-4" />}
          label="Commits"
          value={`${pullRequest.commits}`}
        />
        <Info
          icon={<CalendarClock className="h-4 w-4" />}
          label="Updated"
          value={formatPullRequestDate(pullRequest.updated_at)}
        />
      </div>
    </section>
  );
}

function Info({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-md border border-[#32313f] bg-[#121216] p-4">
      <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.14em] text-[#aaa7b8]">
        {icon}
        {label}
      </p>
      <p className="mt-2 break-words text-sm font-semibold text-[#f4f0ff]">
        {value}
      </p>
    </div>
  );
}
