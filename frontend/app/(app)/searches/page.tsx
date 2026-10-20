"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { PageTitle } from "@/components/Shell";
import { Alert, Badge, Button, Card, Empty, Spinner } from "@/components/ui";
import { api, type Search } from "@/lib/api";
import { SEARCH_STATUS, fmtDate, usd } from "@/lib/labels";

export default function SearchesPage() {
  const [items, setItems] = useState<Search[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const load = () => api<Search[]>("/api/searches").then(setItems).catch((e) => setError(e.message));
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);
  return (
    <>
      <PageTitle title="Pesquisas" subtitle="Histórico completo: reabra qualquer pesquisa para ver resultados, progresso e erros."
        actions={<Link href="/searches/new"><Button>Nova pesquisa</Button></Link>} />
      {error && <Alert tone="error">{error}</Alert>}
      <Card>
        {!items ? <Spinner /> : items.length === 0 ? (
          <Empty title="Nenhuma pesquisa ainda."><Link className="text-brand-400" href="/searches/new">Crie a primeira pesquisa</Link> informando cidade e segmento.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-neutral-950 text-left text-xs uppercase text-neutral-400">
                <tr>{["Pesquisa", "Status", "Fontes", "Encontradas", "Novas", "Verificadas", "Custo est. / real", "Criada"].map((h) => <th key={h} className="px-4 py-2 font-medium">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-neutral-800">
                {items.map((s) => (
                  <tr key={s.id} className="hover:bg-neutral-800/60">
                    <td className="px-4 py-3"><Link href={`/searches/${s.id}`} className="font-medium text-neutral-100 hover:text-brand-400">{s.name}</Link></td>
                    <td className="px-4 py-3"><Badge className={SEARCH_STATUS[s.status]?.badge}>{SEARCH_STATUS[s.status]?.label ?? s.status}</Badge></td>
                    <td className="px-4 py-3 text-neutral-400">{s.config.sources.join(", ")}</td>
                    <td className="px-4 py-3 tabular-nums">{s.total_found}</td>
                    <td className="px-4 py-3 tabular-nums">{s.total_new}</td>
                    <td className="px-4 py-3 tabular-nums">{s.total_verified}/{s.total_to_verify}</td>
                    <td className="px-4 py-3 tabular-nums text-neutral-400">{usd(s.estimated_cost_usd)} / {usd(s.actual_cost_usd)}</td>
                    <td className="px-4 py-3 text-neutral-400">{fmtDate(s.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
