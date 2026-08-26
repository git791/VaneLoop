import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

export default function FleetOverview() {
  // Mock data for the training set (FD001)
  const engines = Array.from({ length: 24 }).map((_, i) => ({
    id: `FD001-${(i + 1).toString().padStart(3, "0")}`,
    lastCycle: Math.floor(Math.random() * 200) + 50,
    status: i % 7 === 0 ? "critical" : i % 4 === 0 ? "warning" : "nominal"
  }))

  const nominalCount = engines.filter(e => e.status === "nominal").length
  const warningCount = engines.filter(e => e.status === "warning").length
  const criticalCount = engines.filter(e => e.status === "critical").length

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Fleet Overview</h1>
        <p className="text-muted-foreground">Monitor real-time engine health and sensor degradation.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card className="bg-bg-surface border-border-hairline shadow-none">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Nominal Engines</CardTitle>
            <div className="h-3 w-3 rounded-full bg-status-nominal"></div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{nominalCount}</div>
          </CardContent>
        </Card>
        <Card className="bg-bg-surface border-border-hairline shadow-none">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Warning State</CardTitle>
            <div className="h-3 w-3 rounded-full bg-status-warning"></div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{warningCount}</div>
          </CardContent>
        </Card>
        <Card className="bg-bg-surface border-border-hairline shadow-none">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Critical State</CardTitle>
            <div className="h-3 w-3 rounded-full bg-status-critical"></div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{criticalCount}</div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8">
        {engines.map((engine) => (
          <a
            key={engine.id}
            href={`/engine/${engine.id}`}
            className="group flex flex-col p-4 border border-border-hairline bg-bg-surface hover:bg-bg-surface-raised transition-colors"
          >
            <div className="flex justify-between items-start mb-4">
              <span className="font-mono text-sm font-bold">{engine.id}</span>
              <div 
                className={`h-2 w-2 rounded-full mt-1 ${
                  engine.status === "nominal" ? "bg-status-nominal" 
                  : engine.status === "warning" ? "bg-status-warning" 
                  : "bg-status-critical"
                }`}
              />
            </div>
            <div className="mt-auto">
              <div className="text-xs text-muted-foreground mb-1">Cycle</div>
              <div className="font-mono text-lg">{engine.lastCycle}</div>
            </div>
          </a>
        ))}
      </div>
    </div>
  )
}
