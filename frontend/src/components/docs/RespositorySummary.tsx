import { Repository } from "@/types/repo";
import { getStatusLabel, getTimeAgo } from "@/utils/repo";
import { Clock3, FileCode2, Loader2 } from "lucide-react";

export function RepositorySummary({
  repo,
  isLoading,
  error,
}: {
  repo: Repository | null;
  isLoading: boolean;
  error: string;
}) {
  return (
    <section className="grid gap-5 rounded-md border border-[#32313f] bg-[#08080b] p-6 shadow-[0_24px_70px_rgba(0,0,0,0.28)] lg:grid-cols-[1fr_auto] lg:items-center">
      <div className="flex min-w-0 items-start gap-4">
        <div className="grid h-14 w-14 shrink-0 place-items-center rounded-md border border-[#444254] bg-[#1d1c24] text-[#c5c1ff]">
          {isLoading ? (
            <Loader2 className="h-7 w-7 animate-spin" />
          ) : (
            <FileCode2 className="h-7 w-7" />
          )}
        </div>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="truncate font-display text-2xl font-bold text-white">
              {repo?.full_name ??
                (error ? "Repository unavailable" : "Loading repository...")}
            </h2>
            <span className="rounded bg-[#252334] px-3 py-1 font-mono text-xs font-bold text-[#d7d3ff]">
              {repo?.branch ?? "main"}
            </span>
          </div>
          <p className="mt-2 flex items-center gap-2 text-sm text-[#c9c5d8]">
            <Clock3 className="h-4 w-4" />
            {error || `Last synced ${getTimeAgo(repo?.updated_at)} ago`}
          </p>
        </div>
      </div>

      <dl className="grid gap-5 text-sm sm:grid-cols-3 lg:min-w-[440px]">
        <Metric
          label="Total Files"
          value={isLoading ? "..." : (repo?.total_files ?? 0).toLocaleString()}
        />
        <Metric
          label="Analysis Status"
          value={getStatusLabel(repo?.status ?? "pending")}
          accent={repo?.status === "failed" ? "red" : "cyan"}
        />
      </dl>
    </section>
  );
}

function Metric({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: "cyan" | "red";
}) {
  return (
    <div>
      <dt className="text-xs font-bold uppercase tracking-[0.16em] text-[#aaa7b8]">
        {label}
      </dt>
      <dd className="mt-1 flex items-center gap-2 font-display text-2xl text-white">
        {accent ? (
          <span
            className={`h-2.5 w-2.5 rounded-full ${
              accent === "red" ? "bg-[#ff9b9b]" : "bg-[#55dfff]"
            }`}
          />
        ) : null}
        {value}
      </dd>
    </div>
  );
}
