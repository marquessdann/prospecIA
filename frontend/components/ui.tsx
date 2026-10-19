"use client";

import clsx from "clsx";
import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

export function cn(...args: Parameters<typeof clsx>) {
  return clsx(...args);
}

type Variant = "primary" | "secondary" | "ghost" | "danger";

export function Button({
  variant = "primary",
  size = "md",
  loading,
  className,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md"; loading?: boolean }) {
  return (
    <button
      {...props}
      disabled={props.disabled || loading}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "px-2.5 py-1.5 text-xs" : "px-3.5 py-2 text-sm",
        variant === "primary" && "bg-brand-600 text-white hover:bg-brand-700",
        variant === "secondary" && "border border-gray-300 bg-white text-gray-800 hover:bg-gray-50",
        variant === "ghost" && "text-gray-700 hover:bg-gray-100",
        variant === "danger" && "bg-red-600 text-white hover:bg-red-700",
        className,
      )}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  );
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("rounded-xl border border-gray-200 bg-white shadow-sm", className)}>{children}</div>;
}

export function CardHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-gray-100 px-5 py-4">
      <div>
        <h2 className="text-base font-semibold text-gray-900">{title}</h2>
        {subtitle && <p className="mt-0.5 text-sm text-gray-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Badge({ className, children, title }: { className?: string; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={cn("inline-flex items-center gap-1 whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ring-transparent", className)}>
      {children}
    </span>
  );
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={cn(
        "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100",
        className,
      )}
    />
  );
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={cn(
        "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100",
        className,
      )}
    >
      {children}
    </select>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-gray-500">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-gray-400">{hint}</span>}
    </label>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-gray-500">
      <Loader2 className="h-5 w-5 animate-spin" /> {label ?? "Carregando..."}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      <p className="text-sm font-medium text-gray-700">{title}</p>
      {children && <div className="max-w-md text-sm text-gray-500">{children}</div>}
    </div>
  );
}

export function Alert({ tone = "info", children }: { tone?: "info" | "warning" | "error" | "success"; children: ReactNode }) {
  return (
    <div
      className={cn(
        "rounded-lg border px-4 py-3 text-sm",
        tone === "info" && "border-blue-200 bg-blue-50 text-blue-900",
        tone === "warning" && "border-yellow-200 bg-yellow-50 text-yellow-900",
        tone === "error" && "border-red-200 bg-red-50 text-red-900",
        tone === "success" && "border-green-200 bg-green-50 text-green-900",
      )}
    >
      {children}
    </div>
  );
}

export function Checkbox({ label, checked, onChange, hint }: { label: ReactNode; checked: boolean; onChange: (v: boolean) => void; hint?: string }) {
  return (
    <label className="flex cursor-pointer items-start gap-2 text-sm text-gray-800">
      <input type="checkbox" className="mt-0.5 h-4 w-4 rounded border-gray-300 text-brand-600" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>
        {label}
        {hint && <span className="block text-xs text-gray-500">{hint}</span>}
      </span>
    </label>
  );
}
