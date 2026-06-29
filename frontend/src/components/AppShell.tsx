"use client";

import Link from "next/link";
import { Grid2X2, LogOut, UserCircle } from "lucide-react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { useAuth } from "@/lib/auth";
import { useRouter } from "next/navigation";
import axios from "axios";

type AppShellProps = {
  children: React.ReactNode;
  active?: "Dashboard" | "New Repository";
  searchPlaceholder?: string;
};

export default function AppShell({
  children,
  active = "Dashboard",
}: AppShellProps) {
  const { user, setUser } = useAuth();
  const router = useRouter();
  const profileImage = user?.avatar_url ?? user?.picture;
  const profileLabel =
    user?.display_name ?? user?.name ?? user?.email ?? "User profile";

  const handleLogout = async () => {
    try {
      await axios.post(
        `${process.env.NEXT_PUBLIC_BACKEND_URL}/auth/logout`,
        {},
        { withCredentials: true },
      );

      setUser(null);
      router.replace("/login");
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <main className="min-h-screen bg-[#050506] text-[#f4f0ff]">
      <header className="fixed inset-x-0 top-0 z-40 h-20 border-b border-[#32313f] bg-[#111115]">
        <div className="flex h-full items-center justify-between px-7">
          <div className="flex items-center gap-12">
            <Link
              href="/"
              className="font-display text-3xl font-bold text-[#cac4ff]"
            >
              CodeNova
            </Link>
            <nav className="hidden items-center gap-8 text-base text-[#ddd8ec] md:flex">
              <Link
                className={
                  active === "Dashboard"
                    ? "border-b-2 border-[#b8b2ff] text-white"
                    : ""
                }
                href="/dashboard"
              >
                Dashboard
              </Link>
              <Link
                className={
                  active === "New Repository"
                    ? "border-b-2 border-[#b8b2ff] text-white"
                    : ""
                }
                href="/ingestion"
              >
                New Repository
              </Link>
            </nav>
          </div>

          <div className="flex items-center gap-5">
            <Avatar
              size="lg"
              className="border border-[#444254] bg-[#101a1f]"
              title={profileLabel}
            >
              {profileImage ? (
                <AvatarImage src={profileImage} alt={profileLabel} />
              ) : null}
              <AvatarFallback className="bg-[#101a1f] text-[#63e7ff]">
                <UserCircle className="h-7 w-7" />
              </AvatarFallback>
            </Avatar>
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 rounded-lg border border-[#32313f] bg-[#151419] px-3 py-2 text-sm text-[#ddd8ec] transition-all hover:border-red-500/40 hover:bg-red-500/10 hover:text-red-200 cursor-pointer"
            >
              <LogOut className="h-4 w-4" />
              Logout
            </button>
          </div>
        </div>
      </header>

      <div className="pt-20 ">{children}</div>
    </main>
  );
}

export function MobileHint() {
  return (
    <div className="border-b border-[#32313f] bg-[#151419] px-5 py-3 text-sm text-[#aaa7b8] lg:hidden">
      <Grid2X2 className="mr-2 inline h-4 w-4" />
      Desktop navigation collapses on smaller screens; all core pages remain
      accessible through links.
    </div>
  );
}
