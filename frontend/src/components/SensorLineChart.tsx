"use client"
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts"
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart"

export function SensorLineChart({ data }: { data: any[] }) {
  const chartConfig = {
    value: {
      label: "Value",
      color: "var(--color-primary)",
    }
  }

  return (
    <ChartContainer config={chartConfig} className="h-full w-full min-h-[200px]">
      <LineChart accessibilityLayer data={data} margin={{ top: 20, right: 20, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--color-border-hairline)" />
        <XAxis 
          dataKey="cycle" 
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
        <ChartTooltip cursor={false} content={<ChartTooltipContent />} />
        <Line 
          type="monotone" 
          dataKey="value" 
          stroke="var(--color-primary)" 
          strokeWidth={2} 
          dot={false} 
        />
      </LineChart>
    </ChartContainer>
  )
}
