"use client";

import { useCallback, useEffect, useRef } from "react";
import RepositoryCard from "./RepositoryCard";
import { Repository, RepositoryStatus } from "@/types/repo";
import { queryKeys } from "@/lib/query-keys";
import { useQuery, useQueryClient } from "@tanstack/react-query";

type Props = {
  initialRepos: Repository[];
};

const terminalStates: RepositoryStatus[] = ["ready", "failed"];
const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL;

export default function RepositoriesList({ initialRepos }: Props) {
  const queryClient = useQueryClient();
  const eventSourcesRef = useRef<Record<string, EventSource>>({});
  const { data: repos = [] } = useQuery({
    queryKey: queryKeys.repositories.all,
    queryFn: async () => initialRepos,
    initialData: initialRepos,
    staleTime: 1000 * 60,
  });

  const updateRepoInCache = useCallback((updatedRepo: Repository) => {
    queryClient.setQueryData<Repository[]>(queryKeys.repositories.all, (current = []) =>
      current.map((repo) =>
        repo.id === updatedRepo.id
          ? {
              ...repo,
              ...updatedRepo,
            }
          : repo,
      ),
    );
  }, [queryClient]);

  useEffect(() => {
    if (!backendUrl) {
      return;
    }

    const repoIds = new Set(repos.map((repo) => repo.id));

    Object.entries(eventSourcesRef.current).forEach(([repoId, es]) => {
      if (!repoIds.has(repoId)) {
        es.close();
        delete eventSourcesRef.current[repoId];
      }
    });

    repos.forEach((repo) => {
      const existingStream = eventSourcesRef.current[repo.id];

      if (terminalStates.includes(repo.status)) {
        if (existingStream) {
          existingStream.close();
          delete eventSourcesRef.current[repo.id];
        }
        return;
      }

      if (existingStream) {
        return;
      }

      const es = new EventSource(
        `${backendUrl}/repos/${repo.id}/status/stream`,
        {
          withCredentials: true,
        },
      );

      eventSourcesRef.current[repo.id] = es;

      es.onmessage = (event) => {
        const payload = JSON.parse(event.data);

        if (!payload.repo) return;

        updateRepoInCache(payload.repo);

        if (
          payload.type === "done" ||
          terminalStates.includes(payload.repo.status)
        ) {
          es.close();
          delete eventSourcesRef.current[repo.id];
        }
      };

      es.onerror = () => {
        es.close();
        delete eventSourcesRef.current[repo.id];
      };
    });
  }, [repos, updateRepoInCache]);

  useEffect(() => {
    return () => {
      Object.values(eventSourcesRef.current).forEach((es) => es.close());
      eventSourcesRef.current = {};
    };
  }, []);

  return (
    <div className="mt-12 grid gap-5">
      {repos.map((repo, index) => (
        <RepositoryCard
          key={repo.id}
          repo={repo}
          index={index}
          onDelete={(id) =>
            queryClient.setQueryData<Repository[]>(
              queryKeys.repositories.all,
              (current = []) => current.filter((repo) => repo.id !== id),
            )
          }
          onUpdate={updateRepoInCache}
        />
      ))}
    </div>
  );
}
