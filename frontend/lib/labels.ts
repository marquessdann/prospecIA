import type { DigitalStatus } from "./api";

export const STATUS: Record<DigitalStatus, { label: string; short: string; color: string; badge: string; hint: string }> = {
  SEM_SITE_IDENTIFICADO: {
    label: "Sem site identificado",
    short: "Sem site",
    color: "#16a34a",
    badge: "bg-green-500/15 text-green-300 ring-green-500/30",
    hint: "Nenhuma evidência confiável de site próprio após as verificações realizadas.",
  },
  SITE_NAO_INFORMADO_NO_MAPS: {
    label: "Site não informado no Maps",
    short: "Não informado",
    color: "#ca8a04",
    badge: "bg-yellow-500/15 text-yellow-300 ring-yellow-500/30",
    hint: "O cadastro de origem não apresenta site — isso NÃO confirma ausência de site na internet.",
  },
  POSSUI_SITE: {
    label: "Possui site",
    short: "Possui site",
    color: "#2563eb",
    badge: "bg-blue-500/15 text-blue-300 ring-blue-500/30",
    hint: "Site oficial identificado e acessível.",
  },
  SITE_INDISPONIVEL: {
    label: "Site indisponível",
    short: "Indisponível",
    color: "#dc2626",
    badge: "bg-red-500/15 text-red-300 ring-red-500/30",
    hint: "Um possível site oficial foi identificado, mas não respondeu às verificações.",
  },
  SITE_SUSPEITO: {
    label: "Site suspeito/não confirmado",
    short: "Suspeito",
    color: "#9333ea",
    badge: "bg-purple-500/15 text-purple-300 ring-purple-500/30",
    hint: "Há indícios de um domínio, sem evidências suficientes de que pertence à empresa.",
  },
  VERIFICACAO_PENDENTE: {
    label: "Verificação pendente",
    short: "Pendente",
    color: "#6b7280",
    badge: "bg-neutral-800 text-neutral-300 ring-neutral-500/30",
    hint: "Não foi possível concluir a análise.",
  },
};

export const STATUS_ORDER: DigitalStatus[] = [
  "SEM_SITE_IDENTIFICADO",
  "SITE_NAO_INFORMADO_NO_MAPS",
  "SITE_INDISPONIVEL",
  "SITE_SUSPEITO",
  "POSSUI_SITE",
  "VERIFICACAO_PENDENTE",
];

export const LEAD_STATUS: Record<string, string> = {
  novo: "Novo lead",
  revisado: "Lead revisado",
  contato_realizado: "Contato realizado",
  aguardando_resposta: "Aguardando resposta",
  interessado: "Interessado",
  proposta_enviada: "Proposta enviada",
  convertido: "Cliente convertido",
  sem_interesse: "Sem interesse",
  nao_contatar: "Não contatar",
};

export const SEARCH_STATUS: Record<string, { label: string; badge: string }> = {
  queued: { label: "Na fila", badge: "bg-neutral-800 text-neutral-300" },
  running: { label: "Em execução", badge: "bg-blue-500/15 text-blue-300" },
  paused: { label: "Pausada", badge: "bg-yellow-500/15 text-yellow-300" },
  completed: { label: "Concluída", badge: "bg-green-500/15 text-green-300" },
  failed: { label: "Falhou", badge: "bg-red-500/15 text-red-300" },
  cancelled: { label: "Cancelada", badge: "bg-neutral-800 text-neutral-400" },
};

export const SEGMENTS = [
  "Restaurantes",
  "Clínicas médicas",
  "Consultórios odontológicos",
  "Psicólogos",
  "Academias",
  "Salões de beleza",
  "Barbearias",
  "Oficinas mecânicas",
  "Imobiliárias",
  "Advogados",
  "Contadores",
  "Pet shops",
  "Lojas de roupas",
  "Empresas de construção",
  "Prestadores de serviços",
  "Pequenos negócios",
];

export const SOURCE_LABEL: Record<string, string> = {
  google_places: "Google Maps",
  osm: "OpenStreetMap",
  demo: "Demonstração",
};

export const INTERACTION_KIND: Record<string, string> = {
  note: "Nota",
  call: "Ligação",
  email: "E-mail",
  whatsapp: "WhatsApp",
  meeting: "Reunião",
  other: "Outro",
  status_change: "Mudança de status",
};

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export function usd(v: number | null | undefined): string {
  return `US$ ${(v ?? 0).toFixed(v && v < 1 ? 3 : 2)}`;
}

export const SCORE_CRITERIA: Record<string, string> = {
  no_website: "Ausência de site (com evidências)",
  public_profile: "Perfil empresarial público",
  contact_channel: "Canal comercial público",
  activity: "Avaliações e sinais de atividade",
  operational: "Empresa em funcionamento",
  data_quality: "Qualidade dos dados",
};
