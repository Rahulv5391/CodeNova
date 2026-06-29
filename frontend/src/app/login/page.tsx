"use client";

import axios from "axios";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import {
  ArrowRight,
  GitBranch,
  KeyRound,
  LockKeyhole,
  Mail,
  Network,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useState } from "react";

const trustItems = [
  { label: "Graph", icon: Network },
  { label: "Secure", icon: ShieldCheck },
  { label: "Review", icon: KeyRound },
];

type AuthResponse = {
  access_token: string;
  token_type: string;
};

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL;

export default function LoginPage() {
  const router = useRouter();
  const { refreshUser } = useAuth();
  const [isSignup, setIsSignup] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  // For Email And Password
  async function handleSubmit(e: React.SubmitEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");

    if (!email.trim() || !password.trim()) {
      setError("Please enter your email and password.");
      return;
    }

    if (isSignup && !displayName.trim()) {
      setError("Please enter your display name.");
      return;
    }

    setIsSubmitting(true);

    try {
      if (!backendUrl) {
        setError("Backend URL is not configured.");
        return;
      }

      const endpoint = isSignup
        ? `${backendUrl}/auth/register`
        : `${backendUrl}/auth/login`;

      const { data } = await axios.post<AuthResponse>(
        endpoint,
        isSignup
          ? {
              email: email.trim(),
              password,
              display_name: displayName.trim(),
            }
          : {
              email: email.trim(),
              password,
            },
        {
          withCredentials: true,
        },
      );

      if (!data?.access_token) {
        setError(`${isSignup ? "Signup" : "Sign in"} failed. Token missing.`);
        return;
      }

      await refreshUser();
      router.push("/dashboard");
    } catch (err) {
      if (axios.isAxiosError(err)) {
        const detail = err.response?.data?.detail;
        const message = err.response?.data?.message;
        setError(
          detail ||
            message ||
            `${isSignup ? "Signup" : "Sign in"} failed. Please check your credentials.`,
        );
        return;
      }

      setError("Unable to reach the auth server. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }


  // For Login With Github
  async function loginWithGithub() {
  try {
    const { data } = await axios.get(
      `${backendUrl}/auth/github`
    );

    window.location.href = data.url;
  } catch {
    setError("Unable to start GitHub login.");
  }
}

  return (
    <main className="grid min-h-screen bg-[#050506] text-[#f4f0ff] lg:grid-cols-[1.1fr_0.9fr]">
      <section className="relative hidden overflow-hidden border-r border-[#32313f] bg-[#0d0d12] p-12 lg:block">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_22%_15%,rgba(126,121,255,0.26),transparent_28%),radial-gradient(circle_at_72%_42%,rgba(28,214,231,0.16),transparent_30%)]" />
        <div className="relative z-10 flex h-full flex-col justify-between">
          <Link
            href="/"
            className="font-display text-3xl font-bold text-[#cac4ff]"
          >
            CodeNova
          </Link>

          <div>
            <div className="mb-8 inline-flex items-center gap-2 rounded-full border border-[#444254] bg-[#151419] px-4 py-2 text-sm text-[#d8d4e6]">
              <Sparkles className="h-4 w-4 text-[#63e7ff]" />
              AI Codebase Navigator and PR Reviewer
            </div>
            <h1 className="font-display max-w-2xl text-6xl font-bold leading-[1.02] text-white">
              Sign in to explore repositories with context.
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-8 text-[#c9c5d8]">
              Connect GitHub, index a branch, inspect the file tree, ask
              questions, and generate review-ready summaries for every pull
              request.
            </p>
          </div>

          <div className="grid max-w-2xl grid-cols-3 gap-4">
            {trustItems.map(({ label, icon: Icon }) => (
              <div
                key={label}
                className="rounded-md border border-[#32313f] bg-[#111115]/80 p-5"
              >
                <Icon className="h-7 w-7 text-[#63e7ff]" />
                <p className="font-display mt-4 text-lg font-bold">{label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="flex items-center justify-center px-5 py-10">
        <div className="w-full max-w-md">
          <Link
            href="/"
            className="font-display text-3xl font-bold text-[#cac4ff] lg:hidden"
          >
            CodeNova
          </Link>
          <div className="mt-8 rounded-md border border-[#32313f] bg-[#111115] p-7 shadow-[0_28px_80px_rgba(0,0,0,0.38)] sm:p-9 lg:mt-0">
            <h2 className="font-display text-3xl font-bold text-white">
              {isSignup ? "Create your account" : "Welcome back"}
            </h2>
            <p className="mt-2 text-[#aaa7b8]">
              Use GitHub or your email to continue.
            </p>

            <button
              type="button"
              className="mt-7 flex h-12 w-full items-center justify-center gap-3 rounded-md border border-[#444254] bg-[#0b0b0f] font-semibold text-white transition hover:border-[#b8b2ff] cursor-pointer"
              onClick={loginWithGithub}
            >
              <GitBranch className="h-5 w-5 " />
              Continue with GitHub
            </button>

            <div className="my-7 flex items-center gap-4 text-xs uppercase tracking-[0.16em] text-[#777381]">
              <span className="h-px flex-1 bg-[#32313f]" />
              or
              <span className="h-px flex-1 bg-[#32313f]" />
            </div>

            {/* Form for Login using Email or Github */}
            <form className="grid gap-5" onSubmit={handleSubmit}>
              <div
                className={`grid transition-all duration-300 ease-out ${
                  isSignup
                    ? "grid-rows-[1fr] opacity-100"
                    : "grid-rows-[0fr] opacity-0"
                }`}
              >
                <label className="grid min-h-0 gap-2 overflow-hidden">
                  <span className="text-sm text-[#d8d4e6]">Display Name</span>
                  <div className="flex h-12 items-center gap-3 rounded-md border border-[#444254] bg-[#0b0b0f] px-4">
                    <KeyRound className="h-5 w-5 text-[#8f8b9c]" />
                    <input
                      className="w-full bg-transparent outline-none placeholder:text-[#777381]"
                      placeholder="John Doe"
                      value={displayName}
                      onChange={(e) => setDisplayName(e.target.value)}
                    />
                  </div>
                </label>
              </div>

              <label className="grid gap-2">
                <span className="text-sm text-[#d8d4e6]">Email</span>
                <div className="flex h-12 items-center gap-3 rounded-md border border-[#444254] bg-[#0b0b0f] px-4">
                  <Mail className="h-5 w-5 text-[#8f8b9c]" />
                  <input
                    className="w-full bg-transparent outline-none placeholder:text-[#777381]"
                    placeholder="john@google.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </div>
              </label>
              <label className="grid gap-2">
                <span className="text-sm text-[#d8d4e6]">Password</span>
                <div className="flex h-12 items-center gap-3 rounded-md border border-[#444254] bg-[#0b0b0f] px-4">
                  <LockKeyhole className="h-5 w-5 text-[#8f8b9c]" />
                  <input
                    className="w-full bg-transparent outline-none placeholder:text-[#777381]"
                    placeholder="Password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    type="password"
                  />
                </div>
              </label>
              <div className="flex items-center justify-between text-sm text-[#aaa7b8]">
                <label className="flex items-center gap-2">
                  <input type="checkbox" className="h-4 w-4 accent-[#827dff]" />
                  Remember me
                </label>
                <button
                  className="text-[#c5c1ff] cursor-pointer"
                  type="button"
                  onClick={() => {
                    setError("");
                    setIsSignup((current) => !current);
                  }}
                >
                  {isSignup
                    ? "Already have an account? Sign in"
                    : "Don't have account? Signup"}
                </button>
              </div>

              {error ? (
                <p className="rounded-md border border-[#6b2936] bg-[#2a1016] px-4 py-3 text-sm text-[#ffb6c0]">
                  {error}
                </p>
              ) : null}

              <button
                className="flex h-12 items-center justify-center gap-2 rounded-md bg-[#bbb7ff] font-bold text-[#0b08a8] cursor-pointer disabled:cursor-not-allowed disabled:opacity-70"
                disabled={isSubmitting}
              >
                {isSubmitting
                  ? isSignup
                    ? "Creating account..."
                    : "Signing in..."
                  : isSignup
                    ? "Sign up"
                    : "Sign in"}
                <ArrowRight className="h-5 w-5" />
              </button>
            </form>
          </div>
        </div>
      </section>
    </main>
  );
}
