import { http, HttpResponse } from 'msw';
import { Engine, Alert } from '@/lib/api';

// Realistic FD001 fleet with 100 engines
const mockFleet: Engine[] = Array.from({ length: 100 }).map((_, i) => ({
  id: `FD001-${(i + 1).toString().padStart(3, "0")}`,
  lastCycle: Math.floor(Math.random() * 200) + 50,
  status: i % 15 === 0 ? "critical" : i % 5 === 0 ? "warning" : "nominal"
}));

// Real alerts for the realistic fleet
const mockAlerts: Alert[] = [
  { engine: "FD001-023", sensor: "T50", reading: 1612.3, rule: "R1", severity: "critical", time: "2m ago" },
  { engine: "FD001-008", sensor: "P30", reading: 39.8, rule: "R2", severity: "warning", time: "15m ago" },
  { engine: "FD001-042", sensor: "Nf", reading: 2391.1, rule: "R2", severity: "warning", time: "1h ago" },
  { engine: "FD001-011", sensor: "T24", reading: 645.2, rule: "R1", severity: "critical", time: "2h ago" },
  { engine: "FD001-067", sensor: "T50", reading: 1608.1, rule: "R1", severity: "critical", time: "5h ago" },
  { engine: "FD001-099", sensor: "P30", reading: 39.6, rule: "R2", severity: "warning", time: "6h ago" },
];

export const handlers = [
  http.get('/api/fleet', () => {
    return HttpResponse.json(mockFleet);
  }),
  http.get('/api/alerts', () => {
    return HttpResponse.json(mockAlerts);
  })
];
