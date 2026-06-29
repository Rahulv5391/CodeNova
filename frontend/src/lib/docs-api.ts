import { api } from "@/lib/api";
import { getPillarIcon } from "@/utils/docs";
import { DocDetail, DocHistoryItem, DocTopics, Pillar } from "@/types/doc";

export async function getDocsHistory(repositoryId: string) {
  const { data } = await api.get<DocHistoryItem[]>("/docs", {
    params: {
      repository_id: repositoryId,
    },
  });

  return data;
}

export async function getDocTopics() {
  const { data } = await api.get<DocTopics[]>("/docs/topics");

  return data.map<Pillar>((topic) => ({
    ...topic,
    icon: getPillarIcon(topic.id),
  }));
}

export async function generateDocumentation({
  repositoryId,
  topics,
  userContext,
  format,
}: {
  repositoryId: string;
  topics: string[];
  userContext: string;
  format: "Markdown" | "JSON";
}) {
  const { data } = await api.post(`/docs/generate/${repositoryId}`, {
    topics,
    user_context: userContext,
    format,
  });

  return data;
}

export async function getDocDetail(docId: string) {
  const { data } = await api.get<DocDetail>(`/docs/${docId}`);

  return data;
}
