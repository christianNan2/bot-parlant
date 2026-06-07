import { CalendarDaysIcon, GlobeIcon, UsersIcon } from "lucide-react"

import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import type { UserStats } from "@/types/user"

type StatsCardsProps = {
  stats: UserStats | null
  loading: boolean
}

export function StatsCards({ stats, loading }: StatsCardsProps) {
  const items = [
    {
      title: "Total users",
      value: stats?.total ?? 0,
      description: "Registered in dbo.Users",
      icon: UsersIcon,
    },
    {
      title: "Today",
      value: stats?.registeredToday ?? 0,
      description: "New registrations today",
      icon: CalendarDaysIcon,
    },
    {
      title: "This week",
      value: stats?.registeredThisWeek ?? 0,
      description: "Last 7 days",
      icon: CalendarDaysIcon,
    },
    {
      title: "Countries",
      value: stats?.byCountry.length ?? 0,
      description: "Distinct countries",
      icon: GlobeIcon,
    },
  ]

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => (
        <Card key={item.title}>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <div className="flex flex-col gap-1">
              <CardDescription>{item.title}</CardDescription>
              {loading ? (
                <Skeleton className="h-8 w-16" />
              ) : (
                <CardTitle className="text-3xl tabular-nums">
                  {item.value.toLocaleString()}
                </CardTitle>
              )}
            </div>
            <div className="rounded-lg bg-muted p-2 text-muted-foreground">
              <item.icon />
            </div>
          </CardHeader>
          <CardDescription className="px-6 pb-6">{item.description}</CardDescription>
        </Card>
      ))}
    </div>
  )
}
