export const queryKeys = {
  auth: {
    me: ["auth", "me"] as const,
  },
  repositories: {
    all: ["repositories"] as const,
    detail: (repositoryId: string) =>
      ["repositories", repositoryId] as const,
    workspace: (repositoryId: string) =>
      ["repositories", repositoryId, "workspace"] as const,
  },
  chat: {
    sessions: ["chat", "sessions"] as const,
    commands: ["chat", "commands"] as const,
    models: ["chat", "models"] as const,
    detail: (sessionId: string) => ["chat", "sessions", sessionId] as const,
  },
  pullRequests: {
    workspace: (repositoryId: string) =>
      ["pull-requests", repositoryId, "workspace"] as const,
    list: (repositoryId: string) =>
      ["pull-requests", repositoryId, "list"] as const,
    detail: (repositoryId: string, prNumber: number) =>
      ["pull-requests", repositoryId, prNumber] as const,
    review: (repositoryId: string, prNumber: number) =>
      ["pull-requests", repositoryId, prNumber, "review"] as const,
  },
  docs: {
    history: (repositoryId: string) =>
      ["docs", repositoryId, "history"] as const,
    topics: ["docs", "topics"] as const,
    detail: (docId: string) => ["docs", docId] as const,
  },
};
