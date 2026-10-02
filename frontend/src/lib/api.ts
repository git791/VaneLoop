export interface Engine {
  id: string;
  lastCycle: number;
  status: "nominal" | "warning" | "critical";
}

export interface Alert {
  engine: string;
  sensor: string;
  reading: number;
  rule: string;
  severity: "warning" | "critical";
  time: string;
}

export const fetchFleet = async (): Promise<Engine[]> => {
  const res = await fetch("/api/fleet");
  if (!res.ok) throw new Error("Failed to fetch fleet");
  return res.json();
};

export const fetchAlerts = async (): Promise<Alert[]> => {
  const res = await fetch("/api/alerts");
  if (!res.ok) throw new Error("Failed to fetch alerts");
  return res.json();
};
