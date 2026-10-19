"use client";

import L from "leaflet";
import { Circle, CircleMarker, MapContainer, Popup, TileLayer, useMapEvents } from "react-leaflet";
import Link from "next/link";
import { useEffect } from "react";
import type { DigitalStatus } from "@/lib/api";
import { STATUS } from "@/lib/labels";

export interface MapPoint {
  id: number;
  name: string;
  lat: number;
  lng: number;
  digital_status: DigitalStatus;
  lead_score: number;
  category: string | null;
  city: string | null;
  is_fictitious: boolean;
}

const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">colaboradores do OpenStreetMap</a>';
const TILE_URL = process.env.NEXT_PUBLIC_MAP_TILE_URL || "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";

function FitBounds({ points }: { points: MapPoint[] }) {
  const map = useMapEvents({});
  useEffect(() => {
    if (points.length) map.fitBounds(L.latLngBounds(points.map((p) => [p.lat, p.lng] as [number, number])), { padding: [30, 30], maxZoom: 15 });
  }, [points, map]);
  return null;
}

export default function MapView({ points }: { points: MapPoint[] }) {
  return (
    <MapContainer center={[-15.8, -47.9]} zoom={4} className="h-full w-full rounded-xl" scrollWheelZoom>
      <TileLayer url={TILE_URL} attribution={ATTRIBUTION} />
      <FitBounds points={points} />
      {points.map((p) => (
        <CircleMarker key={p.id} center={[p.lat, p.lng]} radius={7}
          pathOptions={{ color: "#fff", weight: 1.5, fillColor: STATUS[p.digital_status]?.color ?? "#6b7280", fillOpacity: 0.9 }}>
          <Popup>
            <div className="text-sm">
              <div className="font-semibold">{p.name}</div>
              <div className="text-gray-600">{p.category} · {p.city}</div>
              <div className="mt-1">{STATUS[p.digital_status]?.label} · pontuação {p.lead_score}</div>
              {p.is_fictitious && <div className="font-semibold text-orange-700">FICTÍCIO (demonstração)</div>}
              <Link href={`/leads/${p.id}`} className="mt-1 inline-block text-brand-600">Ver detalhes →</Link>
            </div>
          </Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}

function ClickHandler({ onPick }: { onPick: (lat: number, lng: number) => void }) {
  useMapEvents({ click: (e) => onPick(Number(e.latlng.lat.toFixed(6)), Number(e.latlng.lng.toFixed(6))) });
  return null;
}

export function MapPicker({ lat, lng, radiusKm, onPick }: { lat?: number; lng?: number; radiusKm?: number; onPick: (lat: number, lng: number) => void }) {
  const center: [number, number] = lat != null && lng != null ? [lat, lng] : [-15.8, -47.9];
  return (
    <MapContainer center={center} zoom={lat != null ? 12 : 4} className="h-72 w-full rounded-lg">
      <TileLayer url={TILE_URL} attribution={ATTRIBUTION} />
      <ClickHandler onPick={onPick} />
      {lat != null && lng != null && <Circle center={[lat, lng]} radius={(radiusKm ?? 2) * 1000} pathOptions={{ color: "#2f56d9" }} />}
    </MapContainer>
  );
}
