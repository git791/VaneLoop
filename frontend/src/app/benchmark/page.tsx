import { BenchmarkBarChart } from "@/components/BenchmarkBarChart"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

export default function BenchmarkPage() {
  const latencyData = [
    { name: "By Engine", latency: 45 },
    { name: "By Sensor", latency: 12 },
  ]
  
  const cacheData = [
    { name: "Direct Cassandra", latency: 120 },
    { name: "Redis Cache", latency: 8 },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Benchmark & Performance</h1>
        <p className="text-muted-foreground">Latency comparison: Redis-cached vs Direct-Cassandra.</p>
      </div>
      
      <div className="grid gap-6 md:grid-cols-2">
        <Card className="bg-bg-surface border-border-hairline shadow-none">
          <CardHeader>
            <CardTitle className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
              Sensor Query Latency (ms)
            </CardTitle>
          </CardHeader>
          <CardContent className="h-72">
            <BenchmarkBarChart data={latencyData} dataKey="latency" name="Latency (ms)" color="var(--color-primary)" />
          </CardContent>
        </Card>

        <Card className="bg-bg-surface border-border-hairline shadow-none">
          <CardHeader>
            <CardTitle className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
              Dashboard Load Time (ms)
            </CardTitle>
          </CardHeader>
          <CardContent className="h-72">
            <BenchmarkBarChart data={cacheData} dataKey="latency" name="Load Time (ms)" color="var(--color-secondary)" />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
