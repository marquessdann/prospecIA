"use client";

import { ExternalLink, RefreshCw, Trash2 } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { PageTitle, useUser } from "@/components/Shell";
import { Confidence, FictitiousTag, Score, StatusBadge } from "@/components/StatusBadge";
import { Alert, Badge, Button, Card, CardHeader, Field, Input, Select, Spinner, cn } from "@/components/ui";
import { api, type BusinessDetail, type DigitalStatus, type User } from "@/lib/api";
import { INTERACTION_KIND, LEAD_STATUS, SCORE_CRITERIA, SOURCE_LABEL, STATUS, STATUS_ORDER, fmtDate, usd } from "@/lib/labels";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-3 gap-3 py-2 text-sm">
      <dt className="text-gray-500">{label}</dt>
      <dd className="col-span-2 break-words text-gray-900">{children || <span className="text-gray-300">—</span>}</dd>
    </div>
  );
}

function Ext({ href }: { href: string | null | undefined }) {
  if (!href) return null;
  return <a href={href} target="_blank" rel="noopener noreferrer nofollow" className="inline-flex items-center gap-1 text-brand-600 hover:underline">{href} <ExternalLink className="h-3 w-3" /></a>;
}

export default function BusinessPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const me = useUser();
  const [b, setB] = useState<BusinessDetail | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [note, setNote] = useState({ kind: "note", content: "" });
  const [msg, setMsg] = useState<{ tone: "success" | "error" | "info"; text: string } | null>(null);
  const canManage = me?.role === "admin" || me?.role === "manager";

  const load = useCallback(() => api<BusinessDetail>(`/api/businesses/${id}`).then(setB).catch((e) => setMsg({ tone: "error", text: e.message })), [id]);
  useEffect(() => { load(); api<User[]>("/api/users").then(setUsers).catch(() => undefined); }, [load]);

  async function patch(body: Record<string, unknown>) {
    try {
      await api(`/api/businesses/${id}`, { method: "PATCH", json: body });
      load();
    } catch (e) {
      setMsg({ tone: "error", text: (e as Error).message });
    }
  }

  async function addNote() {
    if (!note.content.trim()) return;
    await api(`/api/businesses/${id}/interactions`, { method: "POST", json: note });
    setNote({ ...note, content: "" });
    load();
  }

  async function reverify() {
    const r = await api<{ queued: boolean }>(`/api/businesses/${id}/verify`, { method: "POST" });
    setMsg({ tone: "info", text: r.queued ? "Verificação enfileirada. Atualize em instantes." : "Já existe uma verificação na fila." });
    load();
  }

  async function remove() {
    if (!confirm("Excluir definitivamente esta empresa e todo o histórico?")) return;
    await api(`/api/businesses/${id}`, { method: "DELETE" });
    router.push("/leads");
  }

  if (!b) return msg ? <Alert tone="error">{msg.text}</Alert> : <Spinner />;
  const last = b.verifications[0];

  return (
    <>
      <PageTitle title={b.name}
        subtitle={<span className="flex flex-wrap items-center gap-2">{b.category} · {[b.city, b.state].filter(Boolean).join(" / ")} {b.is_fictitious && <FictitiousTag />}</span>}
        actions={<>
          <Button variant="secondary" onClick={reverify} disabled={b.is_fictitious}><RefreshCw className="h-4 w-4" /> Reverificar</Button>
          {canManage && <Button variant="danger" onClick={remove}><Trash2 className="h-4 w-4" /> Excluir</Button>}
        </>} />
      {msg && <div className="mb-4"><Alert tone={msg.tone}>{msg.text}</Alert></div>}
      {b.possible_duplicate_of && <div className="mb-4"><Alert tone="warning">Possível duplicada de <a className="underline" href={`/leads/${b.possible_duplicate_of}`}>#{b.possible_duplicate_of}</a>. Revise antes de contatar.</Alert></div>}

      <div className="grid gap-4 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">
          <Card>
            <CardHeader title="Presença digital" subtitle={`Última verificação: ${fmtDate(b.last_verified_at)}`} actions={<StatusBadge status={b.digital_status} />} />
            <div className="space-y-3 p-5">
              <div className="flex flex-wrap items-center gap-6">
                <div><div className="text-xs uppercase text-gray-500">Confiança</div><Confidence value={b.confidence} /></div>
                <div><div className="text-xs uppercase text-gray-500">Pontuação do lead</div><Score value={b.lead_score} /></div>
                {b.social_only && <Badge className="bg-pink-100 text-pink-800">Presença apenas em redes sociais</Badge>}
              </div>
              <p className="text-sm text-gray-800">{b.classification_reason}</p>
              {b.ai_summary && <Alert tone="info"><b>Observação gerada por IA</b> (baseada apenas nas evidências): {b.ai_summary}</Alert>}
              <p className="text-xs text-gray-500">{STATUS[b.digital_status].hint}</p>
              <dl className="divide-y divide-gray-100">
                <Row label="Site informado na fonte"><Ext href={b.source_website} /></Row>
                <Row label="Site oficial identificado"><Ext href={b.official_website} /></Row>
                <Row label="Domínio não confirmado"><Ext href={b.candidate_website} /></Row>
                <Row label="Redes sociais">{b.social_links?.map((s) => <div key={s}><Ext href={s} /></div>)}</Row>
                <Row label="Diretórios/marketplaces">{b.directory_links?.map((s) => <div key={s}><Ext href={s} /></div>)}</Row>
              </dl>
            </div>
          </Card>

          {last && (
            <Card>
              <CardHeader title="Evidências da última verificação" subtitle={`${last.ai_used ? "Com análise por IA · " : ""}custo ${usd(last.cost_usd)}`} />
              <ul className="divide-y divide-gray-100">
                {last.evidence.map((e, i) => (
                  <li key={i} className="flex gap-3 px-5 py-2.5 text-sm">
                    <span className={cn("mt-1 h-2 w-2 shrink-0 rounded-full", e.polarity === "+" ? "bg-blue-500" : e.polarity === "-" ? "bg-green-500" : "bg-gray-300")} title={e.polarity === "+" ? "Indica site" : e.polarity === "-" ? "Indica ausência de site" : "Neutro"} />
                    <div><span className="font-medium text-gray-700">{e.source}:</span> {e.detail} {e.url && <Ext href={e.url} />}</div>
                  </li>
                ))}
              </ul>
              <div className="border-t border-gray-100 px-5 py-3 text-xs text-gray-500"><b>Fontes consultadas:</b> {last.sources_consulted.join(" · ")}</div>
            </Card>
          )}

          <Card>
            <CardHeader title="Histórico de verificações" />
            <ul className="divide-y divide-gray-100 text-sm">
              {b.verifications.length === 0 && <li className="px-5 py-3 text-gray-500">Ainda não verificada.</li>}
              {b.verifications.map((v) => (
                <li key={v.id} className="flex flex-wrap items-center gap-3 px-5 py-2.5">
                  <span className="text-xs text-gray-400">{fmtDate(v.created_at)}</span>
                  <StatusBadge status={v.status} short />
                  <span className="text-xs text-gray-500">{v.confidence}%</span>
                  <span className="flex-1 text-gray-700">{v.reason}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Dados públicos coletados" />
            <dl className="divide-y divide-gray-100 px-5">
              <Row label="Endereço">{b.address}</Row>
              <Row label="Bairro / CEP">{[b.neighborhood, b.postal_code].filter(Boolean).join(" · ")}</Row>
              <Row label="Telefone">{b.phone}</Row>
              <Row label="E-mail comercial">{b.email}</Row>
              <Row label="Avaliação">{b.rating != null ? `★ ${b.rating} (${b.reviews_count ?? 0} avaliações)` : null}</Row>
              <Row label="Funcionamento">{b.business_status}</Row>
              <Row label="Perfil na fonte"><Ext href={b.maps_url} /></Row>
            </dl>
            <div className="border-t border-gray-100 px-5 py-3 text-xs text-gray-500">
              {b.source_records.map((s) => (
                <div key={s.id}>{SOURCE_LABEL[s.source] ?? s.source}: <Ext href={s.source_url} /> · coletado {fmtDate(s.fetched_at)}{s.expires_at && ` · retenção até ${fmtDate(s.expires_at)}`}</div>
              ))}
            </div>
          </Card>

          <Card>
            <CardHeader title="Prospecção (CRM)" />
            <div className="space-y-3 p-5">
              <Field label="Status">
                <Select value={b.lead_status} onChange={(e) => patch({ lead_status: e.target.value })}>
                  {Object.entries(LEAD_STATUS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </Select>
              </Field>
              <Field label="Responsável">
                <Select value={b.assignee_id ?? ""} onChange={(e) => patch({ assignee_id: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">Sem responsável</option>
                  {users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
                </Select>
              </Field>
              {canManage && (
                <Field label="Corrigir classificação (manual)">
                  <Select value="" onChange={(e) => e.target.value && patch({ digital_status: e.target.value })}>
                    <option value="">Manter</option>
                    {STATUS_ORDER.map((s) => <option key={s} value={s}>{STATUS[s as DigitalStatus].label}</option>)}
                  </Select>
                </Field>
              )}
              {b.lead_status === "nao_contatar" && <Alert tone="warning">Marcada como “Não contatar”: excluída das exportações por padrão.</Alert>}
              <div className="border-t border-gray-100 pt-3">
                <div className="flex gap-2">
                  <Select className="w-32" value={note.kind} onChange={(e) => setNote({ ...note, kind: e.target.value })}>
                    {["note", "call", "email", "whatsapp", "meeting", "other"].map((k) => <option key={k} value={k}>{INTERACTION_KIND[k]}</option>)}
                  </Select>
                  <Input placeholder="Nota ou interação..." value={note.content} onChange={(e) => setNote({ ...note, content: e.target.value })} onKeyDown={(e) => e.key === "Enter" && addNote()} />
                </div>
                <Button size="sm" className="mt-2" onClick={addNote}>Registrar</Button>
              </div>
              <ul className="space-y-2">
                {b.interactions.map((it) => (
                  <li key={it.id} className="rounded-lg bg-gray-50 p-2.5 text-sm">
                    <div className="text-xs text-gray-500">{INTERACTION_KIND[it.kind] ?? it.kind} · {it.user_name ?? "sistema"} · {fmtDate(it.created_at)}</div>
                    <div className="text-gray-800">{it.content}</div>
                  </li>
                ))}
              </ul>
              <p className="text-xs text-gray-400">Envio automático de mensagens não é realizado. Respeite a LGPD e as regras de cada canal.</p>
            </div>
          </Card>

          {b.score_breakdown && (
            <Card>
              <CardHeader title="Composição da pontuação" subtitle={b.score_breakdown.note} />
              <ul className="space-y-1 p-5 text-sm">
                {Object.entries(b.score_breakdown.criteria).map(([k, v]) => <li key={k} className="flex justify-between"><span className="text-gray-600">{SCORE_CRITERIA[k] ?? k}</span><span className="tabular-nums">{v} / {Math.round(((b.score_breakdown?.weights[k] ?? 0) / Math.max(1, Object.values(b.score_breakdown?.weights ?? {}).reduce((a, x) => a + x, 0))) * 100)}</span></li>)}
              </ul>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
