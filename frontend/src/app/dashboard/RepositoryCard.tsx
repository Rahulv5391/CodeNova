"use client";

import {
  Code2,
  Boxes,
  Compass,
  Link2,
  ExternalLink,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { deleteRepo, updateRepo } from "./actions";

import { toast } from "sonner";
import Link from "next/link";
import { Repository, RepositoryStatus } from "@/types/repo";
import { getStatusLabel } from "@/utils/repo";
import { useState } from "react";


type RepositoryCardProps = {
  repo: Repository;
  index: number;
  onDelete: (id: string) => void;
  onUpdate: (repo: Repository) => void;
};

function getStatusTone(status: RepositoryStatus) {
  switch (status) {
    case "ready":
      return "text-[#4ade80]"; // cyan → success

    case "pending":
    case "queued":
      return "text-[#b5b5c3]"; // muted gray

    case "cloning":
    case "parsing":
    case "graph_building":
    case "embedding":
      return "text-[#55dfff]"; // orange → processing
    case "updating":
      return "text-[#ffbd8a]";

    case "failed":
      return "text-[#ffb5b5]"; // red → error

    default:
      return "text-white";
  }
}


export default function RespositoryCard({ repo, index, onDelete, onUpdate }: RepositoryCardProps) {
  const [isRefreshing, setIsRefreshing] = useState(false);
  const showRefreshSpinner =
    isRefreshing && repo.status !== "ready" && repo.status !== "failed";

  const handleDelete = async () => {
    try {
      await deleteRepo(repo);
      onDelete(repo.id);
      toast.success("Deleted");
    } catch {
      toast.error("Failed");
    }
  };

  const handleUpdate = async () => {
    setIsRefreshing(true);
    onUpdate({
      ...repo,
      status: "updating",
      progress: 0,
      updated_at: new Date().toISOString(),
    });

    try {
      const data = await updateRepo(repo);
      if (data?.repo) {
        onUpdate(data.repo);
      }
      toast.success("Update Started");
    } catch {
      setIsRefreshing(false);
      onUpdate(repo);
      toast.error("Update Failed");
    }
  };

  return (
    <article
      key={repo.id}
      className="grid gap-5 rounded-md border border-[#32313f] bg-[#08080b] p-7 xl:grid-cols-[1fr_auto] xl:items-center"
    >
      <div className="flex items-start gap-7">
        <div className="grid h-16 w-16 shrink-0 place-items-center rounded-md border border-[#444254] bg-[#1d1c24]">
          {index % 3 === 0 ? (
            <Code2 className="h-8 w-8 text-[#c5c1ff]" />
          ) : index % 3 === 1 ? (
            <Boxes className="h-8 w-8 text-[#55dfff]" />
          ) : (
            <Compass className="h-8 w-8 text-[#827dff]" />
          )}
        </div>
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <Link
              href={`/repo/${repo.id}`}
              className="font-display text-2xl font-bold text-white transition hover:text-[#c5c1ff]"
            >
              {repo.full_name}
            </Link>
            {repo.branch && (
              <span className="rounded bg-[#252334] px-3 py-1 text-xs font-bold text-[#d7d3ff]">
                {repo.branch}
              </span>
            )}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-5 text-lg text-[#d8d4e6]">
            <Link
              href={repo.github_url}
              target="_blank"
              className="flex items-center gap-2 font-mono"
            >
              <Link2 className="h-4 w-4" />
              {repo.github_url}
            </Link>
            <span className="h-6 w-px bg-[#444254]" />
            {repo.lang && (
              <>
                <span className="flex items-center gap-2">
                  <span className="h-3 w-3 rounded-full bg-[#3c9df0]" />
                  {repo.lang}
                </span>
                <span className="h-6 w-px bg-[#444254]" />
              </>
            )}
            <span>
              {new Date(repo.updated_at).toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
                year: "numeric",
              })}
            </span>
          </div>
          {repo.progress != 100 && (
            <div className="mt-3 h-2 rounded bg-[#252334] overflow-hidden">
              <div
                className="h-full bg-cyan-400 transition-all"
                style={{ width: `${repo.progress}%` }}
              />
            </div>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between gap-8 xl:justify-end">
        <span
          className={`flex items-center gap-2 ${getStatusTone(repo.status)}`}
        >
          <span className="h-3 w-3 rounded-full bg-current" />
          {getStatusLabel(repo.status)}
        </span>

        <div className="flex gap-6 text-[#d8d4e6]">
          <Link href={repo.github_url} target="_blank">
            <ExternalLink className="h-6 w-6 hover:text-cyan-200" />
          </Link>
          <RefreshCw
            className={`h-6 w-6 hover:text-yellow-200 cursor-pointer ${
              showRefreshSpinner ? "animate-spin text-yellow-200" : ""
            }`}
            onClick={handleUpdate}
          />

          <Trash2
            className="h-6 w-6 cursor-pointer hover:text-red-300"
            onClick={handleDelete}
          />
        </div>
      </div>
    </article>
  );
}
