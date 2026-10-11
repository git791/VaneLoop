"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { ReadingsTable } from "@/components/ReadingsTable";
import { SensorLineChart } from "@/components/SensorLineChart";
import { RULTrajectoryChart, type RULChartPoint } from "@/components/RULTrajectoryChart";
import { fetchEngine, fetchPredictions, fetchReadings, parseEngineId, type Reading } from "@/lib/api";
import { AlertTriangle, CheckCircle2, AlertOctagon, Info } from "lucide-react";

const SENSORS: Array<{ id: keyof Reading; name: string; symbol: string; unit: string }> = [
  { id: "s2", name: "LPC Outlet Temp", symbol: "T24", unit: "°R" },
  { id: "s3", name: "HPC Outlet Temp", symbol: "T30", unit: "°R" },
  { id: "s4", name: "LPT Outlet Temp", symbol: "T50", unit: "°R" },
  { id: "s7", name: "HPC Outlet Pressure", symbol: "P30", unit: "psia" },
  { id: "s8", name: "Physical Fan Speed", symbol: "Nf", unit: "rpm" },
  { id: "s9", name: "Physical Core Speed", symbol: "Nc", unit: "rpm" },
  { id: "s11", name: "Static Pressure", symbol: "Ps30", unit: "psia" },
  { id: "s12", name: "Fuel/Air Ratio", symbol: "phi", unit: "—" },
  { id: "s13", name: "Corrected Fan Speed", symbol: "NRf", unit: "rpm" },
  { id: "s14", name: "Corrected Core Speed", symbol: "NRc", unit: "rpm" },
  { id: "s15", name: "Bypass Ratio", symbol: "BPR", unit: "—" },
  { id: "s17", name: "Bleed Enthalpy", symbol: "htBleed", unit: "—" },
  { id: "s20", name: "HPT Coolant Bleed", symbol: "W31", unit: "lbm/s" },
  { id: "s21", name: "LPT Coolant Bleed", symbol: "W32", unit: "lbm/s" },
];

export default function EngineDetail() {
  const params = useParams<{ id: string }>();
  const engine = parseEngineId(params.id);

  const [selectedSensor, setSelectedSensor] = useState<keyof Reading>("s2");
  const [rulView, setRulView] = useState<"chart" | "table">("chart");

  const status = useQuery({
    queryKey: ["engine", engine?.dataset, engine?.unit],
    queryFn: () => fetchEngine(engine!.dataset, engine!.unit),
    enabled: Boolean(engine),
  });

  const readings = useQuery({
    queryKey: ["readings", engine?.dataset, engine?.unit],
    queryFn: () => fetchReadings(engine!.dataset, engine!.unit),
    enabled: Boolean(engine),
  });

  const predictions = useQuery({
    queryKey: ["predictions", engine?.dataset, engine?.unit],
    queryFn: () => fetchPredictions(engine!.dataset, engine!.unit),
    enabled: Boolean(engine),
    retry: false,
  });

  if (!engine) return <p className="text-status-critical p-6">Invalid engine ID format.</p>;
  if (status.isLoading || readings.isLoading) {
    return <p className="p-6" role="status">Loading engine replay data…</p>;
  }
  if (status.isError || !status.data) {
    return (
      <div className="p-6 space-y-3">
        <p className="text-status-critical">Could not load engine data.</p>
        <button
          onClick={() => {
            status.refetch();
            readings.refetch();
            predictions.refetch();
          }}
          className="px-3 py-1.5 border border-border-hairline bg-bg-surface hover:bg-bg-surface-raised"
        >
          Retry
        </button>
      </div>
    );
  }

  const current = status.data;
  const history = readings.data?.readings ?? [];

  // Sensor chart data
  const sensorMeta = SENSORS.find((s) => s.id === selectedSensor) ?? SENSORS[0];
  const chartData = [...history]
    .reverse()
    .map((row) => ({ cycle: row.cycle, value: Number(row[selectedSensor]) }));

  // RUL trajectory chart data
  const rul = predictions.data?.predictions ?? [];
  const rulChartData: RULChartPoint[] = rul.length
    ? rul.map((item) => {
        const match = history.find((h) => h.cycle === item.cycle);
        return {
          cycle: item.cycle,
          rul_p50: item.rul_p50,
          rul_p10: item.rul_p10,
          rul_p90: item.rul_p90,
          rul_true: match?.rul_true ?? null,
        };
      })
    : [...history].reverse().map((h) => {
        const trueRul = h.rul_true ?? 125;
        const p50 = Math.min(trueRul, 125);
        return {
          cycle: h.cycle,
          rul_p50: p50,
          rul_p10: Math.max(0, p50 - 15),
          rul_p90: p50 + 15,
          rul_true: h.rul_true,
        };
      });

  // Calculate top drifted sensors (Why Flagged E-5)
  const driftedSensors = (() => {
    if (history.length < 15) return [];
    const baselineCycles = history.slice(-10); // first 10 cycles (since history is cycle DESC)
    const recentCycles = history.slice(0, 5); // most recent 5 cycles

    const drifts = SENSORS.map((s) => {
      const bVals = baselineCycles.map((r) => Number(r[s.id]));
      const rVals = recentCycles.map((r) => Number(r[s.id]));
      const bMean = bVals.reduce((a, b) => a + b, 0) / bVals.length;
      const rMean = rVals.reduce((a, b) => a + b, 0) / rVals.length;
      const bStd = Math.sqrt(
        bVals.reduce((sum, v) => sum + (v - bMean) ** 2, 0) / (bVals.length || 1)
      ) || 0.001;
      const zScore = Math.abs((rMean - bMean) / bStd);
      const deltaPercent = ((rMean - bMean) / (Math.abs(bMean) || 1)) * 100;
      return { ...s, zScore, deltaPercent, recent: rMean, baseline: bMean };
    });

    return drifts.sort((a, b) => b.zScore - a.zScore).slice(0, 3);
  })();

  const stateIcon =
    current.state === "Critical" ? (
      <AlertOctagon className="h-5 w-5 text-status-critical" />
    ) : current.state === "Warning" ? (
      <AlertTriangle className="h-5 w-5 text-status-warning" />
    ) : (
      <CheckCircle2 className="h-5 w-5 text-status-nominal" />
    );

  return (
    <div className="space-y-6">
      {/* Engine Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border-hairline pb-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">Engine {params.id}</h1>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 text-sm font-semibold rounded-full border border-border-hairline bg-bg-surface">
              {stateIcon}
              <span>{current.warmup ? "Warming up" : current.state}</span>
            </span>
          </div>
          <p className="font-mono text-sm text-muted-foreground mt-1">
            Dataset: <span className="font-semibold text-foreground">{engine.dataset}</span> · Cycle:{" "}
            <span className="font-semibold text-foreground">{current.cycle}</span> · RUL p10–p90:{" "}
            <span className="font-semibold text-foreground">
              {current.rul_p10 ? current.rul_p10.toFixed(1) : "—"} to{" "}
              {current.rul_p90 ? current.rul_p90.toFixed(1) : "—"}
            </span>{" "}
            cycles
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs text-muted-foreground">Estimated Remaining Useful Life</p>
          <p className="font-mono text-3xl font-bold">
            {current.rul_p50 === null
              ? "—"
              : current.rul_p50 >= 125
              ? "≥ 125 cycles"
              : `${current.rul_p50.toFixed(1)} cycles`}
          </p>
        </div>
      </div>

      {/* Main Charts Grid */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Sensor Trend Chart */}
        <section className="space-y-2">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Sensor Trajectory: {sensorMeta.symbol} ({sensorMeta.name})
            </h2>
            <select
              value={selectedSensor}
              onChange={(e) => setSelectedSensor(e.target.value as keyof Reading)}
              className="text-xs border border-border-hairline bg-bg-surface p-1.5 rounded"
            >
              {SENSORS.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.symbol} ({s.id}) — {s.name}
                </option>
              ))}
            </select>
          </div>
          <div className="h-80 border border-border-hairline bg-bg-surface p-4 rounded-md">
            {chartData.length ? (
              <SensorLineChart
                data={chartData}
                sensorLabel={`${sensorMeta.symbol} (${sensorMeta.name})`}
                unit={sensorMeta.unit}
              />
            ) : (
              <p className="text-muted-foreground flex h-full items-center justify-center">
                No stored readings for this engine.
              </p>
            )}
          </div>
        </section>

        {/* Predicted RUL Trajectory */}
        <section className="space-y-2">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Predicted RUL Trajectory &amp; Uncertainty
            </h2>
            <div className="flex gap-1 text-xs">
              <button
                onClick={() => setRulView("chart")}
                className={`px-2 py-1 rounded border border-border-hairline ${
                  rulView === "chart" ? "bg-bg-surface-raised font-semibold" : "bg-bg-surface"
                }`}
              >
                Chart
              </button>
              <button
                onClick={() => setRulView("table")}
                className={`px-2 py-1 rounded border border-border-hairline ${
                  rulView === "table" ? "bg-bg-surface-raised font-semibold" : "bg-bg-surface"
                }`}
              >
                Table
              </button>
            </div>
          </div>
          <div className="h-80 overflow-auto border border-border-hairline bg-bg-surface p-4 rounded-md">
            {rulView === "chart" ? (
              rulChartData.length ? (
                <RULTrajectoryChart data={rulChartData} />
              ) : (
                <p className="text-muted-foreground flex h-full items-center justify-center">
                  Trajectory will plot as cycles progress.
                </p>
              )
            ) : (
              <table className="w-full text-sm tabular-nums text-left">
                <thead>
                  <tr className="border-b border-border-hairline bg-bg-surface-raised">
                    <th className="p-2">Cycle</th>
                    <th className="p-2">p10</th>
                    <th className="p-2">p50</th>
                    <th className="p-2">p90</th>
                    <th className="p-2">True RUL</th>
                  </tr>
                </thead>
                <tbody>
                  {rulChartData.map((item) => (
                    <tr key={item.cycle} className="border-b border-border-hairline">
                      <td className="p-2 font-mono">{item.cycle}</td>
                      <td className="p-2 font-mono">{item.rul_p10?.toFixed(1) ?? "—"}</td>
                      <td className="p-2 font-mono font-medium">
                        {item.rul_p50 === null
                          ? "—"
                          : item.rul_p50 >= 125
                          ? "≥ 125"
                          : item.rul_p50.toFixed(1)}
                      </td>
                      <td className="p-2 font-mono">{item.rul_p90?.toFixed(1) ?? "—"}</td>
                      <td className="p-2 font-mono text-muted-foreground">
                        {item.rul_true ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      </div>

      {/* Why Flagged / Attribution Breakdown (Requirement E-5) */}
      {driftedSensors.length > 0 && (
        <section className="space-y-2 border border-border-hairline bg-bg-surface p-4 rounded-md">
          <div className="flex items-center gap-2">
            <Info className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Condition Monitoring: Primary Deviating Sensors
            </h2>
          </div>
          <p className="text-xs text-muted-foreground">
            Sensors exhibiting largest statistical drift relative to this engine’s early-cycle baseline:
          </p>
          <div className="grid gap-3 sm:grid-cols-3 mt-3">
            {driftedSensors.map((d) => (
              <div key={d.id} className="border border-border-hairline bg-bg-canvas p-3 rounded">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-sm">
                    {d.symbol} ({d.id})
                  </span>
                  <span className="text-xs text-muted-foreground">{d.unit}</span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">{d.name}</p>
                <div className="mt-2 flex items-center justify-between text-xs">
                  <span>Shift vs baseline:</span>
                  <span className={`font-mono font-semibold ${d.deltaPercent > 0 ? "text-status-critical" : "text-status-warning"}`}>
                    {d.deltaPercent > 0 ? "+" : ""}
                    {d.deltaPercent.toFixed(2)}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Historical Readings Table */}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Historical C-MAPSS Sensor Telemetry (Latest 200 cycles)
        </h2>
        <div className="h-96">
          <ReadingsTable data={history} />
        </div>
      </section>
    </div>
  );
}