"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { PageTitle } from "@/components/Shell";
import { Alert, Button, Card, CardHeader, Spinner } from "@/components/ui";
import { QuotaBars } from "@/components/QuotaBars";
import { api, type Budget, type DigitalStatus, type QuotaUsage } from "@/lib/api";
import { LEAD_STATUS, STATUS, STATUS_ORDER, usd } from "@/lib/labels";

interface Dash {
  total: number;
  by_status: Record<DigitalStatus, number>;
  awaiting_verification: number;
  social_only: number;
  hot_leads: number;
  by_city: { city: string; count: number }[];
  by_category: { category: string; count: number }[];
  by_lead_status: Record<string, number>;
  active_searches: number;
  fictitious_count: number;
  budget: Budget;
  free_tier_only: boolean;
  quotas: QuotaUsage[];
}

function Kpi({ label, value, color, href, hint }: { label: string; value: number; color?: string; href?: string; hint?: string }) {
  const body = (
    <Card className="h-full p-4 transition hover:shadow-md">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-neutral-400" title={hint}>
        {color && <span className="h-2 w-2 rounded-full" style={{ background: color }} />}
        {label}
      </div>
      <div className="mt-2 text-3xl font-bold tabular-nums text-neutral-100">{value.toLocaleString("pt-BR")}</div>
    </Card>
  );
  return href ? <Link href={href}>{body}</Link> : body;
}

function Bars({ rows }: { rows: { label: string; count: number }[] }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  if (!rows.length) return <p className="px-5 py-6 text-sm text-neutral-400">Sem dados ainda.</p>;
  return (
    <ul className="space-y-2.5 px-5 py-4">
      {rows.map((r) => (
        <li key={r.label} className="text-sm">
          <div className="mb-1 flex justify-between gap-2"><span className="truncate text-neutral-300">{r.label}</span><span className="tabular-nums text-neutral-400">{r.count}</span></div>
          <div className="h-2 rounded-full bg-neutral-800"><div className="h-2 rounded-full bg-brand-500" style={{ width: `${(r.count / max) * 100}%` }} /></div>
        </li>
      ))}
    </ul>
  );
}

export default function Dashboard() {
  const [data, setData] = useState<Dash | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<Dash>("/api/dashboard").then(setData).catch((e) => setError(e.message));
  }, []);
  if (error) return <Alert tone="error">{error}</Alert>;
  if (!data) return <Spinner />;
  const b = data.budget;
  return (
    <>
      <PageTitle title="Painel" subtitle="Visão geral da base de empresas e da presença digital identificada."
        actions={<Link href="/searches/new"><Button>Nova pesquisa</Button></Link>} />
      {data.fictitious_count > 0 && (
        <div className="mb-4"><Alert tone="warning">A base contém <b>{data.fictitious_count}</b> registros <b>FICTÍCIOS</b> de demonstração (marcados na interface). Eles não são resultados reais de pesquisa.</Alert></div>
      )}
      {data.free_tier_only && (
        <Card className="mb-4 p-4">
          <div className="mb-3 flex items-center justify-between gap-2">
            <span className="text-sm font-medium text-neutral-100">Modo gratuito: cotas grátis usadas</span>
            <Link href="/settings" className="text-xs text-brand-400 hover:underline">detalhes</Link>
          </div>
          <QuotaBars quotas={data.quotas} compact />
        </Card>
      )}
      {!data.free_tier_only && b.level !== "ok" && (
        <div className="mb-4"><Alert tone={b.level === "exceeded" ? "error" : "warning"}>Consumo do mês: {usd(b.spent_usd)} de {usd(b.monthly_budget_usd)} ({b.percent}%). {b.level === "exceeded" ? "Limite atingido: novas pesquisas estão bloqueadas." : "Você está próximo do limite mensal."}</Alert></div>
      )}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
        <Kpi label="Empresas encontradas" value={data.total} href="/leads" />
        {STATUS_ORDER.map((s) => (
          <Kpi key={s} label={STATUS[s].label} value={data.by_status[s] ?? 0} color={STATUS[s].color} href={`/leads?digital_status=${s}`} hint={STATUS[s].hint} />
        ))}
        <Kpi label="Aguardando verificação" value={data.awaiting_verification} />
      </div>
      <p className="mt-2 text-xs text-neutral-400">“Site não informado no Maps” indica apenas que o cadastro de origem não traz site — não confirma ausência de site na internet.</p>
      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <Card><CardHeader title="Empresas por cidade" /><Bars rows={data.by_city.map((r) => ({ label: r.city, count: r.count }))} /></Card>
        <Card><CardHeader title="Empresas por segmento" /><Bars rows={data.by_category.map((r) => ({ label: r.category, count: r.count }))} /></Card>
        <Card>
          <CardHeader title="Funil de prospecção" subtitle={`${data.hot_leads} leads com pontuação ≥ 70 · ${data.social_only} só com redes sociais`} />
          <Bars rows={Object.entries(LEAD_STATUS).map(([k, label]) => ({ label, count: data.by_lead_status[k] ?? 0 }))} />
        </Card>
      </div>
      <div className="mt-4 text-sm text-neutral-400">Pesquisas ativas: {data.active_searches} · Consumo do mês: {usd(b.spent_usd)} / {usd(b.monthly_budget_usd)}</div>
    </>
  );
}
