// Cliente HTTP do frontend. Todas as chamadas passam por /api (proxy do Next) com cookie httpOnly.

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function detailMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) return d.map((x) => (x && typeof x === "object" && "msg" in x ? String(x.msg) : String(x))).join("; ");
  }
  return fallback;
}

export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-Requested-With", "prospecia");
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  const res = await fetch(path, { ...init, body, headers, credentials: "same-origin" });
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/api/auth/")) {
    window.location.href = "/login";
  }
  if (!res.ok) {
    let parsed: unknown = null;
    try {
      parsed = await res.json();
    } catch {
      /* corpo não-JSON */
    }
    throw new ApiError(res.status, detailMessage(parsed, `Erro ${res.status}`));
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function qs(params: Record<string, unknown>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "" || (Array.isArray(v) && v.length === 0)) continue;
    sp.set(k, Array.isArray(v) ? v.join(",") : String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

// ---------- Tipos ----------
export type DigitalStatus =
  | "SEM_SITE_IDENTIFICADO"
  | "SITE_NAO_INFORMADO_NO_MAPS"
  | "POSSUI_SITE"
  | "SITE_INDISPONIVEL"
  | "SITE_SUSPEITO"
  | "VERIFICACAO_PENDENTE";

export interface User {
  id: number;
  org_id: number;
  email: string;
  name: string;
  role: "admin" | "manager" | "member";
  is_active: boolean;
  monthly_budget_usd: number;
  max_results_per_search: number;
}

export interface Business {
  id: number;
  name: string;
  category: string | null;
  address: string | null;
  neighborhood: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  postal_code: string | null;
  lat: number | null;
  lng: number | null;
  phone: string | null;
  email: string | null;
  maps_url: string | null;
  source_website: string | null;
  official_website: string | null;
  official_domain: string | null;
  candidate_website: string | null;
  social_links: string[] | null;
  directory_links: string[] | null;
  rating: number | null;
  reviews_count: number | null;
  business_status: string | null;
  sources: string[] | null;
  digital_status: DigitalStatus;
  confidence: number;
  classification_reason: string | null;
  ai_summary: string | null;
  social_only: boolean;
  verification_state: string;
  last_verified_at: string | null;
  lead_score: number;
  lead_status: string;
  assignee_id: number | null;
  possible_duplicate_of: number | null;
  is_fictitious: boolean;
  created_at: string;
}

export interface Evidence {
  type: string;
  source: string;
  detail: string;
  polarity: "+" | "-" | "0";
  url: string | null;
}

export interface Verification {
  id: number;
  search_id: number | null;
  status: DigitalStatus;
  confidence: number;
  reason: string;
  evidence: Evidence[];
  sources_consulted: string[];
  candidates: Array<{ domain: string; url: string; origin: string; score: number; reachable: boolean; parked: boolean; signals: string[]; ai_verdict?: string | null }> | null;
  ai_used: boolean;
  ai_summary: string | null;
  cost_usd: number;
  created_at: string;
}

export interface BusinessDetail extends Business {
  categories: string[] | null;
  score_breakdown: { criteria: Record<string, number>; weights: Record<string, number>; note: string } | null;
  source_records: Array<{ id: number; source: string; external_id: string; source_url: string | null; website: string | null; fetched_at: string; expires_at: string | null }>;
  verifications: Verification[];
  interactions: Array<{ id: number; kind: string; content: string; created_at: string; user_name: string | null }>;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface LocationIn {
  country?: string;
  state?: string;
  city?: string;
  neighborhood?: string;
  postal_code?: string;
  address?: string;
  lat?: number;
  lng?: number;
  radius_km?: number;
}

export interface SearchConfig {
  name?: string;
  locations: LocationIn[];
  categories: string[];
  sources: string[];
  web_verification: boolean;
  web_provider?: string | null;
  domain_guessing: boolean;
  use_ai: boolean;
  max_results: number;
  force_reverify?: boolean;
}

export interface Search {
  id: number;
  name: string;
  status: "queued" | "running" | "paused" | "completed" | "failed" | "cancelled";
  config: SearchConfig;
  estimated_cost_usd: number;
  actual_cost_usd: number;
  total_found: number;
  total_new: number;
  total_verified: number;
  total_to_verify: number;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface SearchDetail extends Search {
  units: Array<{ id: number; source: string; location: LocationIn; category: string; status: string; results_count: number; requests_made: number; attempts: number; last_error: string | null }>;
  events: Array<{ id: number; level: string; provider: string | null; message: string; created_at: string }>;
  status_counts: Record<string, number>;
}

export interface ProviderInfo {
  name: string;
  label: string;
  kind: "places" | "web_search";
  available: boolean;
  requires_credentials: boolean;
  cost_per_request_usd: number;
  coverage: string;
  terms_notes: string;
  max_results_per_query: number | null;
}

export interface Budget {
  monthly_budget_usd: number;
  spent_usd: number;
  remaining_usd: number;
  percent: number;
  level: "ok" | "warning" | "exceeded";
}
