"use client";

import { BarChart3, Building2, LogOut, Map, Menu, Search, Settings, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type User } from "@/lib/api";
import { cn, Spinner } from "./ui";

const UserCtx = createContext<User | null>(null);
export const useUser = () => useContext(UserCtx);

const NAV = [
  { href: "/", label: "Painel", icon: BarChart3 },
  { href: "/searches", label: "Pesquisas", icon: Search },
  { href: "/leads", label: "Resultados / Leads", icon: Building2 },
  { href: "/map", label: "Mapa", icon: Map },
  { href: "/settings", label: "Configurações", icon: Settings },
];

export function Shell({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    api<User>("/api/auth/me").then(setUser).catch(() => router.replace("/login"));
  }, [router]);

  if (!user) return <Spinner label="Verificando sessão..." />;

  const nav = (
    <nav className="flex flex-1 flex-col gap-1 p-3">
      {NAV.map((n) => {
        const active = n.href === "/" ? pathname === "/" : pathname.startsWith(n.href);
        return (
          <Link key={n.href} href={n.href} onClick={() => setOpen(false)}
            className={cn("flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium", active ? "bg-brand-600 text-white" : "text-gray-300 hover:bg-white/10 hover:text-white")}>
            <n.icon className="h-4 w-4" /> {n.label}
          </Link>
        );
      })}
    </nav>
  );

  async function logout() {
    await api("/api/auth/logout", { method: "POST" });
    router.replace("/login");
  }

  return (
    <UserCtx.Provider value={user}>
      <div className="flex min-h-screen">
        <aside className={cn("fixed inset-y-0 left-0 z-40 flex w-60 flex-col bg-brand-900 transition-transform lg:translate-x-0", open ? "translate-x-0" : "-translate-x-full")}>
          <div className="flex items-center justify-between px-5 py-5">
            <Link href="/" className="text-lg font-bold text-white">Prospec<span className="text-brand-100">IA</span></Link>
            <button className="text-gray-300 lg:hidden" onClick={() => setOpen(false)} aria-label="Fechar menu"><X className="h-5 w-5" /></button>
          </div>
          {nav}
          <div className="border-t border-white/10 p-4 text-xs text-gray-300">
            <div className="truncate font-medium text-white">{user.name}</div>
            <div className="truncate">{user.email} · {user.role}</div>
            <button onClick={logout} className="mt-3 inline-flex items-center gap-2 text-gray-300 hover:text-white"><LogOut className="h-3.5 w-3.5" /> Sair</button>
          </div>
        </aside>
        <div className="flex min-w-0 flex-1 flex-col lg:pl-60">
          <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-gray-200 bg-white/90 px-4 py-3 backdrop-blur lg:hidden">
            <button onClick={() => setOpen(true)} aria-label="Abrir menu"><Menu className="h-5 w-5" /></button>
            <span className="font-semibold">ProspecIA</span>
          </header>
          <main className="mx-auto w-full max-w-[1500px] flex-1 p-4 sm:p-6">{children}</main>
        </div>
      </div>
    </UserCtx.Provider>
  );
}

export function PageTitle({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-gray-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-gray-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}
