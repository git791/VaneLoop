export type EngineState = "Nominal" | "Warning" | "Critical";

export interface EngineStatus {
  dataset: string;
  unit: number;
  cycle: number;
  state: EngineState;
  rul_p10: number | null;
  rul_p50: number | null;
  rul_p90: number | null;
  health_index: number | null;
  warmup: boolean;
  model_version: string | null;
  updated_at: string | null;
}

export interface FleetResponse {
  counts: { nominal: number; warning: number; critical: number };
  engines: EngineStatus[];
}

export interface Reading {
  cycle: number;
  op1: number;
  op2: number;
  op3: number;
  s1: number; s2: number; s3: number; s4: number; s5: number; s6: number; s7: number;
  s8: number; s9: number; s10: number; s11: number; s12: number; s13: number; s14: number;
  s15: number; s16: number; s17: number; s18: number; s19: number; s20: number; s21: number;
  rul_true: number | null;
}

export interface AlertItem {
  unit: number;
  cycle: number;
  rule: string;
  severity: EngineState;
  sensor: string | null;
  message: string;
}

export type Prediction = EngineStatus;

const API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? 
  process.env.NEXT_PUBLIC_API_URL ?? 
  "http://localhost:8000"
).replace(/\/$/, "");

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`API request failed (${response.status})`);
  return response.json() as Promise<T>;
}

export const displayEngineId = (dataset: string, unit: number) => `${dataset}-${String(unit).padStart(3, "0")}`;

export function parseEngineId(id: string): { dataset: string; unit: number } | null {
  const match = /^(FD00[1-4])-(\d{3})$/.exec(id);
  return match ? { dataset: match[1], unit: Number(match[2]) } : null;
}

export const fetchFleet = (dataset: string, state?: string, sort = "rul_asc") => {
  const query = new URLSearchParams({ dataset, sort });
  if (state) query.set("state", state);
  return request<FleetResponse>(`/api/v1/fleet?${query}`);
};

export const fetchEngine = (dataset: string, unit: number) => request<EngineStatus>(`/api/v1/engines/${dataset}/${unit}`);
export const fetchReadings = (dataset: string, unit: number) => request<{ readings: Reading[] }>(`/api/v1/engines/${dataset}/${unit}/readings?limit=200`);
export const fetchPredictions = (dataset: string, unit: number) => request<{ predictions: Prediction[] }>(`/api/v1/engines/${dataset}/${unit}/rul`);
export const fetchAlerts = (dataset: string) => request<{ alerts: AlertItem[] }>(`/api/v1/alerts?dataset=${dataset}`);

export interface BenchmarkResult {
  dataset: string;
  accuracy: number;
  latency_ms: number;
  cold_path_latency_ms?: number;
  rmse?: number;
  coverage_80?: number;
  nasa_score?: number;
  rows_inserted?: number;
  time_taken?: number;
  memory_usage_mb?: number;
  timestamp: string;
}

export const fetchBenchmarks = () => request<{ benchmarks: BenchmarkResult[] }>("/api/v1/benchmarks");
