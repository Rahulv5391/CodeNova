"use client";

import axios from "axios";
import { queryKeys } from "@/lib/query-keys";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
} from "react";

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL;

export type AuthUser = {
  id?: string | number;
  email?: string;
  display_name?: string;
  name?: string;
  avatar_url?: string;
  picture?: string;
};

type AuthContextValue = {
  user: AuthUser | null;
  isLoading: boolean;
  refreshUser: () => Promise<void>;
  setUser: (user: AuthUser | null) => void;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function normalizeUser(data: unknown): AuthUser | null {
  if (!data || typeof data !== "object") {
    return null;
  }

  const record = data as Record<string, unknown>;
  const nestedUser = record.user;

  if (nestedUser && typeof nestedUser === "object") {
    return normalizeUser(nestedUser);
  }

  return {
    id: record.id as AuthUser["id"],
    email: record.email as string | undefined,
    display_name:
      (record.display_name as string | undefined) ??
      (record.displayName as string | undefined) ??
      (record.username as string | undefined),
    name: record.name as string | undefined,
    avatar_url:
      (record.avatar_url as string | undefined) ??
      (record.avatarUrl as string | undefined) ??
      (record.picture as string | undefined) ??
      (record.image as string | undefined),
    picture: record.picture as string | undefined,
  };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();

  const userQuery = useQuery({
    queryKey: queryKeys.auth.me,
    queryFn: async () => {
      if (!backendUrl) {
        return null;
      }

      const { data } = await axios.get(`${backendUrl}/auth/me`, {
        withCredentials: true,
      });

      return normalizeUser(data);
    },
    retry: false,
  });
  const {
    data: user,
    isError,
    isLoading,
    refetch: refetchUser,
  } = userQuery;

  const refreshUser = useCallback(async () => {
    const result = await refetchUser();

    if (result.isError) {
      queryClient.setQueryData(queryKeys.auth.me, null);
    }
  }, [queryClient, refetchUser]);

  const setUser = useCallback(
    (user: AuthUser | null) => {
      queryClient.setQueryData(queryKeys.auth.me, user);
    },
    [queryClient],
  );

  useEffect(() => {
    if (isError) {
      queryClient.setQueryData(queryKeys.auth.me, null);
    }
  }, [isError, queryClient]);

  const value = useMemo(
    () => ({
      user: user ?? null,
      isLoading,
      refreshUser,
      setUser,
    }),
    [isLoading, refreshUser, setUser, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }

  return context;
}
