import { RepositoryStatus } from "@/types/repo";

export function getStatusLabel(status: RepositoryStatus) {
  switch (status) {
    case "ready":
      return "Indexed";

    case "failed":
      return "Failed";

    case "pending":
      return "Pending";

    case "queued":
      return "Queued";

    case "cloning":
      return "Cloning";

    case "parsing":
      return "Parsing";

    case "graph_building":
      return "Building Graph";

    case "embedding":
      return "Embedding";

    case "updating":
      return "Updating";

    default:
      return status;
  }
}

export function getTimeAgo(dateString?: string) {
  if (!dateString) return "Unknown";

  const rtf = new Intl.RelativeTimeFormat("en", {
    numeric: "auto",
  });

  const diffSeconds = Math.floor(
    (new Date(dateString).getTime() - Date.now()) / 1000,
  );

  const minutes = Math.floor(diffSeconds / 60);
  const hours = Math.floor(diffSeconds / 3600);
  const days = Math.floor(diffSeconds / 86400);

  if (Math.abs(minutes) < 60) return rtf.format(minutes, "minute");
  if (Math.abs(hours) < 24) return rtf.format(hours, "hour");

  return rtf.format(days, "day");
}

export function getDateTime(time: string) {
  return new Date(time).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
