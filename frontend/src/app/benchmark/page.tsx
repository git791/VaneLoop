"use client";

import { useQuery } from "@tanstack/react-query";
import { BenchmarkBarChart } from "@/components/BenchmarkBarChart";
import { fetchBenchmarks } from "@/lib/api";
import { Activity, Zap } from "lucide-react";

export default function BenchmarkPage() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["benchmarks"],
    queryFn: fetchBenchmarks,
  });

  if (isLoading) {
    return <p className="p-6" role="status">Loading benchmark performance results…</p>;
  }

  if (isError || !data) {
    return (
      <div className="p-6 space-y-3">
        <p className="text-status-critical">Could not load benchmark results.</p>
        <button
          onClick={() => refetch()}
          className="px-3 py-1.5 border border-border-hairline bg-bg-surface hover:bg-bg-surface-raised"
        >
          Retry
        </button>
      </div>
    );
  }

  const benchmarks = data.benchmarks ?? [];

  const latencyData = benchmarks.map((b) => ({
    name: b.dataset,
    latency_ms: b.latency_ms,
  }));

  const accuracyData = benchmarks.map((b) => ({
    name: b.dataset,
    accuracy: Number((b.accuracy * 100).toFixed(1)),
  }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Benchmark &amp; Performance</h1>
        <p className="text-muted-foreground">
          Committed performance and accuracy benchmarks across NASA C-MAPSS subsets (FD001–FD004).
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Latency Comparison */}
        <section className="space-y-2 border border-border-hairline bg-bg-surface p-4 rounded-md">
          <div className="flex items-center gap-2">
            <Zap className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              End-to-End Latency by Dataset (ms)
            </h2>
          </div>
          <div className="h-72">
            <BenchmarkBarChart
              data={latencyData}
              dataKey="latency_ms"
              name="Latency (ms)"
              color="var(--color-primary)"
            />
          </div>
        </section>

        {/* Model Accuracy Comparison */}
        <section className="space-y-2 border border-border-hairline bg-bg-surface p-4 rounded-md">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-emerald-500" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              RUL Classification Accuracy (%)
            </h2>
          </div>
          <div className="h-72">
            <BenchmarkBarChart
              data={accuracyData}
              dataKey="accuracy"
              name="Accuracy (%)"
              color="#10b981"
            />
          </div>
        </section>
      </div>

      {/* Committed Results Table */}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Committed Verification Runs
        </h2>
        <div className="overflow-auto border border-border-hairline bg-bg-surface rounded-md">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-border-hairline bg-bg-surface-raised">
                <th className="p-3">Dataset</th>
                <th className="p-3">Accuracy</th>
                <th className="p-3">RMSE (cycles)</th>
                <th className="p-3">80% Coverage</th>
                <th className="p-3">NASA Score</th>
                <th className="p-3">Latency (ms)</th>
                <th className="p-3">Rows Ingested</th>
                <th className="p-3">Recorded Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {benchmarks.map((b) => (
                <tr key={b.dataset} className="border-b border-border-hairline">
                  <td className="p-3 font-mono font-bold">{b.dataset}</td>
                  <td className="p-3 font-mono">{(b.accuracy * 100).toFixed(1)}%</td>
                  <td className="p-3 font-mono">{b.rmse !== undefined ? b.rmse.toFixed(2) : "—"}</td>
                  <td className="p-3 font-mono">
                    {b.coverage_80 !== undefined ? `${(b.coverage_80 * 100).toFixed(1)}%` : "—"}
                  </td>
                  <td className="p-3 font-mono">
                    {b.nasa_score !== undefined ? b.nasa_score.toFixed(1) : "—"}
                  </td>
                  <td className="p-3 font-mono">{b.latency_ms} ms</td>
                  <td className="p-3 font-mono">{b.rows_inserted ?? "—"}</td>
                  <td className="p-3 font-mono text-muted-foreground">{b.timestamp}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Methodology note */}
      <div className="border border-border-hairline bg-bg-surface p-4 rounded-md text-xs text-muted-foreground space-y-1">
        <p className="font-semibold text-foreground">Benchmark Methodology &amp; Constraints</p>
        <p>
          Tests evaluate batch ingestion throughput and cold-path retrieval latency over NASA C-MAPSS run-to-failure series.
          All numbers are read from reproducible test run logs stored in the repository.
        </p>
      </div>
    </div>
  );
}
