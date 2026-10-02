"use client"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { useQuery } from "@tanstack/react-query"
import { fetchAlerts } from "@/lib/api"

export default function AlertsPage() {
  const { data: alerts = [], isLoading, isError } = useQuery({
    queryKey: ['alerts'],
    queryFn: fetchAlerts
  })

  if (isLoading) return <div className="p-4">Loading alerts...</div>
  if (isError) return <div className="p-4 text-status-critical">Error loading alerts</div>

  return (
    <div className="space-y-6 flex flex-col h-full">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Anomaly / Alerts Feed</h1>
        <p className="text-muted-foreground">Recent threshold breaches across the fleet.</p>
      </div>
      <div className="flex-1 overflow-auto rounded-md border border-border-hairline bg-bg-surface">
        <Table>
          <TableHeader className="bg-bg-surface-raised sticky top-0 z-10">
            <TableRow className="border-border-hairline">
              <TableHead className="w-[120px]">Severity</TableHead>
              <TableHead className="font-mono">Engine</TableHead>
              <TableHead className="font-mono">Sensor</TableHead>
              <TableHead className="font-mono text-right">Reading</TableHead>
              <TableHead className="font-mono text-right">Rule</TableHead>
              <TableHead className="text-right">Time</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {alerts.map((alert, i) => (
              <TableRow key={i} className={`border-border-hairline hover:bg-bg-surface-raised border-l-4 ${
                alert.severity === 'critical' ? 'border-l-status-critical' : 'border-l-status-warning'
              }`}>
                <TableCell>
                  <Badge variant="outline" className={
                    alert.severity === 'critical' 
                      ? 'text-status-critical border-status-critical/50 uppercase text-[10px] font-bold tracking-wider' 
                      : 'text-status-warning border-status-warning/50 uppercase text-[10px] font-bold tracking-wider'
                  }>
                    {alert.severity}
                  </Badge>
                </TableCell>
                <TableCell className="font-mono font-medium">{alert.engine}</TableCell>
                <TableCell className="font-mono text-muted-foreground">{alert.sensor}</TableCell>
                <TableCell className="font-mono text-right text-foreground">{alert.reading.toFixed(1)}</TableCell>
                <TableCell className="font-mono text-right text-muted-foreground">{alert.rule}</TableCell>
                <TableCell className="text-right text-muted-foreground text-sm">{alert.time}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
