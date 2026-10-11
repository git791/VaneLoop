"use client"
import { useEffect, useRef, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"

export type ConnectionState = "live" | "reconnecting" | "stale"

interface StreamEvent {
  type: "tick" | "status_change" | "alert" | "heartbeat"
  unit?: number
  cycle?: number
  state?: string
  rul_p50?: number
  rul_p10?: number
  rul_p90?: number
  warmup?: boolean
  [key: string]: unknown
}

const API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000"
).replace(/\/$/, "")

const STALE_THRESHOLD_MS = 10_000
const RECONNECT_DELAY_MS = 3_000

/**
 * Opens an SSE connection to /api/v1/stream for the given dataset.
 * Merges status_change and tick events into the TanStack Query 'fleet' cache.
 * Exposes connection state: "live" | "reconnecting" | "stale".
 */
export function useFleetStream(dataset = "FD001") {
  const queryClient = useQueryClient()
  const [connection, setConnection] = useState<ConnectionState>("reconnecting")
  const lastTickRef = useRef<number>(0)
  const esRef = useRef<EventSource | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    let active = true
    lastTickRef.current = Date.now()

    function connect() {
      if (!active) return
      setConnection("reconnecting")

      const url = `${API_BASE}/api/v1/stream?dataset=${encodeURIComponent(dataset)}`
      const es = new EventSource(url)
      esRef.current = es

      es.addEventListener("tick", (event) => {
        if (!active) return
        lastTickRef.current = Date.now()
        setConnection("live")
        applyEvent(JSON.parse((event as MessageEvent).data) as StreamEvent)
      })

      es.addEventListener("status_change", (event) => {
        if (!active) return
        lastTickRef.current = Date.now()
        setConnection("live")
        applyEvent(JSON.parse((event as MessageEvent).data) as StreamEvent)
      })

      es.addEventListener("alert", () => {
        if (!active) return
        lastTickRef.current = Date.now()
        // Invalidate alerts list so the Alerts page refetches
        queryClient.invalidateQueries({ queryKey: ["alerts", dataset] })
      })

      es.addEventListener("heartbeat", () => {
        if (!active) return
        lastTickRef.current = Date.now()
        setConnection("live")
      })

      es.onerror = () => {
        if (!active) return
        es.close()
        esRef.current = null
        setConnection("reconnecting")
        reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS)
      }
    }

    function applyEvent(ev: StreamEvent) {
      if (!ev.unit) return
      
      queryClient.setQueryData(["fleet", dataset], (oldData: any) => {
        if (!oldData || !oldData.engines) return oldData
        
        const engines = [...oldData.engines]
        const idx = engines.findIndex((e: any) => e.unit === ev.unit)
        if (idx !== -1) {
          engines[idx] = { ...engines[idx], ...ev }
        }
        
        const counts = { nominal: 0, warning: 0, critical: 0 }
        for (const e of engines) {
          if (e.state === "Warning") counts.warning++
          else if (e.state === "Critical") counts.critical++
          else counts.nominal++
        }
        
        return { counts, engines }
      })

      // Update individual engine cache
      queryClient.setQueryData(["engine", dataset, ev.unit], (oldEngine: any) => {
        if (!oldEngine) return oldEngine
        return { ...oldEngine, ...ev }
      })
    }

    // Stale detection — if no tick in STALE_THRESHOLD_MS, mark stale
    const staleInterval = setInterval(() => {
      if (Date.now() - lastTickRef.current > STALE_THRESHOLD_MS) {
        setConnection((c) => (c === "live" ? "stale" : c))
      }
    }, 2_000)

    connect()

    return () => {
      active = false
      esRef.current?.close()
      esRef.current = null
      clearInterval(staleInterval)
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
    }
  }, [dataset, queryClient])

  return { connection }
}