"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Alert, Button, Card, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState({ email: "", password: "", name: "", organization: "" });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (mode === "login") await api("/api/auth/login", { method: "POST", json: { email: form.email, password: form.password } });
      else await api("/api/auth/register", { method: "POST", json: form });
      router.replace("/");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-brand-900 to-brand-600 p-4">
      <Card className="w-full max-w-md p-8">
        <h1 className="text-2xl font-bold">Prospec<span className="text-brand-600">IA</span></h1>
        <p className="mt-1 text-sm text-gray-500">Encontre empresas sem site em fontes autorizadas, com evidências e nível de confiança.</p>
        <div className="mt-6 grid grid-cols-2 rounded-lg bg-gray-100 p-1 text-sm">
          {(["login", "register"] as const).map((m) => (
            <button key={m} onClick={() => setMode(m)} className={`rounded-md py-1.5 font-medium ${mode === m ? "bg-white shadow" : "text-gray-500"}`}>
              {m === "login" ? "Entrar" : "Criar conta"}
            </button>
          ))}
        </div>
        <form onSubmit={submit} className="mt-6 space-y-4">
          {mode === "register" && (
            <>
              <Field label="Organização"><Input required value={form.organization} onChange={set("organization")} placeholder="Minha agência" /></Field>
              <Field label="Seu nome"><Input required value={form.name} onChange={set("name")} /></Field>
            </>
          )}
          <Field label="E-mail"><Input type="email" required value={form.email} onChange={set("email")} autoComplete="email" /></Field>
          <Field label="Senha" hint={mode === "register" ? "Mínimo de 8 caracteres" : undefined}>
            <Input type="password" required minLength={mode === "register" ? 8 : 1} value={form.password} onChange={set("password")} autoComplete={mode === "login" ? "current-password" : "new-password"} />
          </Field>
          {error && <Alert tone="error">{error}</Alert>}
          <Button type="submit" className="w-full" loading={loading}>{mode === "login" ? "Entrar" : "Criar conta"}</Button>
        </form>
      </Card>
    </div>
  );
}
