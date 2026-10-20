"use client";

import { AlertTriangle, CheckCircle2, Clock, Loader2, PauseCircle } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ResultsTable } from "@/components/ResultsTable";
import { PageTitle } from "@/components/Shell";
import { Alert, Badge, Button, Card, CardHeader, Spinner, cn } from "@/components/ui";
import { api, type DigitalStatus, type SearchDetail } from "@/lib/api";
import { SEARCH_STATUS, STATUS, STATUS_ORDER, fmtDate, usd } from "@/lib/labels";

export default function SearchDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [s, setS] = useState<SearchDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());
  const [lastUpdate, setLastUpdate] = useState<number | null>(null);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const load = useCallback(() => api<SearchDetail>(`/api/searches/${id}`).then((d) => { setS(d); setLastUpdate(Date.now()); }).catch((e) => setError(e.message)), [id]);
  useEffect(() => { load(); }, [load]);
  const active = s && ["queued", "running"].includes(s.status);
  useEffect(() => {
    if (!active) return;
    const t = setInterval(load, 2500);
    return () => clearInterval(t);
  }, [active, load]);
  const fixed = useMemo(() => ({ search_id: id }), [id]);

  async function action(a: "pause" | "resume" | "cancel" | "rerun") {
    try {
      const r = await api<{ id: number }>(`/api/searches/${id}/${a}`, { method: "POST" });
      if (a === "rerun") router.push(`/searches/${r.id}`);
      else load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  if (!s) return error ? <Alert tone="error">{error}</Alert> : <Spinner />;
  const unitsDone = s.activity.units_done; // lotes com erro ainda em nova tentativa não contam como concluídos
  const discoveryPct = s.units.length ? (unitsDone / s.units.length) * 100 : 0;
  const verifyPct = s.total_to_verify ? (s.total_verified / s.total_to_verify) * 100 : s.status === "completed" ? 100 : 0;

  return (
    <>
      <PageTitle title={s.name} subtitle={<>Criada em {fmtDate(s.created_at)} · <Badge className={SEARCH_STATUS[s.status]?.badge}>{SEARCH_STATUS[s.status]?.label}</Badge></>}
        actions={<>
          {active && <Button variant="secondary" onClick={() => action("pause")}>Pausar</Button>}
          {["paused", "failed"].includes(s.status) && <Button onClick={() => action("resume")}>Retomar</Button>}
          {!["completed", "cancelled"].includes(s.status) && <Button variant="ghost" onClick={() => action("cancel")}>Cancelar</Button>}
          <Button variant="secondary" onClick={() => action("rerun")}>Executar novamente</Button>
        </>} />
      {error && <div className="mb-4"><Alert tone="error">{error}</Alert></div>}
      <ActivityBanner s={s} now={now} lastUpdate={lastUpdate} />
      {s.error_message && <div className="mb-4"><Alert tone="warning">{s.error_message}</Alert></div>}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="p-5 lg:col-span-2">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <div className="flex justify-between text-sm"><span className="font-medium">Descoberta de empresas</span><span className="tabular-nums text-neutral-400">{unitsDone}/{s.units.length} lotes</span></div>
              <div className="mt-2 h-2 rounded-full bg-neutral-800"><div className="h-2 rounded-full bg-brand-500 transition-all" style={{ width: `${discoveryPct}%` }} /></div>
              <p className="mt-2 text-sm text-neutral-400">{s.total_found} encontradas · {s.total_new} novas na base</p>
            </div>
            <div>
              <div className="flex justify-between text-sm"><span className="font-medium">Verificação de presença digital</span><span className="tabular-nums text-neutral-400">{s.total_verified}/{s.total_to_verify}</span></div>
              <div className="mt-2 h-2 rounded-full bg-neutral-800"><div className="h-2 rounded-full bg-green-500 transition-all" style={{ width: `${verifyPct}%` }} /></div>
              <p className="mt-2 text-sm text-neutral-400">Custo: {usd(s.actual_cost_usd)} (estimado {usd(s.estimated_cost_usd)})</p>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {STATUS_ORDER.map((k) => (
              <span key={k} className="inline-flex items-center gap-1.5 rounded-md bg-neutral-950 px-2 py-1 text-xs"><span className="h-2 w-2 rounded-full" style={{ background: STATUS[k as DigitalStatus].color }} />{STATUS[k as DigitalStatus].label}: <b>{s.status_counts[k] ?? 0}</b></span>
            ))}
          </div>
        </Card>
        <Card>
          <CardHeader title="Lotes" subtitle="Fonte × localização × segmento" />
          <ul className="max-h-48 divide-y divide-neutral-800 overflow-y-auto text-xs">
            {s.units.map((u) => (
              <li key={u.id} className="flex items-start justify-between gap-2 px-4 py-2">
                <span className="text-neutral-300">{u.source} · {u.category} · {[u.location.neighborhood, u.location.city, u.location.state].filter(Boolean).join(", ") || "coordenadas"}{u.status === "error" && u.last_error && <span className="block text-red-400">{u.last_error}</span>}</span>
                <span className={cn("whitespace-nowrap font-medium", u.status === "error" ? "text-red-400" : u.status === "done" ? "text-green-400" : u.status === "running" ? "text-blue-300" : "text-neutral-400")}>{UNIT_STATUS[u.status] ?? u.status} · {u.results_count}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <div className="mt-4"><ResultsTable fixed={fixed} autoRefreshMs={active ? 4000 : undefined} /></div>

      <Card className="mt-4">
        <CardHeader title="Registro de eventos e erros de integração" />
        <ul className="max-h-64 divide-y divide-neutral-800 overflow-y-auto text-sm">
          {s.events.length === 0 && <li className="px-5 py-3 text-neutral-400">Sem eventos.</li>}
          {s.events.map((e) => (
            <li key={e.id} className="flex gap-3 px-5 py-2">
              <span className="whitespace-nowrap text-xs text-neutral-500">{fmtDate(e.created_at)}</span>
              <span className={cn(e.level === "error" ? "text-red-400" : e.level === "warning" ? "text-yellow-400" : "text-neutral-300")}>{e.message}</span>
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}

const UNIT_STATUS: Record<string, string> = { pending: "aguardando", running: "buscando…", done: "concluído", error: "erro", skipped: "ignorado" };

function ActivityBanner({ s, now, lastUpdate }: { s: SearchDetail; now: number; lastUpdate: number | null }) {
  const a = s.activity;
  const busy = a.state === "searching" || a.state === "verifying" || a.state === "queued";
  const Icon = busy ? Loader2 : a.state === "waiting_retry" ? Clock : a.state === "paused" ? PauseCircle : a.state === "done" ? CheckCircle2 : AlertTriangle;
  const tone = a.state === "done" ? "border-brand-500/40 bg-brand-500/10 text-brand-300"
    : a.state === "failed" ? "border-red-500/40 bg-red-500/10 text-red-300"
    : a.state === "waiting_retry" || a.state === "paused" ? "border-yellow-500/40 bg-yellow-500/10 text-yellow-200"
    : "border-blue-500/40 bg-blue-500/10 text-blue-200";
  // Usa o relógio do servidor (o do computador pode estar errado): espera restante = alvo − hora do servidor − tempo desde a resposta.
  const secs = a.next_retry_at && a.server_time && lastUpdate
    ? Math.max(0, Math.round((new Date(a.next_retry_at).getTime() - new Date(a.server_time).getTime() - (now - lastUpdate)) / 1000))
    : null;
  const ago = lastUpdate ? Math.round((now - lastUpdate) / 1000) : null;
  return (
    <div className={cn("mb-4 flex flex-wrap items-center gap-3 rounded-xl border px-4 py-3", tone)}>
      <Icon className={cn("h-5 w-5 shrink-0", busy && "animate-spin")} />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium">{a.message}</div>
        <div className="mt-0.5 text-xs opacity-80">
          {secs !== null && `Próxima tentativa em ${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")} · `}
          {a.units_total > 0 && `Lotes concluídos: ${a.units_done}/${a.units_total} · `}
          {ago !== null && `atualizado há ${ago}s`}
          {(busy || a.state === "waiting_retry") && " · mantenha esta aba aberta"}
        </div>
      </div>
    </div>
  );
}
