import { PullRequest, PullRequestDecision } from "@/types/pull-request";

export function getDecisionLabel(decision?: PullRequestDecision | string) {
  if (!decision) return "Pending";

  if (decision === "needs_changes") return "Needs changes";

  return decision.charAt(0).toUpperCase() + decision.slice(1);
}

export function getDecisionTone(decision?: PullRequestDecision | string) {
  switch (decision) {
    case "approve":
      return "border-[#1f7a3b] bg-[#0b2c18] text-[#86efac]";
    case "reject":
      return "border-[#7a2636] bg-[#2a1016] text-[#ffb6c0]";
    case "needs_changes":
      return "border-[#73542a] bg-[#261909] text-[#ffcf8a]";
    default:
      return "border-[#444254] bg-[#151419] text-[#c9c5d8]";
  }
}

export function getRiskTone(risk?: string) {
  switch (risk) {
    case "low":
      return "text-[#86efac]";
    case "medium":
      return "text-[#ffcf8a]";
    case "high":
      return "text-[#ff9bad]";
    default:
      return "text-[#d8d4e6]";
  }
}

export function formatConfidence(score?: number | null) {
  if (score === null || score === undefined) return "Pending";

  return `${Math.round(score * 100)}%`;
}

export function formatPullRequestDate(dateString?: string) {
  if (!dateString) return "Unknown";

  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(dateString));
}

export function getPullRequestRisk(pr: PullRequest) {
  if (pr.deletions > 200 || pr.files_changed > 20) return "High";
  if (pr.deletions > 40 || pr.files_changed > 8) return "Medium";
  return "Low";
}

