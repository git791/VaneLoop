import { SensorLineChart } from "@/components/SensorLineChart"
import { ReadingsTable } from "@/components/ReadingsTable"

export default async function EngineDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  
  // Mock data representing a single engine's recent cycle readings (Cassandra `engine_readings`)
  const mockReadings = Array.from({ length: 50 }).map((_, i) => {
    const cycle = 150 + i;
    // Simulate degradation trend
    const degradation = i * 0.05;
    return {
      cycle,
      t24: 641.82 + (Math.random() * 2) + degradation,
      t50: 1589.70 + (Math.random() * 10) + (degradation * 5),
      p30: 39.24 - (Math.random() * 0.5) - (degradation * 0.2),
      nf: 2388.02 + (Math.random() * 1),
      value: 641.82 + (Math.random() * 2) + degradation, // For the main chart
      status: i > 40 ? "critical" : i > 25 ? "warning" : "nominal"
    }
  }).reverse() // Most recent first for the table

  const chartData = [...mockReadings].reverse() // Chronological for the chart

  return (
    <div className="space-y-6 flex flex-col h-full">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Engine {id}</h1>
        <p className="text-muted-foreground font-mono text-sm mt-1">partition: engine_id = {id}</p>
      </div>
      
      <div className="grid gap-6 md:grid-cols-2 flex-1">
        <div className="flex flex-col space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">T24 Sensor Trend</h2>
          <div className="flex-1 min-h-[300px] border border-border-hairline p-4 bg-bg-surface">
            <SensorLineChart data={chartData} />
          </div>
        </div>
        
        <div className="flex flex-col space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Recent Readings</h2>
          <div className="flex-1 min-h-[300px] max-h-[500px]">
            <ReadingsTable data={mockReadings} />
          </div>
        </div>
      </div>
    </div>
  )
}
