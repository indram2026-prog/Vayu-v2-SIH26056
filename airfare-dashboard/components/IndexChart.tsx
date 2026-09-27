"use client";

import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { IndexPoint } from "@/lib/types";

export function IndexChart({ data }: { data: IndexPoint[] }) {
  const values = data.map((d) => d.index_value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = (max - min) * 0.15 || 1;

  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="2 4" className="stroke-line dark:stroke-line-dark" vertical={false} />
          <XAxis
            dataKey="observation_date"
            tickFormatter={(d: string) => d.slice(5)}
            tick={{ fontSize: 11, fontFamily: "var(--font-public-sans)" }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            domain={[min - pad, max + pad]}
            tick={{ fontSize: 11, fontFamily: "var(--font-public-sans)" }}
            // The bug: index values carry long float tails (e.g.
            // 100.77977334310182) from the Laspeyres calculation, and with
            // no formatter Recharts rendered that full precision, then
            // clipped it inside the 40px axis width — that's the
            // "99999/00001" garbage. Round to 1 decimal for display only;
            // the underlying data (and the tooltip below) keep full
            // precision.
            tickFormatter={(v: number) => v.toFixed(1)}
            axisLine={false}
            tickLine={false}
            width={52}
          />
          <Tooltip
            formatter={(v: number) => v.toFixed(2)}
            labelFormatter={(d: string) => d}
            contentStyle={{ fontSize: 12, fontFamily: "var(--font-public-sans)", borderRadius: 4 }}
          />
          <Line
            type="monotone"
            dataKey="index_value"
            stroke="#22344F"
            strokeWidth={2.5}
            dot={{ r: 3, fill: "#22344F", strokeWidth: 0 }}
            activeDot={{ r: 5 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
