import Link from "next/link";
import {
  ArrowRight,
  Bot,
  Braces,
  FileText,
  GitBranch,
  MessageSquare,
  Network,
  ShieldCheck,
  Workflow,
} from "lucide-react";

const tools = [
  {
    icon: Workflow,
    title: "Architecture Visualization",
    body: "Map dependencies, data flow, and service relationships in a high-fidelity workspace.",
  },
  {
    icon: MessageSquare,
    title: "AI Repository Chat",
    body: "Ask precise questions across your codebase, from auth logic to deployment scripts.",
  },
  {
    icon: Network,
    title: "Knowledge Graph",
    body: "Connect symbols, files, pull requests, and docs with semantic indexing.",
  },
  {
    icon: FileText,
    title: "PR Review Briefs",
    body: "Generate review notes, risk summaries, and implementation context for every branch.",
  },
];

export default function Home() {
  return (
    <main className="min-h-screen bg-[#050506] text-[#f4f0ff]">
      <section className="relative overflow-hidden border-b border-[#171720]">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5 mt-4">
          <Link
            href="/"
            className="font-display text-4xl font-bold text-[#cac4ff]"
          >
            CodeNova
          </Link>
          <nav className="hidden items-center gap-8 text-sm text-[#d8d4e6] md:flex"></nav>
          <div className="flex items-center gap-3">
            <Link
              href="/login"
              className="rounded-md  border-[#434155] border-2 px-4 py-2 text-xl text-[#f4f0ff] transition hover:border-[#b8b2ff] px-10"
            >
              Sign in
            </Link>
          </div>
        </div>

        <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(circle_at_30%_20%,rgba(126,121,255,0.22),transparent_26%),radial-gradient(circle_at_72%_16%,rgba(28,214,231,0.15),transparent_28%)]" />
        <div className="relative mx-auto grid max-w-7xl gap-12 px-5 pb-20 pt-20 lg:pt-24">
          <div className="mx-auto max-w-4xl text-center">
            <h1 className="font-display mt-7 text-5xl font-bold leading-[1.02] tracking-normal text-white md:text-7xl">
              Understand Any Codebase
              <span className="block text-[#c5c1ff]">in Minutes</span>
            </h1>
            <p className="mx-auto mt-6 max-w-2xl text-xl leading-7 text-[#c9c5d8]">
              Connect a GitHub repository, generate architecture graphs, build a
              code knowledge base, chat with your code, and review pull requests
              with AI.
            </p>
            <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
              <Link
                href="/login"
                className="inline-flex items-center justify-center gap-2 rounded-md bg-[#bbb7ff] px-6 py-3 text-sm font-semibold text-[#0b08a8] shadow-[0_12px_30px_rgba(126,121,255,0.25)]"
              >
                Analyze Repository
                <ArrowRight className="h-4 w-4" />
              </Link>
              <Link
                target="_blank"
                href="https://www.google.com"
                className="inline-flex items-center justify-center rounded-md border border-[#49475b] px-6 py-3 text-sm text-white"
              >
                View Demo
              </Link>
            </div>
          </div>

          <div className="mx-auto w-full max-w-6xl overflow-hidden rounded-md border border-[#444254] bg-[#0b0b0f] shadow-[0_35px_100px_rgba(0,0,0,0.52)]">
            <div className="flex h-8 items-center gap-2 border-b border-[#33313f] bg-[#1b1a20] px-4">
              <span className="h-2.5 w-2.5 rounded-full bg-[#ffad7c]" />
              <span className="h-2.5 w-2.5 rounded-full bg-[#f1c96f]" />
              <span className="h-2.5 w-2.5 rounded-full bg-[#69d2d7]" />
            </div>
            <div className="grid min-h-102.5 bg-[linear-gradient(110deg,rgba(14,214,231,0.12),transparent_42%),linear-gradient(160deg,#090b10,#050506)] lg:grid-cols-[1fr_320px]">
              <div className="relative nexus-grid p-8">
                <div className="absolute left-[12%] top-[18%] w-72 rotate-[-12deg] rounded-md border border-[#12d9f0]/60 bg-[#111922]/92 p-4 shadow-[0_0_40px_rgba(18,217,240,0.22)]">
                  <div className="mb-3 h-2 w-24 rounded bg-[#12d9f0]" />
                  {[
                    "src/app/api/auth.ts",
                    "components/reviewer.tsx",
                    "lib/github.ts",
                    "routes/webhook.ts",
                  ].map((item) => (
                    <div
                      key={item}
                      className="mb-2 rounded bg-white/5 px-3 py-2 font-mono text-xs text-[#dbe9ff]"
                    >
                      {item}
                    </div>
                  ))}
                </div>
                <div className="absolute bottom-8 left-10 rounded-md border border-[#12d9f0] bg-[#07161b] px-4 py-3">
                  <p className="text-xs font-semibold text-[#63e7ff]">
                    Architecture Summary
                  </p>
                  <div className="mt-2 h-2 w-28 rounded bg-[#12d9f0]/70" />
                </div>
              </div>
              <div className="m-8 self-center rounded-md border border-[#32313f] bg-[#0c0c11]/95 p-4">
                <div className="mb-4 flex items-center gap-2 text-sm font-semibold">
                  <Bot className="h-4 w-4 text-[#b8b2ff]" />
                  CodeNova Assistant
                </div>
                <p className="rounded-md bg-[#24232a] p-3 text-sm leading-6 text-white">
                  The authentication logic is handled in{" "}
                  <span className="font-mono text-[#63e7ff]">
                    auth/session.ts{" "}
                  </span>
                  and protected by a token validation strategy.
                </p>
                <div className="mt-5 flex items-center gap-2 rounded border border-[#444254] px-3 py-2 text-xs text-[#aaa7b8]">
                  Ask a question...
                  <ArrowRight className="ml-auto h-4 w-4 text-[#b8b2ff]" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-16 text-center">
        <p className="text-xs uppercase tracking-[0.24em] text-[#8a8796]">
          Powering engineering teams at
        </p>
        <div className="mt-7 flex flex-wrap justify-center gap-8 font-display text-lg font-bold text-[#777381]">
          <span>NEBULA</span>
          <span>VERTEX</span>
          <span>QUANTUM</span>
          <span>SYNAPSE</span>
          <span>ORBITAL</span>
        </div>
      </section>

      <section id="features" className="mx-auto max-w-7xl px-5 py-12">
        <div className="text-center">
          <h2 className="font-display text-3xl font-bold text-white">
            Tools for Modern Architects
          </h2>
          <p className="mt-3 text-md text-[#aaa7b8]">
            Everything needed to master complex legacy systems and ship faster.
          </p>
        </div>
        <div className="mt-10 grid gap-4 md:grid-cols-2">
          {tools.map((tool, index) => (
            <article
              key={tool.title}
              className={`nexus-panel rounded-md p-8 ${index === 0 || index === 3 ? "md:col-span-1" : ""}`}
            >
              <tool.icon className="h-8 w-8 text-[#63e7ff]" />
              <h3 className="font-display mt-6 text-xl font-bold text-white">
                {tool.title}
              </h3>
              <p className="mt-3 max-w-xl text-md leading-6 text-[#c9c5d8]">
                {tool.body}
              </p>
            </article>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-16">
        <div className="nexus-panel rounded-md bg-[radial-gradient(circle_at_80%_40%,rgba(126,121,255,0.14),transparent_28%),#09090d] px-6 py-16 text-center">
          <ShieldCheck className="mx-auto h-8 w-8 text-[#63e7ff]" />
          <h2 className="font-display mt-5 text-4xl font-bold text-white">
            Ready to decode complexity?
          </h2>
          <p className="mt-3 text-lg text-[#c9c5d8]">
            Join teams using CodeNova to manage their codebase knowledge.
          </p>
          <Link
            href="/login"
            className="mt-8 inline-flex rounded-md bg-[#bbb7ff] px-7 py-3 text-md font-semibold text-[#0b08a8]"
          >
            Analyze Your First Repository
          </Link>
        </div>
      </section>

      <footer className="border-t border-[#282735] bg-[#111115]">
        <div className="mx-auto grid max-w-7xl gap-10 px-5 py-14 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
          <div>
            <h3 className="font-display text-xl font-bold text-[#cac4ff]">
              CodeNova
            </h3>
            <p className="mt-3 max-w-sm text-md leading-6 text-[#aaa7b8]">
              Built under the guidance of Lakshit Wasan
            </p>
            <div className="mt-5 flex gap-3 text-[#c9c5d8]">
              <GitBranch className="h-5 w-5" />
              <Braces className="h-5 w-5" />
              <GitBranch className="h-5 w-5" />
            </div>
          </div>
          {["Product", "Company", "Support"].map((heading) => (
            <div key={heading}>
              <h4 className="text-xs uppercase tracking-[0.18em] text-[#8a8796]">
                {heading}
              </h4>
              <div className="mt-4 grid gap-3 text-sm text-[#d8d4e6]">
                <Link href="https://nebula9.ai/" target="_blank">
                  Website
                </Link>
                <Link
                  href="https://www.linkedin.com/company/nebula9"
                  target="_blank"
                >
                  Linkedin
                </Link>
                <Link href="/ingestion">Integrations</Link>
              </div>
            </div>
          ))}
        </div>
      </footer>
    </main>
  );
}
