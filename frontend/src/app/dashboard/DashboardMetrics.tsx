import { Repository } from "@/types/repo";


function reposCreatedThisMonth(repos: Repository[]) {
  const now = new Date();
  return repos.filter((repo) => {
    const created = new Date(repo.created_at);

    return (
      created.getMonth() === now.getMonth() &&
      created.getFullYear() === now.getFullYear()
    );
  }).length;
}

export default function DashboardMetrics({ repos }: { repos: Repository[] }) {
  const metrics = [
    {
      label: "Total Repos",
      value: repos.length,
      detail: `+${reposCreatedThisMonth(repos)} this month`,
      color: "border-l-[#b8b2ff]",
    },
    {
      label: "Files Indexed",
      value: `${repos.reduce((s, r) => s + r.total_files, 0)}`,
      detail: "Optimized",
      color: "border-l-[#55dfff]",
    },
    {
      label: "Functions Map",
      value: `${repos.reduce((s, r) => s + r.total_functions, 0)}`,
      detail: "Deep Scan active",
      color: "border-l-[#ffb57a]",
    },
    {
      label: "Code Chunks Indexed",
      value: `${repos.reduce((s, r) => s + r.indexed_chunks, 0)}`,
      detail: "Deep Scan active",
      color: "border-l-[#ffb57a]",
    },
  ];

  return (
    <div className="mt-10 grid gap-7 sm:grid-cols-2 xl:grid-cols-4">
      {metrics.map((metric, index) => (
        <article
          key={index}
          className={`rounded-md border border-[#32313f] border-l-4 bg-[#09090c] p-6 ${metric.color}`}
        >
          <p className="text-sm uppercase tracking-[0.16em] text-[#aaa7b8]">
            {metric.label}
          </p>
          <p className="font-display mt-3 text-3xl text-white">
            {metric.value}
          </p>
          <p className="mt-4 text-sm text-[#55dfff]">{metric.detail}</p>
        </article>
      ))}
    </div>
  );
}
