"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { PageTitle } from "@/components/Shell";
import type { MapPoint } from "@/components/MapView";
import { Card, Input, Spinner, cn } from "@/components/ui";
import { api, qs } from "@/lib/api";
import { STATUS, STATUS_ORDER } from "@/lib/labels";

const MapView = dynamic(() => import("@/components/MapView"), { ssr: false, loading: () => <Spinner label="Carregando mapa..." /> });

export default function MapPage() {
  const [points, setPoints] = useState<MapPoint[] | null>(null);
  const [statuses, setStatuses] = useState<string[]>([]);
  const [city, setCity] = useState("");
  useEffect(() => {
    const t = setTimeout(() => api<MapPoint[]>(`/api/businesses/map${qs({ digital_status: statuses, city })}`).then(setPoints), 300);
    return () => clearTimeout(t);
  }, [statuses, city]);
  return (
    <>
      <PageTitle title="Mapa" subtitle="Empresas com coordenadas, coloridas pelo status da presença digital." />
      <Card className="mb-3 flex flex-wrap items-center gap-2 p-3">
        {STATUS_ORDER.map((s) => (
          <button key={s} onClick={() => setStatuses((x) => (x.includes(s) ? x.filter((y) => y !== s) : [...x, s]))}
            className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs", statuses.includes(s) ? "border-brand-500 bg-brand-500/15 text-brand-300" : "border-neutral-800")}>
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: STATUS[s].color }} /> {STATUS[s].label}
          </button>
        ))}
        <Input className="ml-auto w-56" placeholder="Filtrar por cidade" value={city} onChange={(e) => setCity(e.target.value)} />
        <span className="text-xs text-neutral-400">{points?.length ?? 0} no mapa</span>
      </Card>
      <div className="h-[70vh]">{points ? <MapView points={points} /> : <Spinner />}</div>
    </>
  );
}
