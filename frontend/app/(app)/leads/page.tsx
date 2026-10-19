"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { ResultsTable } from "@/components/ResultsTable";
import { PageTitle } from "@/components/Shell";
import { Spinner } from "@/components/ui";

function Leads() {
  const sp = useSearchParams();
  const initial = Object.fromEntries(sp.entries());
  return (
    <>
      <PageTitle title="Resultados e leads" subtitle="Base persistente de empresas de todas as pesquisas, com classificação, evidências e status de prospecção." />
      <ResultsTable initial={initial} />
    </>
  );
}

export default function LeadsPage() {
  return <Suspense fallback={<Spinner />}><Leads /></Suspense>;
}
