"use client"
import { type ConnectionState } from "@/lib/useFleetStream"
import { cn } from "@/lib/utils"

const LABELS: Record<ConnectionState, string> = {
  live: "Simulated data · live",
  reconnecting: "Simulated data · reconnecting",
  stale: "Simulated data · stale",
}

const DOT_CLASSES: Record<ConnectionState, string> = {
  live: "bg-status-nominal animate-pulse",
  reconnecting: "bg-status-warning",
  stale: "bg-muted-foreground",
}

export function ConnectionBadge({ connection }: { connection: ConnectionState }) {
  return (
    <div
      className="flex items-center gap-1.5 text-xs text-muted-foreground font-mono select-none"
      aria-live="polite"
      aria-label={LABELS[connection]}
    >
      {/* Icon + text — never color alone (WCAG requirement) */}
      <span
        className={cn("h-2 w-2 rounded-full flex-shrink-0", DOT_CLASSES[connection])}
        aria-hidden="true"
      />
      <span>{LABELS[connection]}</span>
    </div>
  )
}
