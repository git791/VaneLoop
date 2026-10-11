"use client";

import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";

export function SensorLineChart({
  data,
  sensorLabel = "T24 (s2)",
  unit = "",
}: {
  data: Array<{ cycle: number; value: number }>;
  sensorLabel?: string;
  unit?: string;
}) {
  const values = data.map((d) => d.value).filter((v) => !isNaN(v));
  const minVal = values.length ? Math.min(...values) : 0;
  const maxVal = values.length ? Math.max(...values) : 100;
  const padding = (maxVal - minVal) * 0.08 || 1;
  const yDomain: [number, number] = [
    Number((minVal - padding).toFixed(2)),
    Number((maxVal + padding).toFixed(2)),
  ];

  return (
    <ChartContainer
      config={{
        value: {
          label: `${sensorLabel} ${unit ? `(${unit})` : ""}`.trim(),
          color: "var(--color-primary)",
        },
      }}
      className="h-full w-full min-h-[200px]"
    >
      <LineChart accessibilityLayer data={data} margin={{ top: 15, right: 20, left: 15, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--color-border-hairline)" />
        <XAxis
          dataKey="cycle"
          tickLine={false}
          axisLine={false}
          tickMargin={8}
          className="font-mono text-xs"
        />
        <YAxis
          domain={yDomain}
          tickLine={false}
          axisLine={false}
          tickMargin={8}
          className="font-mono text-xs"
          tickFormatter={(val) => (typeof val === "number" ? val.toFixed(1) : String(val))}
        />
        <ChartTooltip cursor={false} content={<ChartTooltipContent />} />
        <Line
          type="monotone"
          dataKey="value"
          stroke="var(--color-primary)"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ChartContainer>
  );
}
