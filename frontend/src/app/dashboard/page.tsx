import Link from "next/link";
import AppShell, { MobileHint } from "@/components/AppShell";
import { Repository } from "@/types/repo";
import { getRepos } from "./actions";

import { Filter, PlusCircle } from "lucide-react";
import DashboardMetrics from "./DashboardMetrics";
import RepositoriesList from "./RepositoriesList";


export default async function DashboardPage() {
  const repos: Repository[] = await getRepos();

  return (
    <AppShell active="Dashboard">
      <MobileHint />
      <section className="px-5 py-10 md:px-12 lg:px-14">
        <div className="flex flex-col justify-between gap-6 xl:flex-row xl:items-end">
          <div>
            <h1 className="font-display text-4xl font-bold text-white md:text-5xl max-w-screen">
              Your Repositories
            </h1>
            <p className="mt-3 text-lg text-[#c9c5d8]">
              Manage and analyze your codebase with high-performance AI tools.
            </p>
          </div>
          <div className="flex flex-col gap-4 sm:flex-row">
            <div className="flex h-12 min-w-[320px] items-center gap-3 rounded-md border border-[#444254] bg-[#1b1a20] px-4 text-[#8f8b9c]">
              <Filter className="h-5 w-5" />
              <input
                placeholder="Filter repositories..."
                className="outline-none"
              ></input>
            </div>
            <Link
              href="/ingestion"
              className="inline-flex h-12 items-center justify-center gap-3 rounded-md bg-[#bbb7ff] px-7 font-semibold text-[#0b08a8] shadow-[0_14px_34px_rgba(126,121,255,0.18)]"
            >
              <PlusCircle className="h-5 w-5" />
              Create New Repository
            </Link>
          </div>
        </div>

        <DashboardMetrics repos={repos} />

        <div className="mt-12 grid gap-5">

          <RepositoriesList initialRepos={repos} />

          {/* {repos.map((repo, index) => (
            <RespositoryCard key={index} repo={repo} index={index} />
          ))} */}
        </div>
      </section>
    </AppShell>
  );
}
