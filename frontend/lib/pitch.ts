// Gerador de mensagens de prospecção por WhatsApp (modelos locais, sem custo e sem IA).
// As mensagens usam apenas dados já verificados da empresa e sempre oferecem opção de recusa (LGPD).

import type { Business } from "./api";

export interface Sender {
  name: string;
  company: string;
  portfolio: string;
}

export type PitchStyle = "primeiro" | "consultivo" | "portfolio" | "followup";

export const PITCH_STYLES: { key: PitchStyle; label: string; hint: string }[] = [
  { key: "primeiro", label: "Primeiro contato", hint: "curta e direta" },
  { key: "consultivo", label: "Consultiva", hint: "mostra os benefícios" },
  { key: "portfolio", label: "Com portfólio", hint: "envia exemplos do seu trabalho" },
  { key: "followup", label: "Retorno", hint: "para quem não respondeu" },
];

// Benefício do site conforme o segmento (comparação por palavras-chave, sem acento).
const SEGMENT_BENEFITS: [string[], string][] = [
  [["restaurante", "lanchonete", "pizzaria", "hamburg", "cafe", "padaria", "bar", "food"], "mostrar o cardápio, fotos dos pratos e receber pedidos direto, sem pagar comissão de aplicativo"],
  [["odonto", "dentist", "clinica", "medic", "psicolog", "fisio", "nutri", "saude", "doctor", "dentist"], "oferecer agendamento online, apresentar os profissionais e passar mais confiança para novos pacientes"],
  [["academia", "fitness", "crossfit", "pilates", "studio"], "divulgar planos, horários e captar alunos com aula experimental"],
  [["barbear", "salao", "beleza", "estetica", "manicure", "hairdresser", "beauty"], "oferecer agendamento de horários 24h e mostrar fotos dos seus trabalhos"],
  [["oficina", "mecanic", "auto", "car_repair", "funilaria"], "receber pedidos de orçamento e mostrar os serviços para quem procura no Google"],
  [["imobiliar", "imoveis", "corretor", "estate"], "ter uma vitrine própria de imóveis, sem depender só dos portais"],
  [["advoga", "lawyer", "contab", "contador", "accountant"], "transmitir credibilidade e ser encontrado por quem procura esse serviço na região"],
  [["pet", "veterin"], "oferecer agendamento de banho e tosa e divulgar os serviços"],
  [["roupa", "moda", "loja", "boutique", "clothes", "calcado"], "ter um catálogo online e vender também pela internet"],
  [["constru", "reforma", "builder", "eletric", "encanador", "pintor"], "mostrar um portfólio de obras que gera confiança e pedidos de orçamento"],
];

function norm(s: string | null | undefined): string {
  return (s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

export function benefitFor(b: Business): string {
  const text = norm(`${b.category} ${b.name}`);
  for (const [keys, benefit] of SEGMENT_BENEFITS) if (keys.some((k) => text.includes(k))) return benefit;
  return "ser encontrado no Google por quem procura esse serviço na região e passar mais confiança";
}

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? "Bom dia" : h < 18 ? "Boa tarde" : "Boa noite";
}

function shortName(name: string): string {
  return name.replace(/^\[FICTÍCIO\]\s*/, "").replace(/\s+(ltda|me|eireli|epp)\.?$/i, "").trim();
}

function domainOf(url: string | null): string | null {
  if (!url) return null;
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

// Frase de contexto honesta para cada situação de presença digital.
function situation(b: Business): string {
  const name = shortName(b.name);
  if (b.digital_status === "SITE_INDISPONIVEL") {
    const d = domainOf(b.candidate_website || b.source_website) ?? "o site de vocês";
    return `Tentei acessar ${d}, o site de ${name}, e ele não está abrindo — quem procura vocês no Google pode acabar desistindo.`;
  }
  if (b.social_only) return `Encontrei ${name} nas redes sociais, mas não achei um site próprio de vocês.`;
  if (b.digital_status === "SEM_SITE_IDENTIFICADO") return `Pesquisei ${name} na internet e não encontrei um site próprio de vocês.`;
  if (b.digital_status === "SITE_NAO_INFORMADO_NO_MAPS") return `Encontrei ${name} no mapa e reparei que não aparece um site cadastrado.`;
  if (b.digital_status === "SITE_SUSPEITO") return `Procurei o site de ${name} e não consegui encontrar com facilidade o endereço oficial.`;
  if (b.digital_status === "POSSUI_SITE") return `Dei uma olhada no site de ${name} e tive algumas ideias para ele trazer mais clientes.`;
  return `Encontrei ${name} pesquisando empresas ${b.city ? `em ${b.city}` : "da região"}.`;
}

function praise(b: Business): string {
  if (b.rating && b.rating >= 4.5 && (b.reviews_count ?? 0) >= 20)
    return ` Vocês têm ótimas avaliações (${b.rating.toString().replace(".", ",")}★) — um site ajudaria a transformar essa reputação em mais clientes.`;
  return "";
}

const OPT_OUT = "Se não tiver interesse, é só me avisar que não envio mais mensagens. 🙂";

export function buildPitch(style: PitchStyle, b: Business, s: Sender): string {
  const me = [s.name, s.company && `da ${s.company}`].filter(Boolean).join(", ");
  const intro = `${greeting()}! Tudo bem? Aqui é ${me || "um profissional de criação de sites"}.`;
  const sit = situation(b);
  const benefit = benefitFor(b);
  const city = b.city ? ` em ${b.city}` : "";
  const what = b.digital_status === "POSSUI_SITE" ? "melhorar o site de vocês" : b.digital_status === "SITE_INDISPONIVEL" ? "colocar o site de vocês no ar de novo" : "criar um site para vocês";
  switch (style) {
    case "primeiro":
      return `${intro}\n\n${sit}${praise(b)}\n\nTrabalho ajudando negócios${city} a ${what}. Posso te mandar uma ideia de como ficaria, sem compromisso?\n\n${OPT_OUT}`;
    case "consultivo":
      return `${intro}\n\n${sit}\n\nHoje a maioria dos clientes pesquisa no Google antes de escolher. Com um site próprio dá para ${benefit}.${praise(b)}\n\nFaço isso de forma rápida e com preço acessível, já otimizado para celular e para aparecer no Google. Quer que eu prepare uma proposta para vocês?\n\n${OPT_OUT}`;
    case "portfolio":
      return `${intro}\n\n${sit}\n\nSeparei alguns sites que já fiz para negócios parecidos${s.portfolio ? `: ${s.portfolio}` : " (posso te mandar os links)"}.\n\nPara vocês, a ideia seria ${benefit}. Posso te explicar em 5 minutos como funcionaria?\n\n${OPT_OUT}`;
    case "followup":
      return `${greeting()}! Passando só para retomar minha mensagem sobre ${b.digital_status === "POSSUI_SITE" ? "o site" : "um site"} para ${shortName(b.name)}. Se fizer sentido, te mando um exemplo de como ficaria — sem compromisso.\n\n${OPT_OUT}`;
  }
}

// Número no formato do link wa.me (somente dígitos, com DDI). Retorna null se não houver telefone utilizável.
export function whatsappNumber(phone: string | null): string | null {
  if (!phone) return null;
  let d = phone.replace(/\D/g, "");
  if (!phone.trim().startsWith("+")) d = d.replace(/^0+/, "");
  if (d.length === 10 || d.length === 11) d = "55" + d;
  return d.length >= 12 ? d : null;
}

// Celular brasileiro tem 9 dígitos começando com 9 após o DDD; fixo dificilmente tem WhatsApp.
export function looksLikeMobile(waNumber: string): boolean {
  return !waNumber.startsWith("55") || (waNumber.length === 13 && waNumber[4] === "9");
}

export function whatsappLink(waNumber: string, text: string): string {
  return `https://wa.me/${waNumber}?text=${encodeURIComponent(text)}`;
}
