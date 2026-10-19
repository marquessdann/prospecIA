"use client";

import { useCallback, useEffect, useState } from "react";
import { PageTitle, useUser } from "@/components/Shell";
import { Alert, Badge, Button, Card, CardHeader, Field, Input, Select, Spinner } from "@/components/ui";
import { api, type Budget, type ProviderInfo, type User } from "@/lib/api";
import { usd } from "@/lib/labels";

interface SettingsInfo {
  providers: ProviderInfo[];
  ai: { enabled: boolean; provider: string; model: string | null };
  domain_guessing: boolean;
  verification_ttl_days: number;
  scoring: { weights: Record<string, number>; labels: Record<string, string> };
  retention: { google_places_days: number };
}
interface Usage {
  by_provider: { provider: string; operation: string; units: number; cost_usd: number; calls: number }[];
  by_user: { user: string; cost_usd: number }[];
  budget: Budget;
}

export default function SettingsPage() {
  const me = useUser();
  const [info, setInfo] = useState<SettingsInfo | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [newUser, setNewUser] = useState({ name: "", email: "", password: "", role: "member", monthly_budget_usd: 25, max_results_per_search: 200 });
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const isAdmin = me?.role === "admin";
  const canManage = isAdmin || me?.role === "manager";

  const load = useCallback(() => {
    api<SettingsInfo>("/api/settings").then((s) => { setInfo(s); setWeights(s.scoring.weights); });
    api<Usage>("/api/usage").then(setUsage);
    api<User[]>("/api/users").then(setUsers);
  }, []);
  useEffect(load, [load]);

  const wrap = (fn: () => Promise<unknown>, ok: string) => async () => {
    try { await fn(); setMsg({ tone: "success", text: ok }); load(); } catch (e) { setMsg({ tone: "error", text: (e as Error).message }); }
  };

  if (!info) return <Spinner />;
  return (
    <>
      <PageTitle title="Configurações" subtitle="Fontes conectadas, limites de cobertura, custos, pontuação e usuários." />
      {msg && <div className="mb-4"><Alert tone={msg.tone}>{msg.text}</Alert></div>}

      <Card className="mb-4">
        <CardHeader title="Fontes de dados e cobertura" subtitle="Chaves de API ficam apenas no servidor (variáveis de ambiente) e nunca são enviadas ao navegador." />
        <div className="grid gap-3 p-5 md:grid-cols-2">
          {info.providers.map((p) => (
            <div key={p.name} className="rounded-lg border border-gray-200 p-4">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">{p.label}</span>
                <Badge className={p.available ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-600"}>{p.available ? "Ativa" : p.requires_credentials ? "Sem credenciais" : "Desativada"}</Badge>
              </div>
              <div className="mt-1 text-xs text-gray-500">{p.kind === "places" ? "Descoberta de empresas" : "Busca web para verificação"} · {usd(p.cost_per_request_usd)}/requisição{p.max_results_per_query ? ` · máx. ${p.max_results_per_query} por consulta` : ""}</div>
              <p className="mt-2 text-sm text-gray-700"><b>Cobertura:</b> {p.coverage}</p>
              <p className="mt-1 text-sm text-gray-700"><b>Termos/custos:</b> {p.terms_notes}</p>
            </div>
          ))}
          <div className="rounded-lg border border-gray-200 p-4 text-sm">
            <div className="font-medium">IA</div>
            <p className="mt-1 text-gray-700">{info.ai.enabled ? `Ativa (${info.ai.provider}, modelo ${info.ai.model}).` : "Não configurada — a classificação usa apenas regras determinísticas."}</p>
            <p className="mt-1 text-gray-500">Teste de domínios prováveis: {info.domain_guessing ? "ativo" : "desativado"} · reverificação após {info.verification_ttl_days} dias · retenção de dados do Google: {info.retention.google_places_days} dias.</p>
          </div>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Pesos da pontuação de leads" subtitle="A pontuação (0–100) é uma prioridade estimada, não garantia de interesse." />
          <div className="space-y-3 p-5">
            {Object.entries(info.scoring.labels).map(([k, label]) => (
              <div key={k} className="flex items-center gap-3">
                <span className="flex-1 text-sm text-gray-700">{label}</span>
                <input type="range" min={0} max={60} value={weights[k] ?? 0} disabled={!canManage} onChange={(e) => setWeights({ ...weights, [k]: Number(e.target.value) })} />
                <span className="w-8 text-right text-sm tabular-nums">{weights[k]}</span>
              </div>
            ))}
            {canManage && <Button onClick={wrap(() => api("/api/settings/scoring", { method: "PUT", json: { weights } }), "Pesos salvos e pontuações recalculadas.")}>Salvar e recalcular</Button>}
          </div>
        </Card>

        <Card>
          <CardHeader title="Consumo de APIs neste mês" subtitle={usage ? `Seu limite: ${usd(usage.budget.spent_usd)} de ${usd(usage.budget.monthly_budget_usd)} (${usage.budget.percent}%)` : ""} />
          <div className="p-5">
            {usage?.budget.level === "warning" && <Alert tone="warning">Você usou mais de 80% do limite mensal.</Alert>}
            {usage?.budget.level === "exceeded" && <Alert tone="error">Limite mensal atingido: novas pesquisas bloqueadas e pesquisas em andamento pausadas.</Alert>}
            <table className="mt-2 w-full text-sm">
              <thead className="text-left text-xs uppercase text-gray-500"><tr><th className="py-1">Provedor</th><th>Operação</th><th className="text-right">Chamadas</th><th className="text-right">Custo</th></tr></thead>
              <tbody className="divide-y divide-gray-100">
                {usage?.by_provider.map((r) => <tr key={r.provider + r.operation}><td className="py-1.5">{r.provider}</td><td>{r.operation}</td><td className="text-right tabular-nums">{r.calls}</td><td className="text-right tabular-nums">{usd(r.cost_usd)}</td></tr>)}
                {!usage?.by_provider.length && <tr><td colSpan={4} className="py-3 text-gray-500">Nenhum consumo registrado.</td></tr>}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader title="Usuários e limites" subtitle="Limite de consumo mensal e de empresas por pesquisa por usuário." />
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500"><tr>{["Nome", "E-mail", "Papel", "Limite mensal (US$)", "Máx. empresas/pesquisa", "Ativo"].map((h) => <th key={h} className="px-4 py-2">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-gray-100">
              {users.map((u) => (
                <tr key={u.id}>
                  <td className="px-4 py-2">{u.name}</td>
                  <td className="px-4 py-2 text-gray-600">{u.email}</td>
                  <td className="px-4 py-2">
                    <Select disabled={!isAdmin} value={u.role} onChange={(e) => wrap(() => api(`/api/users/${u.id}`, { method: "PATCH", json: { role: (e.target as HTMLSelectElement).value } }), "Papel atualizado.")()}>
                      <option value="admin">admin</option><option value="manager">manager</option><option value="member">member</option>
                    </Select>
                  </td>
                  <td className="px-4 py-2"><Input type="number" disabled={!isAdmin} defaultValue={u.monthly_budget_usd} onBlur={(e) => Number(e.target.value) !== u.monthly_budget_usd && wrap(() => api(`/api/users/${u.id}`, { method: "PATCH", json: { monthly_budget_usd: Number(e.target.value) } }), "Limite atualizado.")()} /></td>
                  <td className="px-4 py-2"><Input type="number" disabled={!isAdmin} defaultValue={u.max_results_per_search} onBlur={(e) => Number(e.target.value) !== u.max_results_per_search && wrap(() => api(`/api/users/${u.id}`, { method: "PATCH", json: { max_results_per_search: Number(e.target.value) } }), "Limite atualizado.")()} /></td>
                  <td className="px-4 py-2"><input type="checkbox" disabled={!isAdmin || u.id === me?.id} checked={u.is_active} onChange={(e) => wrap(() => api(`/api/users/${u.id}`, { method: "PATCH", json: { is_active: e.target.checked } }), "Usuário atualizado.")()} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {isAdmin && (
          <div className="grid gap-3 border-t border-gray-100 p-5 sm:grid-cols-3 lg:grid-cols-7">
            <Field label="Nome"><Input value={newUser.name} onChange={(e) => setNewUser({ ...newUser, name: e.target.value })} /></Field>
            <Field label="E-mail"><Input type="email" value={newUser.email} onChange={(e) => setNewUser({ ...newUser, email: e.target.value })} /></Field>
            <Field label="Senha"><Input type="password" value={newUser.password} onChange={(e) => setNewUser({ ...newUser, password: e.target.value })} /></Field>
            <Field label="Papel"><Select value={newUser.role} onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}><option value="member">member</option><option value="manager">manager</option><option value="admin">admin</option></Select></Field>
            <Field label="Limite US$/mês"><Input type="number" value={newUser.monthly_budget_usd} onChange={(e) => setNewUser({ ...newUser, monthly_budget_usd: Number(e.target.value) })} /></Field>
            <Field label="Máx. empresas"><Input type="number" value={newUser.max_results_per_search} onChange={(e) => setNewUser({ ...newUser, max_results_per_search: Number(e.target.value) })} /></Field>
            <div className="flex items-end"><Button onClick={wrap(() => api("/api/users", { method: "POST", json: newUser }), "Usuário criado.")}>Adicionar usuário</Button></div>
          </div>
        )}
      </Card>
    </>
  );
}
