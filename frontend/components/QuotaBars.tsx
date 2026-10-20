"use client";

import type { QuotaUsage } from "@/lib/api";
import { cn } from "./ui";

export function QuotaBars({ quotas, compact }: { quotas: QuotaUsage[]; compact?: boolean }) {
  return (
    <div className={cn("grid gap-3", compact ? "sm:grid-cols-3" : "")}>
      {quotas.map((q) => {
        const pct = q.effective_limit ? Math.min(100, (q.used / q.effective_limit) * 100) : 0;
        const tone = pct >= 100 ? "bg-red-500" : pct >= 80 ? "bg-yellow-400" : "bg-brand-500";
        return (
          <div key={q.provider} className="text-sm">
            <div className="flex justify-between gap-2">
              <span className="text-neutral-300">{q.label}</span>
              <span className="tabular-nums text-neutral-400">
                {q.used} / {q.effective_limit} {q.period === "month" ? "no mês" : "hoje"}
              </span>
            </div>
            <div className="mt-1.5 h-2 rounded-full bg-neutral-800">
              <div className={cn("h-2 rounded-full transition-all", tone)} style={{ width: `${pct}%` }} />
            </div>
            {!compact && (
              <p className="mt-1 text-xs text-neutral-500">
                Cota grátis do provedor: {q.free_limit}/{q.period === "month" ? "mês" : "dia"} · o sistema usa até {q.effective_limit} (margem de segurança)
                {q.enforced ? " e para sozinho ao atingir." : " — modo gratuito desligado: apenas contando."}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
