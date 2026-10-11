"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { displayEngineId, fetchAlerts } from "@/lib/api";
import { useDatasetStore } from "@/lib/useDatasetStore";
import { AlertTriangle, AlertOctagon } from "lucide-react";

export default function AlertsPage() {
  const { dataset, setDataset } = useDatasetStore();
  const [severityFilter, setSeverityFilter] = useState<string>("");

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["alerts", dataset],
    queryFn: () => fetchAlerts(dataset),
  });

  if (isLoading) return <p className="p-4" role="status">Loading replay alerts…</p>;
  if (isError || !data) return <button onClick={() => refetch()} className="p-4 text-status-critical">Could not load alerts. Retry</button>;

  const alerts = data.alerts.filter((a) =>
    severityFilter ? a.severity.toLowerCase() === severityFilter.toLowerCase() : true
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Alerts</h1>
          <p className="text-muted-foreground">
            Replay-clock alerts, derived from status transitions and per-engine sensor drift.
          </p>
        </div>
        <div className="flex gap-2">
          <label className="text-sm">
            Dataset{" "}
            <select
              value={dataset}
              onChange={(e) => setDataset(e.target.value)}
              className="ml-1 border bg-bg-surface p-2"
            >
              <option>FD001</option>
              <option>FD002</option>
              <option>FD003</option>
              <option>FD004</option>
            </select>
          </label>
          <label className="text-sm">
            Severity{" "}
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="ml-1 border bg-bg-surface p-2"
            >
              <option value="">All</option>
              <option value="Warning">Warning</option>
              <option value="Critical">Critical</option>
            </select>
          </label>
        </div>
      </div>

      {!alerts.length ? (
        <p className="border border-border-hairline p-6 text-muted-foreground">
          No alerts recorded for dataset {dataset}.
        </p>
      ) : (
        <div className="overflow-auto border border-border-hairline bg-bg-surface">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b bg-bg-surface-raised">
                <th className="p-3">Severity</th>
                <th>Engine</th>
                <th>Cycle</th>
                <th>Rule</th>
                <th>Sensor</th>
                <th>Message</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((alert, idx) => {
                const isCrit = alert.severity === "Critical";
                return (
                  <tr
                    key={`${alert.unit}-${alert.cycle}-${alert.rule}-${alert.sensor ?? ""}-${idx}`}
                    className="border-b border-border-hairline hover:bg-bg-surface-raised transition-colors"
                  >
                    <td className="p-3">
                      <span
                        className={`inline-flex items-center gap-1.5 font-medium ${
                          isCrit ? "text-status-critical" : "text-status-warning"
                        }`}
                      >
                        {isCrit ? (
                          <AlertOctagon className="h-4 w-4" />
                        ) : (
                          <AlertTriangle className="h-4 w-4" />
                        )}
                        {alert.severity}
                      </span>
                    </td>
                    <td>
                      <Link
                        className="font-mono font-medium underline hover:text-primary"
                        href={`/engine/${displayEngineId(dataset, alert.unit)}`}
                      >
                        {displayEngineId(dataset, alert.unit)}
                      </Link>
                    </td>
                    <td className="font-mono">{alert.cycle}</td>
                    <td>
                      <span className="rounded bg-bg-canvas px-1.5 py-0.5 font-mono text-xs border border-border-hairline">
                        {alert.rule}
                      </span>
                    </td>
                    <td>{alert.sensor ?? "—"}</td>
                    <td className="text-muted-foreground">{alert.message}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
