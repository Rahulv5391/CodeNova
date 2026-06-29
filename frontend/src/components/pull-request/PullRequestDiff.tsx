"use client";

import { PullRequestFile } from "@/types/pull-request";
import { FileCode2 } from "lucide-react";

type PullRequestDiffProps = {
  files: PullRequestFile[];
};

export function PullRequestDiff({ files }: PullRequestDiffProps) {
  if (!files.length) {
    return (
      <div className="rounded-md border border-[#32313f] bg-[#08080b] p-6 text-sm text-[#aaa7b8]">
        No file diff is available for this pull request.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {files.map((file) => (
        <article
          key={file.filename}
          className="overflow-hidden rounded-md border border-[#32313f] bg-[#08080b]"
        >
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#32313f] bg-[#151419] px-4 py-3">
            <h3 className="flex min-w-0 items-center gap-2 font-mono text-sm text-[#f4f0ff]">
              <FileCode2 className="h-4 w-4 shrink-0 text-[#55dfff]" />
              <span className="truncate">{file.filename}</span>
            </h3>
            <div className="flex items-center gap-3 text-xs">
              <span className="rounded bg-[#252334] px-2 py-1 font-semibold text-[#d8d4e6]">
                {file.status}
              </span>
              <span className="text-[#53e38d]">+{file.additions}</span>
              <span className="text-[#ff9bad]">-{file.deletions}</span>
            </div>
          </div>

          {file.patch ? (
            <pre className="max-h-80 overflow-auto p-4 text-sm leading-6">
              <code className="font-mono text-[#d8d4e6]">
                {file.patch.split("\n").map((line, index) => (
                  <span
                    key={`${file.filename}-${index}`}
                    className={`block whitespace-pre-wrap ${
                      line.startsWith("+")
                        ? "bg-[#0b2c18] text-[#86efac]"
                        : line.startsWith("-")
                          ? "bg-[#2a1016] text-[#ffb6c0]"
                          : line.startsWith("@@")
                            ? "text-[#9adfff]"
                            : ""
                    }`}
                  >
                    {line}
                  </span>
                ))}
              </code>
            </pre>
          ) : (
            <p className="p-4 text-sm text-[#aaa7b8]">Patch not available.</p>
          )}
        </article>
      ))}
    </div>
  );
}
