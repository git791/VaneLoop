"use client"
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts"
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart"

export function BenchmarkBarChart({ data, dataKey, name, color }: { data: any[], dataKey: string, name: string, color: string }) {
  const chartConfig = {
    [dataKey]: {
      label: name,
      color: color,
    }
  }

  return (
    <ChartContainer config={chartConfig} className="h-full w-full">
      <BarChart accessibilityLayer data={data} margin={{ top: 20, right: 20, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--color-border-hairline)" />
        <XAxis 
          dataKey="name" 
          tickLine={false} 
          axisLine={false} 
          tickMargin={8}
          className="text-xs font-mono"
        />
        <YAxis 
          tickLine={false} 
          axisLine={false} 
          tickMargin={8} 
          className="text-xs font-mono"
        />
        <ChartTooltip cursor={{ fill: 'var(--color-bg-surface-raised)' }} content={<ChartTooltipContent />} />
        <Bar dataKey={dataKey} fill={color} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ChartContainer>
  )
}
