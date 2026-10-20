"use client";

import { ArrowDown, ArrowUp, Download, ExternalLink, Filter, RefreshCw, Search as SearchIcon, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, qs, type Business, type Page } from "@/lib/api";
import { LEAD_STATUS, SOURCE_LABEL, STATUS, STATUS_ORDER, fmtDate } from "@/lib/labels";
import { Confidence, FictitiousTag, Score, StatusBadge } from "./StatusBadge";
import { Alert, Badge, Button, Card, Checkbox, Empty, Field, Input, Select, Spinner, cn } from "./ui";

export type Filters = Record<string, string | undefined>;

const COLS: { key: string; label: string; sort?: string; className?: string }[] = [
  { key: "score", label: "Pont.", sort: "lead_score" },
  { key: "name", label: "Empresa", sort: "name" },
  { key: "category", label: "Categoria", sort: "category" },
  { key: "city", label: "Cidade / endereço", sort: "city" },
  { key: "phone", label: "Telefone" },
  { key: "email", label: "E-mail" },
  { key: "profile", label: "Perfil / fonte" },
  { key: "source_site", label: "Site na fonte" },
  { key: "found_site", label: "Site identificado" },
  { key: "status", label: "Presença digital", sort: "digital_status" },
  { key: "confidence", label: "Confiança", sort: "confidence" },
  { key: "verified", label: "Verificação", sort: "last_verified_at" },
  { key: "lead", label: "Prospecção" },
];

function host(url: string | null) {
  if (!url) return null;
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function LinkOut({ href, children }: { href: string | null; children?: React.ReactNode }) {
  if (!href) return <span className="text-neutral-600">—</span>;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer nofollow" className="inline-flex max-w-[160px] items-center gap-1 truncate text-brand-400 hover:underline">
      <span className="truncate">{children ?? host(href)}</span> <ExternalLink className="h-3 w-3 shrink-0" />
    </a>
  );
}

export function ResultsTable({ fixed = {}, initial = {}, autoRefreshMs }: { fixed?: Filters; initial?: Filters; autoRefreshMs?: number }) {
  const [filters, setFilters] = useState<Filters>(initial);
  const [q, setQ] = useState(initial.q ?? "");
  const [sort, setSort] = useState("lead_score");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [data, setData] = useState<Page<Business> | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [showFilters, setShowFilters] = useState(false);
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  const query = useMemo(() => ({ ...filters, ...fixed, q: q || undefined }), [filters, fixed, q]);

  const load = useCallback(async () => {
    try {
      setData(await api<Page<Business>>(`/api/businesses${qs({ ...query, sort, order, page, page_size: pageSize })}`));
    } catch (e) {
      setMsg({ tone: "error", text: (e as Error).message });
    }
  }, [query, sort, order, page, pageSize]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  useEffect(() => {
    if (!autoRefreshMs) return;
    const t = setInterval(load, autoRefreshMs);
    return () => clearInterval(t);
  }, [autoRefreshMs, load]);

  const setF = (k: string, v: string | undefined) => {
    setPage(1);
    setFilters((f) => ({ ...f, [k]: v || undefined }));
  };
  const statuses = (filters.digital_status ?? "").split(",").filter(Boolean);
  const toggleStatus = (s: string) => setF("digital_status", (statuses.includes(s) ? statuses.filter((x) => x !== s) : [...statuses, s]).join(","));

  function toggleSort(key?: string) {
    if (!key) return;
    if (sort === key) setOrder(order === "asc" ? "desc" : "asc");
    else {
      setSort(key);
      setOrder(key === "name" || key === "city" ? "asc" : "desc");
    }
  }

  const allOnPage = data?.items.map((b) => b.id) ?? [];
  const allChecked = allOnPage.length > 0 && allOnPage.every((id) => selected.has(id));
  const toggleAll = () => setSelected((s) => { const n = new Set(s); allOnPage.forEach((id) => (allChecked ? n.delete(id) : n.add(id))); return n; });
  const toggleOne = (id: number) => setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });

  async function bulk(path: string, body: Record<string, unknown>, ok: (r: Record<string, number>) => string) {
    try {
      const r = await api<Record<string, number>>(path, { method: "POST", json: { ids: Array.from(selected), ...body } });
      setMsg({ tone: "success", text: ok(r) });
      load();
    } catch (e) {
      setMsg({ tone: "error", text: (e as Error).message });
    }
  }

  const exportUrl = (fmt: "csv" | "xlsx", onlySelected = false) =>
    `/api/exports/businesses.${fmt}${qs(onlySelected ? { ids: Array.from(selected) } : { ...query, sort, order })}`;

  const activeCount = Object.values(filters).filter(Boolean).length;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2 border-b border-neutral-800 p-3">
        <div className="relative min-w-[220px] flex-1">
          <SearchIcon className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-neutral-500" />
          <Input className="pl-9" placeholder="Buscar por nome, endereço, telefone ou domínio..." value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        </div>
        <Button variant="secondary" onClick={() => setShowFilters((v) => !v)}><Filter className="h-4 w-4" /> Filtros{activeCount ? ` (${activeCount})` : ""}</Button>
        <Button variant="ghost" onClick={load} title="Atualizar"><RefreshCw className="h-4 w-4" /></Button>
        <a href={exportUrl("csv")}><Button variant="secondary"><Download className="h-4 w-4" /> CSV</Button></a>
        <a href={exportUrl("xlsx")}><Button variant="secondary"><Download className="h-4 w-4" /> Excel</Button></a>
      </div>

      <div className="flex flex-wrap gap-1.5 border-b border-neutral-800 px-3 py-2">
        {STATUS_ORDER.map((s) => (
          <button key={s} onClick={() => toggleStatus(s)} title={STATUS[s].hint}
            className={cn("rounded-full border px-2.5 py-1 text-xs font-medium transition", statuses.includes(s) ? "border-transparent text-white" : "border-neutral-800 bg-neutral-900 text-neutral-400 hover:bg-neutral-800/60")}
            style={statuses.includes(s) ? { background: STATUS[s].color } : undefined}>
            {STATUS[s].label}
          </button>
        ))}
        <button onClick={() => setF("social_only", filters.social_only ? undefined : "true")}
          className={cn("rounded-full border px-2.5 py-1 text-xs font-medium", filters.social_only ? "border-transparent bg-pink-600 text-white" : "border-neutral-800 text-neutral-400")}>
          Só redes sociais
        </button>
      </div>

      {showFilters && (
        <div className="grid gap-3 border-b border-neutral-800 bg-neutral-950 p-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6">
          <Field label="Cidade"><Input value={filters.city ?? ""} onChange={(e) => setF("city", e.target.value)} /></Field>
          <Field label="Estado"><Input value={filters.state ?? ""} onChange={(e) => setF("state", e.target.value)} placeholder="PR" /></Field>
          <Field label="Bairro"><Input value={filters.neighborhood ?? ""} onChange={(e) => setF("neighborhood", e.target.value)} /></Field>
          <Field label="CEP"><Input value={filters.postal_code ?? ""} onChange={(e) => setF("postal_code", e.target.value)} /></Field>
          <Field label="Categoria"><Input value={filters.category ?? ""} onChange={(e) => setF("category", e.target.value)} /></Field>
          <Field label="Fonte">
            <Select value={filters.source ?? ""} onChange={(e) => setF("source", e.target.value)}>
              <option value="">Todas</option>
              <option value="google_places">Google Maps</option>
              <option value="osm">OpenStreetMap</option>
            </Select>
          </Field>
          <Field label="Status da prospecção">
            <Select value={filters.lead_status ?? ""} onChange={(e) => setF("lead_status", e.target.value)}>
              <option value="">Todos</option>
              {Object.entries(LEAD_STATUS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
          </Field>
          <Field label="Confiança mínima (%)"><Input type="number" min={0} max={100} value={filters.min_confidence ?? ""} onChange={(e) => setF("min_confidence", e.target.value)} /></Field>
          <Field label="Pontuação mínima"><Input type="number" min={0} max={100} value={filters.min_score ?? ""} onChange={(e) => setF("min_score", e.target.value)} /></Field>
          <Field label="Avaliação mínima"><Input type="number" step="0.1" min={0} max={5} value={filters.min_rating ?? ""} onChange={(e) => setF("min_rating", e.target.value)} /></Field>
          <Field label="Mín. de avaliações"><Input type="number" min={0} value={filters.min_reviews ?? ""} onChange={(e) => setF("min_reviews", e.target.value)} /></Field>
          <Field label="Verificado desde"><Input type="date" value={filters.verified_after?.slice(0, 10) ?? ""} onChange={(e) => setF("verified_after", e.target.value)} /></Field>
          <Field label="Dados">
            <Select value={filters.fictitious ?? ""} onChange={(e) => setF("fictitious", e.target.value)}>
              <option value="">Reais e fictícios</option>
              <option value="false">Somente reais</option>
              <option value="true">Somente fictícios (demo)</option>
            </Select>
          </Field>
          <div className="flex flex-col justify-end gap-2 sm:col-span-2">
            <Checkbox label="Com telefone" checked={filters.has_phone === "true"} onChange={(v) => setF("has_phone", v ? "true" : undefined)} />
            <Checkbox label="Com e-mail comercial público" checked={filters.has_email === "true"} onChange={(v) => setF("has_email", v ? "true" : undefined)} />
            <Checkbox label="Com perfil no Maps/fonte" checked={filters.has_maps === "true"} onChange={(v) => setF("has_maps", v ? "true" : undefined)} />
            <Checkbox label="Possíveis duplicadas" checked={filters.possible_duplicates === "true"} onChange={(v) => setF("possible_duplicates", v ? "true" : undefined)} />
          </div>
          <div className="flex items-end">
            <Button variant="ghost" onClick={() => { setFilters({}); setPage(1); }}><X className="h-4 w-4" /> Limpar filtros</Button>
          </div>
        </div>
      )}

      {selected.size > 0 && (
        <div className="flex flex-wrap items-center gap-2 border-b border-neutral-800 bg-brand-500/10 px-3 py-2 text-sm">
          <span className="font-medium">{selected.size} selecionada(s)</span>
          <Select className="w-auto" defaultValue="" onChange={(e) => { if (e.target.value) bulk("/api/businesses/bulk", { lead_status: e.target.value }, (r) => `${r.updated} atualizada(s).`); e.target.value = ""; }}>
            <option value="">Alterar status para...</option>
            {Object.entries(LEAD_STATUS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
          <Button size="sm" variant="secondary" onClick={() => bulk("/api/businesses/bulk-verify", {}, (r) => `${r.queued} verificação(ões) enfileirada(s).`)}>Reverificar</Button>
          <a href={exportUrl("csv", true)}><Button size="sm" variant="secondary">Exportar CSV</Button></a>
          <a href={exportUrl("xlsx", true)}><Button size="sm" variant="secondary">Exportar Excel</Button></a>
          <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>Limpar seleção</Button>
        </div>
      )}
      {msg && <div className="p-3"><Alert tone={msg.tone}>{msg.text}</Alert></div>}

      {!data ? <Spinner /> : data.items.length === 0 ? (
        <Empty title="Nenhuma empresa encontrada com estes filtros.">Ajuste os filtros ou inicie uma nova pesquisa.</Empty>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-neutral-950 text-left text-xs uppercase tracking-wide text-neutral-400">
              <tr>
                <th className="px-3 py-2"><input type="checkbox" checked={allChecked} onChange={toggleAll} aria-label="Selecionar página" /></th>
                {COLS.map((c) => (
                  <th key={c.key} className={cn("whitespace-nowrap px-3 py-2 font-medium", c.sort && "cursor-pointer select-none hover:text-neutral-200")} onClick={() => toggleSort(c.sort)}>
                    <span className="inline-flex items-center gap-1">{c.label}{c.sort === sort && (order === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}</span>
                  </th>
                ))}
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-800">
              {data.items.map((b) => (
                <tr key={b.id} className={cn("align-top hover:bg-neutral-800/60", selected.has(b.id) && "bg-brand-500/5")}>
                  <td className="px-3 py-2.5"><input type="checkbox" checked={selected.has(b.id)} onChange={() => toggleOne(b.id)} aria-label={`Selecionar ${b.name}`} /></td>
                  <td className="px-3 py-2.5"><Score value={b.lead_score} /></td>
                  <td className="min-w-[220px] max-w-[280px] px-3 py-2.5">
                    <Link href={`/leads/${b.id}`} className="font-medium text-neutral-100 hover:text-brand-400">{b.name}</Link>
                    <div className="mt-0.5 flex flex-wrap gap-1">
                      {b.is_fictitious && <FictitiousTag />}
                      {b.possible_duplicate_of && <Badge className="bg-amber-500/15 text-amber-300">possível duplicada</Badge>}
                      {b.social_only && <Badge className="bg-pink-500/15 text-pink-300">só redes sociais</Badge>}
                      {b.rating != null && <span className="text-xs text-neutral-400">★ {b.rating} ({b.reviews_count ?? 0})</span>}
                    </div>
                  </td>
                  <td className="max-w-[160px] px-3 py-2.5 text-neutral-400">{b.category ?? "—"}</td>
                  <td className="min-w-[180px] max-w-[220px] px-3 py-2.5 text-neutral-400">
                    <div className="font-medium text-neutral-200">{[b.city, b.state].filter(Boolean).join(" / ") || "—"}</div>
                    <div className="truncate text-xs" title={b.address ?? ""}>{b.address}</div>
                  </td>
                  <td className="whitespace-nowrap px-3 py-2.5 text-neutral-300">{b.phone ?? <span className="text-neutral-600">—</span>}</td>
                  <td className="max-w-[160px] truncate px-3 py-2.5 text-neutral-300">{b.email ?? <span className="text-neutral-600">—</span>}</td>
                  <td className="px-3 py-2.5"><LinkOut href={b.maps_url}>{(b.sources ?? []).map((s) => SOURCE_LABEL[s] ?? s).join(", ") || "abrir"}</LinkOut></td>
                  <td className="px-3 py-2.5"><LinkOut href={b.source_website} /></td>
                  <td className="px-3 py-2.5">
                    {b.official_website ? <LinkOut href={b.official_website} /> : b.candidate_website ? <span title="Não confirmado"><LinkOut href={b.candidate_website}>{host(b.candidate_website)} (?)</LinkOut></span> : <span className="text-neutral-600">—</span>}
                  </td>
                  <td className="px-3 py-2.5"><StatusBadge status={b.digital_status} short /></td>
                  <td className="px-3 py-2.5"><Confidence value={b.confidence} /></td>
                  <td className="whitespace-nowrap px-3 py-2.5 text-xs text-neutral-400">{b.verification_state === "queued" ? <Badge className="bg-blue-500/10 text-blue-400">na fila</Badge> : fmtDate(b.last_verified_at)}</td>
                  <td className="whitespace-nowrap px-3 py-2.5 text-xs text-neutral-400">{LEAD_STATUS[b.lead_status] ?? b.lead_status}</td>
                  <td className="px-3 py-2.5"><Link href={`/leads/${b.id}`}><Button size="sm" variant="secondary">Detalhes</Button></Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-neutral-800 px-3 py-2 text-sm text-neutral-400">
          <span>{data.total.toLocaleString("pt-BR")} empresa(s) · página {page} de {totalPages}</span>
          <div className="flex items-center gap-2">
            <Select className="w-auto" value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}>
              {[25, 50, 100, 200].map((n) => <option key={n} value={n}>{n} por página</option>)}
            </Select>
            <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Anterior</Button>
            <Button size="sm" variant="secondary" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Próxima</Button>
          </div>
        </div>
      )}
    </Card>
  );
}
