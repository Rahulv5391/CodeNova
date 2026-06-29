"use client";

import { PullRequest } from "@/types/pull-request";
import { GitCommitHorizontal, GitPullRequest, Plus, ShieldCheck } from "lucide-react";

type PullRequestStatsProps = {
  pullRequests: PullRequest[];
};

export function PullRequestStats({ pullRequests }: PullRequestStatsProps) {
  const openCount = pullRequests.filter((item) => item.state === "open").length;
  const reviewedCount = pullRequests.filter(
    (item) => item.analysis_status === "done" || item.ai_decision,
  ).length;
  const changedFiles = pullRequests.reduce(
    (total, item) => total + item.files_changed,
    0,
  );
  const commits = pullRequests.reduce((total, item) => total + item.commits, 0);

  return (
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <StatCard icon={<GitPullRequest className="h-5 w-5" />} label="Open PRs" value={openCount} />
      <StatCard icon={<ShieldCheck className="h-5 w-5" />} label="AI Reviewed" value={reviewedCount} />
      <StatCard icon={<Plus className="h-5 w-5" />} label="Files Changed" value={changedFiles} />
      <StatCard icon={<GitCommitHorizontal className="h-5 w-5" />} label="Commits" value={commits} />
    </section>
  );
}

function StatCard({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
}) {
  return (
    <div className="rounded-md border border-[#32313f] bg-[#121216] p-4">
      <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.14em] text-[#aaa7b8]">
        <span className="grid h-8 w-8 place-items-center rounded-md border border-[#3d395d] bg-[#151525] text-[#bbb7ff]">
          {icon}
        </span>
        {label}
      </p>
      <p className="mt-3 font-display text-3xl font-bold text-white">{value}</p>
    </div>
  );
}
