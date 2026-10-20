"use client";

import type { DigitalStatus } from "@/lib/api";
import { STATUS } from "@/lib/labels";
import { Badge, cn } from "./ui";

export function StatusBadge({ status, short }: { status: DigitalStatus; short?: boolean }) {
  const s = STATUS[status] ?? STATUS.VERIFICACAO_PENDENTE;
  return (
    <Badge className={s.badge} title={s.hint}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: s.color }} />
      {short ? s.short : s.label}
    </Badge>
  );
}

export function Confidence({ value }: { value: number }) {
  const tone = value >= 75 ? "bg-green-500" : value >= 50 ? "bg-yellow-500" : value > 0 ? "bg-orange-500" : "bg-neutral-700";
  const label = value >= 75 ? "alta" : value >= 50 ? "média" : value > 0 ? "baixa" : "—";
  return (
    <div className="flex items-center gap-2" title={`Confiança ${label}: ${value}%`}>
      <div className="h-1.5 w-14 overflow-hidden rounded-full bg-neutral-800">
        <div className={cn("h-full", tone)} style={{ width: `${value}%` }} />
      </div>
      <span className="text-xs tabular-nums text-neutral-400">{value}%</span>
    </div>
  );
}

export function Score({ value }: { value: number }) {
  const tone = value >= 70 ? "bg-brand-500 text-black" : value >= 45 ? "bg-yellow-400 text-black" : "bg-neutral-800 text-neutral-300";
  return (
    <span title="Prioridade estimada para prospecção (não garante interesse)" className={cn("inline-flex h-7 w-9 items-center justify-center rounded-md text-xs font-bold tabular-nums", tone)}>
      {value}
    </span>
  );
}

export function FictitiousTag() {
  return <Badge className="bg-orange-500/15 text-orange-300 ring-orange-500/30" title="Registro fictício, apenas para demonstração">FICTÍCIO</Badge>;
}
