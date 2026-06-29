"use client";

import { GitPullRequestArrow } from "lucide-react";

type PullRequestEmptyStateProps = {
  message: string;
};

export function PullRequestEmptyState({ message }: PullRequestEmptyStateProps) {
  return (
    <div className="flex min-h-[360px] items-center justify-center rounded-md border border-[#32313f] bg-[#08080b] p-8 text-center">
      <div>
        <div className="mx-auto grid h-14 w-14 place-items-center rounded-md border border-[#444254] bg-[#151419] text-[#bbb7ff]">
          <GitPullRequestArrow className="h-7 w-7" />
        </div>
        <h2 className="mt-5 font-display text-2xl font-bold text-white">
          Pull request workspace
        </h2>
        <p className="mt-3 max-w-md text-sm leading-7 text-[#c9c5d8]">{message}</p>
      </div>
    </div>
  );
}
