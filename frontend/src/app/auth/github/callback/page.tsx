"use client";

import axios from "axios";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/lib/auth";

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL;

function GithubCallbackContent() {
  const router = useRouter();
  const params = useSearchParams();
  const { refreshUser } = useAuth();

  useEffect(() => {
    async function finishLogin() {
      const code = params.get("code");

      if (!code) {
        router.push("/login");
        return;
      }

      try {
        await axios.get(`${backendUrl}/auth/github/callback`, {
          params: { code },
          withCredentials: true,
        });

        await refreshUser();
        router.replace("/dashboard");
      } catch {
        router.replace("/login");
      }
    }

    finishLogin();
  }, [params, refreshUser, router]);

  return <GithubCallbackLoading />;
}

function GithubCallbackLoading() {
  return (
  <div className="flex min-h-screen items-center justify-center">
    <div className="flex flex-col items-center gap-4">
      <Loader2 className="h-10 w-10 animate-spin" />

      <div className="text-center">
        <h2 className="text-xl font-semibold">
          Completing GitHub Sign In
        </h2>
        <p className="text-muted-foreground">
          This will only take a few seconds...
        </p>
      </div>
    </div>
  </div>
);
}

export default function GithubCallback() {
  return (
    <Suspense fallback={<GithubCallbackLoading />}>
      <GithubCallbackContent />
    </Suspense>
  );
}
