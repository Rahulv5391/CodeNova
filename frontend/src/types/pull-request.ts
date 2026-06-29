export type PullRequestState = "open" | "closed" | "merged";
export type PullRequestAnalysisStatus =
  | "not_analyzed"
  | "pending"
  | "running"
  | "done"
  | "failed";
export type PullRequestDecision = "approve" | "reject" | "needs_changes" | null;
export type HumanDecision = "pending" | "approved" | "rejected" | "merged";

export type PullRequestFile = {
  filename: string;
  status: string;
  additions: number;
  deletions: number;
  changes: number;
  patch: string | null;
  previous_filename: string | null;
};

export type PullRequest = {
  number: number;
  title: string;
  body: string | null;
  author: string;
  state: PullRequestState | string;
  merged: boolean;
  base_branch: string;
  head_branch: string;
  created_at: string;
  updated_at: string;
  url: string;
  files_changed: number;
  additions: number;
  deletions: number;
  commits: number;
  mergeable: boolean | null;
  analysis_status: PullRequestAnalysisStatus | string;
  ai_decision: PullRequestDecision | string;
  confidence_score: number | null;
  human_decision: HumanDecision | string;
  files: PullRequestFile[];
};

export type PullRequestImpactAnalysis = {
  per_file: Record<string, unknown>;
  total_dependent_files: number;
  total_affected_functions: number;
  breaking_change_risk: "low" | "medium" | "high" | string;
};

export type PullRequestReview = {
  pr_number: number;
  repository_id: string;
  analysis_status: PullRequestAnalysisStatus | string;
  summary: string;
  code_review: string;
  optimization_suggestions: string;
  impact_analysis: PullRequestImpactAnalysis;
  ai_decision: Exclude<PullRequestDecision, null> | string;
  confidence_score: number | null;
  risk_flags: string[];
  ai_decision_reason: string;
  total_tokens: number;
  error_message: string | null;
  human_decision: HumanDecision | string;
  human_decision_note: string | null;
  created_at: string;
  updated_at: string;
};

export type PullRequestApproval = {
  pr_number: number;
  human_decision: HumanDecision | string;
  github_action?: {
    review_id?: number;
    state?: string;
    merge?: {
      merged: boolean;
      sha?: string;
      message?: string;
    };
  };
  decided_at: string;
};


export type PRDecisionRequest = {
  action: "approve" | "reject";
  note: string;
  merge_on_approve: boolean;
  merge_method: "merge" | "squash" | "rebase";
};

export type PullRequestPanel = {
  pullRequest: PullRequest | null;
  decisionOpen: boolean;
  isApproving: boolean;
  onDecisionOpenChange: (open: boolean) => void;
  onDecision: (decision: PRDecisionRequest) => void;
}