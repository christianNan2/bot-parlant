"use client"

import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { Skeleton } from "@/components/ui/skeleton"
import type { UserStats } from "@/types/user"

const chartConfig = {
  count: {
    label: "Users",
    color: "var(--chart-1)",
  },
} satisfies ChartConfig

type CountryChartProps = {
  stats: UserStats | null
  loading: boolean
}

export function CountryChart({ stats, loading }: CountryChartProps) {
  const data = (stats?.byCountry ?? []).slice(0, 8)

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle>Users by country</CardTitle>
        <CardDescription>Top countries in your database</CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-[280px] w-full" />
        ) : data.length === 0 ? (
          <div className="flex h-[280px] items-center justify-center text-sm text-muted-foreground">
            No country data yet.
          </div>
        ) : (
          <ChartContainer config={chartConfig} className="h-[280px] w-full">
            <BarChart data={data} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
              <CartesianGrid vertical={false} />
              <XAxis
                dataKey="country"
                tickLine={false}
                axisLine={false}
                tickMargin={8}
              />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={32} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Bar dataKey="count" fill="var(--color-count)" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  )
}
