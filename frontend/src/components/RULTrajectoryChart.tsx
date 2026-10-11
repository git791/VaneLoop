"use client";

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  Legend,
} from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";

export interface RULChartPoint {
  cycle: number;
  rul_p50: number | null;
  rul_p10: number | null;
  rul_p90: number | null;
  rul_true?: number | null;
}

export function RULTrajectoryChart({ data }: { data: RULChartPoint[] }) {
  // Compute chart configuration
  const chartConfig = {
    rul_p50: {
      label: "Predicted RUL (p50)",
      color: "var(--color-primary)",
    },
    rul_true: {
      label: "True RUL",
      color: "#10b981", // Emerald
    },
    rul_p90: {
      label: "p10–p90 Band",
      color: "rgba(59, 130, 246, 0.2)",
    },
  };

  const chartData = data.map((d) => ({
    cycle: d.cycle,
    rul_p50: d.rul_p50,
    rul_p10: d.rul_p10,
    rul_p90: d.rul_p90,
    rul_true: d.rul_true ?? null,
  }));

  return (
    <ChartContainer config={chartConfig} className="h-full w-full min-h-[200px]">
      <ComposedChart
        accessibilityLayer
        data={chartData}
        margin={{ top: 15, right: 20, left: 10, bottom: 0 }}
      >
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--color-border-hairline)" />
        <XAxis
          dataKey="cycle"
          tickLine={false}
          axisLine={false}
          tickMargin={8}
          className="font-mono text-xs"
        />
        <YAxis
          domain={[0, "auto"]}
          tickLine={false}
          axisLine={false}
          tickMargin={8}
          className="font-mono text-xs"
          tickFormatter={(val) => (typeof val === "number" ? `${val}` : String(val))}
        />
        <ChartTooltip cursor={false} content={<ChartTooltipContent />} />
        <Legend verticalAlign="top" height={36} wrapperStyle={{ fontSize: "12px" }} />
        {/* Uncertainty band p10 - p90 */}
        <Area
          type="monotone"
          dataKey="rul_p90"
          stroke="none"
          fill="var(--color-primary)"
          fillOpacity={0.15}
          name="p10–p90 Band"
        />
        {/* Ground truth line (if present) */}
        <Line
          type="monotone"
          dataKey="rul_true"
          stroke="#10b981"
          strokeWidth={1.5}
          strokeDasharray="4 4"
          dot={false}
          name="True RUL"
          isAnimationActive={false}
        />
        {/* Predicted p50 */}
        <Line
          type="monotone"
          dataKey="rul_p50"
          stroke="var(--color-primary)"
          strokeWidth={2}
          dot={false}
          name="Predicted RUL (p50)"
          isAnimationActive={false}
        />
      </ComposedChart>
    </ChartContainer>
  );
}
