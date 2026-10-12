"use client";

import { type Reading } from "@/lib/api";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export function ReadingsTable({ data }: { data: Reading[] }) {
  return (
    <div className="h-full w-full overflow-auto rounded-md border border-border-hairline bg-bg-surface">
      <Table>
        <TableHeader className="sticky top-0 bg-bg-surface-raised">
          <TableRow>
            <TableHead>Cycle</TableHead>
            <TableHead className="text-right">LPC Temp T24 (°R)</TableHead>
            <TableHead className="text-right">Exhaust Temp T50 (°R)</TableHead>
            <TableHead className="text-right">HPC Pressure P30 (psia)</TableHead>
            <TableHead className="text-right">Fan Speed Nf (RPM)</TableHead>
            <TableHead className="text-right">True RUL</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((row) => (
            <TableRow key={row.cycle}>
              <TableCell className="font-mono">{row.cycle}</TableCell>
              <TableCell className="text-right font-mono">{row.s2.toFixed(2)}</TableCell>
              <TableCell className="text-right font-mono">{row.s4.toFixed(2)}</TableCell>
              <TableCell className="text-right font-mono">{row.s7.toFixed(2)}</TableCell>
              <TableCell className="text-right font-mono">{row.s8.toFixed(2)}</TableCell>
              <TableCell className="text-right font-mono">
                {row.rul_true === null ? "—" : row.rul_true >= 125 ? "≥ 125" : row.rul_true}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
