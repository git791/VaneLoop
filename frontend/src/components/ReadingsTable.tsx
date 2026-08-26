"use client"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

export function ReadingsTable({ data }: { data: any[] }) {
  return (
    <div className="rounded-md border border-border-hairline overflow-hidden w-full h-full flex flex-col bg-bg-surface">
      <div className="overflow-auto flex-1">
        <Table>
          <TableHeader className="bg-bg-surface-raised sticky top-0">
            <TableRow className="border-border-hairline">
              <TableHead className="font-mono text-xs">Cycle</TableHead>
              <TableHead className="font-mono text-xs text-right">T24</TableHead>
              <TableHead className="font-mono text-xs text-right">T50</TableHead>
              <TableHead className="font-mono text-xs text-right">P30</TableHead>
              <TableHead className="font-mono text-xs text-right">Nf</TableHead>
              <TableHead className="font-mono text-xs text-center w-[60px]">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((row, i) => (
              <TableRow key={i} className="border-border-hairline hover:bg-bg-surface-raised transition-colors">
                <TableCell className="font-mono text-xs text-muted-foreground">{row.cycle}</TableCell>
                <TableCell className="font-mono text-xs text-right">{row.t24.toFixed(2)}</TableCell>
                <TableCell className="font-mono text-xs text-right">{row.t50.toFixed(2)}</TableCell>
                <TableCell className="font-mono text-xs text-right">{row.p30.toFixed(2)}</TableCell>
                <TableCell className="font-mono text-xs text-right">{row.nf.toFixed(2)}</TableCell>
                <TableCell className="text-center flex justify-center py-3">
                  <div className={`h-2 w-2 rounded-full ${
                    row.status === 'warning' ? 'bg-status-warning' 
                    : row.status === 'critical' ? 'bg-status-critical' 
                    : 'bg-status-nominal'
                  }`}></div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
