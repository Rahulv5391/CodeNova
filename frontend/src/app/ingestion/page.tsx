"use client";

import AppShell, { MobileHint } from "@/components/AppShell";
import axios from "axios";
import {
  BarChart3,
  Braces,
  FolderGit2,
  Globe2,
  Link2,
  Lock,
  Network,
  ScanSearch,
  ShieldCheck,
  WandSparkles,
  Zap,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

const stages = [
  {
    label: "Repository Cloning",
    icon: FolderGit2,
  },
  { label: "AST Extraction", icon: Braces },
  { label: "Embedding Gen", icon: ScanSearch },
  { label: "Knowledge Graph", icon: Network },
  {
    label: "Final Indexing",
    icon: ScanSearch,
  },
];

const benefits = [
  {
    icon: ShieldCheck,
    title: "Secure Analysis",
    body: "Code is analyzed in a sandboxed ephemeral environment and purged post-analysis.",
  },
  {
    icon: Zap,
    title: "Parallel Indexing",
    body: "AST trees are extracted in parallel using multi-core distributed workers.",
  },
  {
    icon: WandSparkles,
    title: "Graph Persistence",
    body: "Visual relationships between files and classes are saved for easy exploration.",
  },
];

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL;

export default function IngestionPage() {
  const router = useRouter();
  const [githubUrl, setGithubUrl] = useState("");
  const [branch, setBranch] = useState("main");
  const [visibility, setVisibility] = useState<"public" | "private">("public");
  const [githubAccessToken, setGithubAccessToken] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.SubmitEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");

    if (!backendUrl) {
      setError("Backend URL is not configured.");
      return;
    }

    if (!githubUrl.trim()) {
      setError("Please enter a GitHub repository URL.");
      return;
    }

    if (visibility === "private" && !githubAccessToken.trim()) {
      setError("Please enter a GitHub access token for private repositories.");
      return;
    }

    setIsSubmitting(true);

    try {
      const { data } = await axios.post(
        `${backendUrl}/repos`,
        {
          github_url: githubUrl.trim(),
          branch: branch.trim() || "main",
          github_access_token:
            visibility === "private" ? githubAccessToken.trim() : undefined,
        },
        { withCredentials: true },
      );

      router.push(`/repo/${data.repo.id}`);
    } catch (err) {
      if (axios.isAxiosError(err)) {
        setError(
          err.response?.data?.detail ||
            err.response?.data?.message ||
            "Repository ingestion failed.",
        );
        return;
      }

      setError("Unable to reach the ingestion service. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AppShell active="New Repository">
      <MobileHint />
      <section className="px-5 py-10 md:px-12 lg:px-20">
        <div className="mx-auto max-w-6xl">
          <div className="rounded-md border border-[#32313f] bg-[#111115] p-8 shadow-[0_28px_80px_rgba(0,0,0,0.38)] md:p-12">
            <h1 className="font-display text-4xl font-bold text-white md:text-5xl">
              Repository Ingestion
            </h1>
            <p className="mt-3 max-w-3xl text-xl leading-8 text-[#c9c5d8]">
              Synchronize your codebase with CodeNova to generate AST-backed
              embeddings and build a persistent knowledge graph of your
              architecture.
            </p>

            <form className="mt-10 grid gap-7" onSubmit={handleSubmit}>
              <label className="grid gap-2">
                <span className="text-md text-[#d8d4e6]">Repository URL</span>
                <div className="flex h-14 items-center gap-4 rounded-md border border-[#48475a] bg-[#0d0d12] px-5">
                  <Link2 className="h-5 w-5 text-[#d8d4e6]" />
                  <input
                    className="w-full bg-transparent font-mono text-lg text-[#d8d4e6] outline-none placeholder:text-[#858192]"
                    placeholder="https://github.com/org/repository"
                    value={githubUrl}
                    onChange={(e) => setGithubUrl(e.target.value)}
                  />
                </div>
              </label>

              <div className="grid gap-7 lg:grid-cols-[1fr_1fr]">
                <label className="grid gap-2">
                  <span className="text-md text-[#d8d4e6]">Target Branch</span>
                  <div className="flex h-14 items-center rounded-md border border-[#48475a] bg-[#0d0d12] px-5 text-xl">
                    <input
                      className="w-full bg-transparent text-[#d8d4e6] outline-none"
                      value={branch}
                      onChange={(e) => setBranch(e.target.value)}
                      placeholder="main"
                    />
                  </div>
                </label>
                <div className="grid gap-2">
                  <span className="text-sm text-[#d8d4e6]">
                    Visibility Status
                  </span>
                  <div className="grid gap-5 sm:grid-cols-2">
                    <button
                      type="button"
                      onClick={() => setVisibility("public")}
                      className={`flex h-14 items-center justify-center gap-3 rounded-md text-xl font-bold cursor-pointer hover:outline-2 ${
                        visibility === "public"
                          ? "bg-[#827dff] text-[#15115d]"
                          : "border border-[#48475a] bg-[#0d0d12] text-[#d8d4e6]"
                      }`}
                    >
                      <Globe2 className="h-5 w-5" />
                      Public
                    </button>
                    <button
                      type="button"
                      onClick={() => setVisibility("private")}
                      className={`flex h-14 items-center justify-center gap-3 rounded-md text-xl font-bold cursor-pointer hover:outline-2 ${
                        visibility === "private"
                          ? "bg-[#827dff] text-[#15115d]"
                          : "border border-[#48475a] bg-[#0d0d12] text-[#d8d4e6]"
                      }`}
                    >
                      <Lock className="h-5 w-5" />
                      Private
                    </button>
                  </div>
                </div>
              </div>

              {visibility === "private" && (
                <label className="grid gap-2">
                  <span className="text-md text-[#d8d4e6]">
                    GitHub Access Token
                  </span>
                  <div className="flex h-14 items-center gap-4 rounded-md border border-[#48475a] bg-[#0d0d12] px-5">
                    <Lock className="h-5 w-5 text-[#d8d4e6]" />
                    <input
                      className="w-full bg-transparent font-mono text-lg text-[#d8d4e6] outline-none placeholder:text-[#858192]"
                      type="password"
                      placeholder="github_pat_..."
                      value={githubAccessToken}
                      onChange={(e) => setGithubAccessToken(e.target.value)}
                      autoComplete="off"
                    />
                  </div>
                </label>
              )}

              {error && (
                <p className="rounded-md border border-[#6e2635] bg-[#220b12] px-4 py-3 text-sm text-[#ffb7c4]">
                  {error}
                </p>
              )}

              <button
                className="mt-4 flex h-16 items-center justify-center gap-4 cursor-pointer rounded-md bg-[#bbb7ff] font-bold uppercase tracking-[0.12em] text-[#0b08a8] shadow-[0_16px_36px_rgba(126,121,255,0.18)] disabled:cursor-not-allowed disabled:opacity-60 hover:bg-[#918dc1] transition-all ease-in"
                disabled={isSubmitting}
              >
                <BarChart3 className="h-6 w-6" />
                {isSubmitting ? "Starting..." : "Start Analysis"}
              </button>
            </form>
          </div>

          <div className="mt-12 rounded-md border border-[#32313f] bg-[#111115] p-8 md:p-10">
            <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
              <h2 className="font-display text-3xl font-bold text-white">
                Ingestion Pipeline
              </h2>
            </div>

            <div className="mt-10 grid gap-6 lg:grid-cols-5 lg:gap-0">
              {stages.map((stage, index) => {
                const Icon = stage.icon;
                return (
                  <div key={stage.label} className="relative text-center">
                    {index < stages.length - 1 && (
                      <div className="absolute left-1/2 top-8 hidden h-px w-full bg-[#4a4858] lg:block" />
                    )}
                    <div
                      className={
                        "relative z-10 mx-auto grid h-16 w-16 place-items-center rounded-full border-4 border-[#474367] bg-[#827dff] text-[#15115d]"
                      }
                    >
                      {Icon ? (
                        <Icon className="h-7 w-7" />
                      ) : (
                        <span className="font-semibold">75%</span>
                      )}
                    </div>
                    <h3 className="font-display mt-4 text-base font-bold text-white">
                      {stage.label}
                    </h3>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="mt-12 grid gap-5 lg:grid-cols-3">
            {benefits.map((benefit) => (
              <article
                key={benefit.title}
                className="rounded-md border border-[#32313f] bg-[#111115] p-7"
              >
                <benefit.icon className="h-8 w-8 text-[#63e7ff]" />
                <h3 className="font-display mt-5 text-lg font-bold text-white">
                  {benefit.title}
                </h3>
                <p className="mt-2 leading-6 text-[#c9c5d8]">{benefit.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>
    </AppShell>
  );
}
