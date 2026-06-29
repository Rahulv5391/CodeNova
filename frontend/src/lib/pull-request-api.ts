import { api } from "@/lib/api";
import {
  PRDecisionRequest,
  PullRequestApproval,
  PullRequest,
  PullRequestReview,
} from "@/types/pull-request";
import { Repository } from "@/types/repo";

export async function getPullRequestRepository(repositoryId: string) {
  const { data } = await api.get<{ repo: Repository }>(`/repos/${repositoryId}`);
  return data.repo;
}

export async function getPullRequests(repositoryId: string) {
  const { data } = await api.get<PullRequest[]>(`/prs/${repositoryId}`);
  return data;
}

export async function getPullRequestDetail(
  repositoryId: string,
  prNumber: number,
) {
  const { data } = await api.get<PullRequest>(
    `/prs/${repositoryId}/${prNumber}`,
  );

  return data;
}

export async function reviewPullRequest(
  repositoryId: string,
  prNumber: number,
) {
  const { data } = await api.post<PullRequestReview>(
    `/prs/${repositoryId}/${prNumber}/analyze`,
  );
  return data;
}

export async function decidePullRequest(
  repositoryId: string,
  prNumber: number,
  decision: PRDecisionRequest,
) {
  const { data } = await api.post<PullRequestApproval>(
    `/prs/${repositoryId}/${prNumber}/decision`,
    decision,
  );

  return data;
}
