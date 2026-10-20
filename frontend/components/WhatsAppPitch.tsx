"use client";

import { Check, Copy, MessageCircle, Send } from "lucide-react";
import { useEffect, useState } from "react";
import type { Business } from "@/lib/api";
import { PITCH_STYLES, buildPitch, looksLikeMobile, whatsappLink, whatsappNumber, type PitchStyle, type Sender } from "@/lib/pitch";
import { Alert, Button, Card, CardHeader, Field, Input, cn } from "./ui";

const SENDER_KEY = "prospecia.sender";

function loadSender(defaultName: string): Sender {
  try {
    const raw = localStorage.getItem(SENDER_KEY);
    if (raw) return { name: defaultName, company: "", portfolio: "", ...JSON.parse(raw) };
  } catch {
    /* armazenamento indisponível: usa o padrão */
  }
  return { name: defaultName, company: "", portfolio: "" };
}

export function WhatsAppPitch({ business, defaultName, onSent }: {
  business: Business;
  defaultName: string;
  onSent: (text: string) => Promise<void>;
}) {
  const [style, setStyle] = useState<PitchStyle>("primeiro");
  const [sender, setSender] = useState<Sender>({ name: defaultName, company: "", portfolio: "" });
  const [text, setText] = useState("");
  const [editingSender, setEditingSender] = useState(false);
  const [copied, setCopied] = useState(false);
  const [opened, setOpened] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => setSender(loadSender(defaultName)), [defaultName]);
  useEffect(() => {
    setText(buildPitch(style, business, sender));
    setSaved(false);
  }, [style, business, sender]);

  function saveSender(next: Sender) {
    setSender(next);
    try {
      localStorage.setItem(SENDER_KEY, JSON.stringify(next));
    } catch {
      /* ignora */
    }
  }

  const wa = whatsappNumber(business.phone);
  const blocked = business.lead_status === "nao_contatar";

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* navegador sem permissão de área de transferência */
    }
  }

  async function markSent() {
    await onSent(text);
    setSaved(true);
    setOpened(false);
  }

  return (
    <Card>
      <CardHeader title={<span className="inline-flex items-center gap-2"><MessageCircle className="h-4 w-4 text-brand-400" /> Mensagem para WhatsApp</span>}
        subtitle="Sugestões personalizadas. Revise antes de enviar — o envio é sempre feito por você." />
      <div className="space-y-3 p-5">
        {blocked && <Alert tone="error">Esta empresa está marcada como “Não contatar”.</Alert>}
        <div className="flex flex-wrap gap-1.5">
          {PITCH_STYLES.map((p) => (
            <button key={p.key} onClick={() => setStyle(p.key)} title={p.hint}
              className={cn("rounded-full border px-3 py-1 text-xs font-medium", style === p.key ? "border-brand-500 bg-brand-500 text-black" : "border-neutral-700 text-neutral-300 hover:bg-neutral-800")}>
              {p.label}
            </button>
          ))}
        </div>

        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={9}
          className="w-full rounded-lg border border-neutral-700 bg-neutral-900 p-3 text-sm leading-relaxed text-neutral-100 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/25" />

        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" onClick={copy}>{copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />} {copied ? "Copiado!" : "Copiar"}</Button>
          {wa && !blocked && (
            <a href={whatsappLink(wa, text)} target="_blank" rel="noopener noreferrer" onClick={() => setOpened(true)}>
              <Button size="sm"><Send className="h-4 w-4" /> Abrir no WhatsApp</Button>
            </a>
          )}
          {(opened || copied) && !saved && !blocked && (
            <Button size="sm" variant="secondary" onClick={markSent}>Marcar como enviada</Button>
          )}
        </div>
        {saved && <Alert tone="success">Registrado no histórico e status atualizado para “Contato realizado”.</Alert>}
        {!wa && <p className="text-xs text-neutral-500">Sem telefone cadastrado: use “Copiar” e envie por outro canal.</p>}
        {wa && !looksLikeMobile(wa) && <p className="text-xs text-yellow-300">Este número parece ser fixo — talvez não tenha WhatsApp.</p>}

        <div className="border-t border-neutral-800 pt-3">
          <button className="text-xs text-brand-400 hover:underline" onClick={() => setEditingSender((v) => !v)}>
            {editingSender ? "Fechar" : "Editar sua assinatura (nome, empresa, portfólio)"}
          </button>
          {editingSender && (
            <div className="mt-2 grid gap-2">
              <Field label="Seu nome"><Input value={sender.name} onChange={(e) => saveSender({ ...sender, name: e.target.value })} /></Field>
              <Field label="Sua empresa"><Input value={sender.company} onChange={(e) => saveSender({ ...sender, company: e.target.value })} placeholder="ex.: Della Sites" /></Field>
              <Field label="Link do portfólio"><Input value={sender.portfolio} onChange={(e) => saveSender({ ...sender, portfolio: e.target.value })} placeholder="ex.: instagram.com/seuperfil" /></Field>
            </div>
          )}
        </div>
        <p className="text-xs text-neutral-500">Boas práticas: envie em horário comercial, uma mensagem por vez, e respeite quem pedir para não ser contatado (LGPD).</p>
      </div>
    </Card>
  );
}
