"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchFleet, displayEngineId, type EngineState } from "@/lib/api";
import { useDatasetStore } from "@/lib/useDatasetStore";

const STATES: Array<"" | EngineState> = ["", "Nominal", "Warning", "Critical"];
const STATUS_CLASS: Record<string, string> = { Nominal: "text-status-nominal", Warning: "text-status-warning", Critical: "text-status-critical" };

export default function FleetOverview() {
  const { dataset, setDataset } = useDatasetStore();
  const [state, setState] = useState("");
  const [sort, setSort] = useState("rul_asc");
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["fleet", dataset, state, sort],
    queryFn: () => fetchFleet(dataset, state || undefined, sort),
  });

  if (isLoading) return <p className="p-4" role="status">Loading replayed fleet data…</p>;
  if (isError || !data) return <button className="p-4 text-status-critical" onClick={() => refetch()}>Could not load the fleet. Retry</button>;
  const fleet = { counts: data.counts ?? { nominal: 0, warning: 0, critical: 0 }, engines: data.engines ?? [] };

  return <div className="space-y-6">
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div><h1 className="text-2xl font-bold tracking-tight">Fleet Overview</h1><p className="text-muted-foreground">Simulated NASA C-MAPSS replay; never for maintenance decisions.</p></div>
      <div className="flex gap-2">
        <label className="text-sm">Dataset <select value={dataset} onChange={(e) => setDataset(e.target.value)} className="ml-1 border bg-bg-surface p-2"><option>FD001</option><option>FD002</option><option>FD003</option><option>FD004</option></select></label>
        <label className="text-sm">State <select value={state} onChange={(e) => setState(e.target.value)} className="ml-1 border bg-bg-surface p-2">{STATES.map((item) => <option key={item} value={item}>{item || "All"}</option>)}</select></label>
        <label className="text-sm">Sort <select value={sort} onChange={(e) => setSort(e.target.value)} className="ml-1 border bg-bg-surface p-2"><option value="rul_asc">RUL ↑</option><option value="rul_desc">RUL ↓</option><option value="id">ID</option><option value="cycle">Cycle</option></select></label>
      </div>
    </div>
    {(dataset === "FD002" || dataset === "FD004") && <p className="border border-status-warning p-3 text-sm">This dataset has six operating conditions; comparisons use its replayed operating settings.</p>}
    <div className="grid gap-4 md:grid-cols-3 tabular-nums">
      {(["nominal", "warning", "critical"] as const).map((key) => <div key={key} className="border border-border-hairline bg-bg-surface p-4"><p className="text-sm capitalize">{key}</p><p className="font-mono text-2xl">{fleet.counts[key] ?? 0}</p></div>)}
    </div>
    {!fleet.engines.length ? <p className="border border-border-hairline p-6 text-muted-foreground">No replay state is available yet. Start the replayer after ingesting this dataset.</p> : <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8">
      {fleet.engines.map((engine) => <Link key={engine.unit} href={`/engine/${displayEngineId(engine.dataset, engine.unit)}`} className="border border-border-hairline bg-bg-surface p-4 transition-colors hover:bg-bg-surface-raised">
        <p className="font-mono font-bold">{displayEngineId(engine.dataset, engine.unit)}</p><p className={`mt-2 text-sm ${STATUS_CLASS[engine.state] ?? "text-status-nominal"}`}>● {engine.warmup ? "Warming up" : engine.state}</p><p className="mt-4 text-xs text-muted-foreground">Cycle</p><p className="font-mono text-lg">{engine.cycle}</p><p className="text-xs text-muted-foreground">RUL p50</p><p className="font-mono">{engine.rul_p50 === null ? "—" : engine.rul_p50 >= 125 ? "≥ 125" : engine.rul_p50.toFixed(1)}</p>
      </Link>)}
    </div>}
  </div>;
}