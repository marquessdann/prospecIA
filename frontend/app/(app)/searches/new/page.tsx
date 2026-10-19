"use client";

import dynamic from "next/dynamic";
import { Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { PageTitle } from "@/components/Shell";
import { Alert, Button, Card, CardHeader, Checkbox, Field, Input, Select, cn } from "@/components/ui";
import { api, type Budget, type LocationIn, type ProviderInfo, type Search, type SearchConfig } from "@/lib/api";
import { SEGMENTS, usd } from "@/lib/labels";

const MapPicker = dynamic(() => import("@/components/MapView").then((m) => m.MapPicker), { ssr: false });

interface Estimate {
  units: number;
  expected_businesses_max: number;
  total_usd: number;
  lines: { provider: string; requests: number; unit_cost_usd: number; cost_usd: number; available: boolean; note?: string }[];
  disclaimer: string;
  budget: Budget;
  warnings: string[];
  max_results: number;
}

const emptyLoc = (): LocationIn => ({ country: "Brasil", state: "", city: "" });

export default function NewSearchPage() {
  const router = useRouter();
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [aiEnabled, setAiEnabled] = useState(false);
  const [locations, setLocations] = useState<LocationIn[]>([emptyLoc()]);
  const [categories, setCategories] = useState<string[]>([]);
  const [custom, setCustom] = useState("");
  const [sources, setSources] = useState<string[]>([]);
  const [opts, setOpts] = useState({ web_verification: true, domain_guessing: true, use_ai: true, max_results: 100, web_provider: "", name: "", force_reverify: false });
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [mapFor, setMapFor] = useState<number | null>(null);

  useEffect(() => {
    api<{ providers: ProviderInfo[]; ai: { enabled: boolean } }>("/api/settings").then((s) => {
      setProviders(s.providers);
      setAiEnabled(s.ai.enabled);
      setSources(s.providers.filter((p) => p.kind === "places" && p.available).map((p) => p.name).slice(0, 1));
    });
  }, []);

  const placeProviders = providers.filter((p) => p.kind === "places");
  const webProviders = providers.filter((p) => p.kind === "web_search" && p.available);

  const config = (): SearchConfig => ({
    name: opts.name || undefined,
    locations: locations.map((l) => Object.fromEntries(Object.entries(l).filter(([, v]) => v !== "" && v !== undefined && !Number.isNaN(v))) as LocationIn),
    categories,
    sources,
    web_verification: opts.web_verification,
    web_provider: opts.web_provider || null,
    domain_guessing: opts.domain_guessing,
    use_ai: opts.use_ai,
    max_results: opts.max_results,
    force_reverify: opts.force_reverify,
  });

  const updLoc = (i: number, patch: Partial<LocationIn>) => { setEstimate(null); setLocations((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l))); };
  const toggleCat = (c: string) => { setEstimate(null); setCategories((cs) => (cs.includes(c) ? cs.filter((x) => x !== c) : [...cs, c])); };

  async function doEstimate() {
    setError(null);
    setBusy(true);
    try {
      setEstimate(await api<Estimate>("/api/searches/estimate", { method: "POST", json: config() }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function start() {
    setBusy(true);
    setError(null);
    try {
      const s = await api<Search>("/api/searches", { method: "POST", json: config() });
      router.push(`/searches/${s.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <>
      <PageTitle title="Nova pesquisa" subtitle="Defina localizações, segmentos e fontes. A estimativa de custo é exibida antes de iniciar." />
      <div className="grid gap-4 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">
          <Card>
            <CardHeader title="1. Localização" subtitle="Adicione várias cidades/bairros para pesquisar em sequência (lotes)."
              actions={<Button size="sm" variant="secondary" onClick={() => setLocations([...locations, emptyLoc()])}><Plus className="h-4 w-4" /> Localização</Button>} />
            <div className="space-y-4 p-5">
              {locations.map((l, i) => (
                <div key={i} className="rounded-lg border border-gray-200 p-3">
                  <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
                    <Field label="País"><Input value={l.country ?? ""} onChange={(e) => updLoc(i, { country: e.target.value })} /></Field>
                    <Field label="Estado"><Input value={l.state ?? ""} placeholder="PR" onChange={(e) => updLoc(i, { state: e.target.value })} /></Field>
                    <Field label="Cidade"><Input value={l.city ?? ""} placeholder="Curitiba" onChange={(e) => updLoc(i, { city: e.target.value })} /></Field>
                    <Field label="Bairro"><Input value={l.neighborhood ?? ""} onChange={(e) => updLoc(i, { neighborhood: e.target.value })} /></Field>
                    <Field label="CEP"><Input value={l.postal_code ?? ""} onChange={(e) => updLoc(i, { postal_code: e.target.value })} /></Field>
                    <Field label="Raio (km)"><Input type="number" min={0.1} max={50} step={0.5} value={l.radius_km ?? ""} onChange={(e) => updLoc(i, { radius_km: e.target.value ? Number(e.target.value) : undefined })} /></Field>
                  </div>
                  <div className="mt-3 grid gap-3 sm:grid-cols-3">
                    <Field label="Endereço (opcional)"><Input value={l.address ?? ""} onChange={(e) => updLoc(i, { address: e.target.value })} /></Field>
                    <Field label="Latitude"><Input type="number" step="any" value={l.lat ?? ""} onChange={(e) => updLoc(i, { lat: e.target.value ? Number(e.target.value) : undefined })} /></Field>
                    <Field label="Longitude"><Input type="number" step="any" value={l.lng ?? ""} onChange={(e) => updLoc(i, { lng: e.target.value ? Number(e.target.value) : undefined })} /></Field>
                  </div>
                  <div className="mt-2 flex gap-2">
                    <Button size="sm" variant="ghost" onClick={() => setMapFor(mapFor === i ? null : i)}>{mapFor === i ? "Fechar mapa" : "Selecionar ponto no mapa"}</Button>
                    {locations.length > 1 && <Button size="sm" variant="ghost" onClick={() => setLocations(locations.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /> Remover</Button>}
                  </div>
                  {mapFor === i && <div className="mt-2"><MapPicker lat={l.lat} lng={l.lng} radiusKm={l.radius_km} onPick={(lat, lng) => updLoc(i, { lat, lng, radius_km: l.radius_km ?? 2 })} /></div>}
                </div>
              ))}
            </div>
          </Card>

          <Card>
            <CardHeader title="2. Segmentos" subtitle="Escolha da lista ou digite qualquer segmento personalizado." />
            <div className="p-5">
              <div className="flex flex-wrap gap-2">
                {[...SEGMENTS, ...categories.filter((c) => !SEGMENTS.includes(c))].map((c) => (
                  <button key={c} onClick={() => toggleCat(c)} className={cn("rounded-full border px-3 py-1 text-sm", categories.includes(c) ? "border-brand-600 bg-brand-600 text-white" : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50")}>{c}</button>
                ))}
              </div>
              <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (custom.trim()) { toggleCat(custom.trim()); setCustom(""); } }}>
                <Input value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="Ex.: estúdio de tatuagem, autoescola, floricultura..." />
                <Button type="submit" variant="secondary">Adicionar</Button>
              </form>
            </div>
          </Card>

          <Card>
            <CardHeader title="3. Fontes e verificação" />
            <div className="grid gap-5 p-5 md:grid-cols-2">
              <div className="space-y-3">
                <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Fontes de empresas</p>
                {placeProviders.map((p) => (
                  <div key={p.name} className={cn("rounded-lg border p-3", !p.available && "opacity-60")}>
                    <Checkbox checked={sources.includes(p.name)} onChange={(v) => { setEstimate(null); setSources(v ? [...sources, p.name] : sources.filter((x) => x !== p.name)); }}
                      label={<span className="font-medium">{p.label} {!p.available && <span className="text-xs text-red-600">(sem credenciais)</span>}</span>} hint={p.coverage} />
                  </div>
                ))}
              </div>
              <div className="space-y-3">
                <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Verificação de presença digital</p>
                <Checkbox checked={opts.web_verification} onChange={(v) => setOpts({ ...opts, web_verification: v })} label="Buscar site oficial em mecanismo de busca autorizado"
                  hint={webProviders.length ? "Pesquisa nome + cidade e telefone." : "Nenhum provedor configurado: empresas sem site no cadastro ficarão como 'Site não informado no Maps'."} />
                {webProviders.length > 1 && (
                  <Select value={opts.web_provider} onChange={(e) => setOpts({ ...opts, web_provider: e.target.value })}>
                    <option value="">Automático</option>
                    {webProviders.map((w) => <option key={w.name} value={w.name}>{w.label}</option>)}
                  </Select>
                )}
                <Checkbox checked={opts.domain_guessing} onChange={(v) => setOpts({ ...opts, domain_guessing: v })} label="Testar domínios prováveis (DNS)" hint="Ex.: nomedaempresa.com.br — só confirma com telefone/endereço no site." />
                <Checkbox checked={opts.use_ai && aiEnabled} onChange={(v) => setOpts({ ...opts, use_ai: v })} label={`Adjudicação por IA nos casos ambíguos${aiEnabled ? "" : " (não configurada)"}`} />
                <Checkbox checked={opts.force_reverify} onChange={(v) => setOpts({ ...opts, force_reverify: v })} label="Reverificar empresas já verificadas recentemente" />
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Limite de empresas"><Input type="number" min={1} max={2000} value={opts.max_results} onChange={(e) => { setEstimate(null); setOpts({ ...opts, max_results: Number(e.target.value) }); }} /></Field>
                  <Field label="Nome (opcional)"><Input value={opts.name} onChange={(e) => setOpts({ ...opts, name: e.target.value })} /></Field>
                </div>
              </div>
            </div>
          </Card>
        </div>

        <div className="space-y-4">
          <Card className="sticky top-4">
            <CardHeader title="Estimativa e início" />
            <div className="space-y-4 p-5">
              {error && <Alert tone="error">{error}</Alert>}
              {estimate ? (
                <>
                  <table className="w-full text-sm">
                    <tbody className="divide-y divide-gray-100">
                      {estimate.lines.map((l) => (
                        <tr key={l.provider}><td className="py-1.5 text-gray-700">{l.provider}<div className="text-xs text-gray-400">{l.requests} req. × {usd(l.unit_cost_usd)}{l.note ? ` — ${l.note}` : ""}</div></td><td className="whitespace-nowrap py-1.5 pl-2 text-right tabular-nums">{usd(l.cost_usd)}</td></tr>
                      ))}
                      <tr className="font-semibold"><td className="py-2">Total máximo estimado</td><td className="whitespace-nowrap py-2 pl-2 text-right tabular-nums">{usd(estimate.total_usd)}</td></tr>
                    </tbody>
                  </table>
                  <p className="text-xs text-gray-500">{estimate.units} combinação(ões) localização × segmento × fonte · até {estimate.expected_businesses_max} empresas. {estimate.disclaimer}</p>
                  <p className="text-xs text-gray-500">Saldo do mês: {usd(estimate.budget.remaining_usd)} de {usd(estimate.budget.monthly_budget_usd)}</p>
                  {estimate.warnings.map((w) => <Alert key={w} tone="warning">{w}</Alert>)}
                  <Button className="w-full" onClick={start} loading={busy}>Iniciar pesquisa</Button>
                </>
              ) : (
                <Button className="w-full" variant="secondary" onClick={doEstimate} loading={busy} disabled={!categories.length || !sources.length}>Calcular estimativa</Button>
              )}
              <p className="text-xs text-gray-500">A cobertura depende das fontes conectadas, dos planos de API e dos dados cadastrados — não existe cobertura de todas as empresas.</p>
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
