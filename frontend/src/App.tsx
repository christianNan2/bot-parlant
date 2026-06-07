"use client"

import { useCallback, useEffect, useState } from "react"
import { DatabaseIcon, LogOutIcon, RefreshCwIcon } from "lucide-react"
import { toast } from "sonner"

import { CountryChart } from "@/components/country-chart"
import { LoginForm } from "@/components/login-form"
import { StatsCards } from "@/components/stats-cards"
import { UserFormDialog } from "@/components/user-form-dialog"
import { UsersTable } from "@/components/users-table"
import { Button, buttonVariants } from "@/components/ui/button"
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Toaster } from "@/components/ui/sonner"
import {
  ApiError,
  fetchDashboardSession,
  fetchUsers,
  fetchUserStats,
  logout,
} from "@/lib/api"
import type { User, UserStats } from "@/types/user"

const PAGE_SIZE = 10

export default function App() {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null)
  const [username, setUsername] = useState<string | null>(null)
  const [databaseConfigured, setDatabaseConfigured] = useState(true)
  const [stats, setStats] = useState<UserStats | null>(null)
  const [users, setUsers] = useState<User[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState("")
  const [debouncedSearch, setDebouncedSearch] = useState("")
  const [loadingStats, setLoadingStats] = useState(false)
  const [loadingUsers, setLoadingUsers] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [editUser, setEditUser] = useState<User | null>(null)
  const [createOpen, setCreateOpen] = useState(false)

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedSearch(search.trim())
      setOffset(0)
    }, 300)
    return () => window.clearTimeout(timer)
  }, [search])

  const checkSession = useCallback(async () => {
    try {
      const session = await fetchDashboardSession()
      setAuthenticated(session.authenticated)
      setUsername(session.username)
      setDatabaseConfigured(session.databaseConfigured)
      return session.authenticated
    } catch {
      setAuthenticated(false)
      setUsername(null)
      return false
    }
  }, [])

  const loadDashboard = useCallback(async () => {
    setLoadingStats(true)
    setLoadingUsers(true)
    setRefreshing(true)

    try {
      const isAuthed = await checkSession()
      if (!isAuthed) {
        setStats(null)
        setUsers([])
        setTotal(0)
        return
      }

      const [statsResult, usersResult] = await Promise.all([
        fetchUserStats(),
        fetchUsers({ limit: PAGE_SIZE, offset, search: debouncedSearch || undefined }),
      ])

      setStats(statsResult)
      setUsers(usersResult.users)
      setTotal(usersResult.total)
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setAuthenticated(false)
        setUsername(null)
        toast.error("Session expired. Please sign in again.")
      } else {
        toast.error(error instanceof Error ? error.message : "Failed to load dashboard")
      }
    } finally {
      setLoadingStats(false)
      setLoadingUsers(false)
      setRefreshing(false)
    }
  }, [checkSession, debouncedSearch, offset])

  useEffect(() => {
    void loadDashboard()
  }, [loadDashboard])

  async function handleLoginSuccess(signedInUsername: string) {
    setAuthenticated(true)
    setUsername(signedInUsername)
    toast.success(`Signed in as ${signedInUsername}`)
    await loadDashboard()
  }

  async function handleLogout() {
    try {
      await logout()
      setAuthenticated(false)
      setUsername(null)
      setStats(null)
      setUsers([])
      setTotal(0)
      toast.success("Signed out")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Sign out failed")
    }
  }

  function handleUserSaved(updated: User) {
    setUsers((current) =>
      current.map((user) => (user.userId === updated.userId ? updated : user))
    )
    void fetchUserStats().then(setStats).catch(() => undefined)
  }

  function handleUserCreated(created: User) {
    setUsers((current) => [created, ...current])
    setTotal((current) => current + 1)
    void fetchUserStats().then(setStats).catch(() => undefined)
  }

  function handleUserDeleted(userId: number) {
    setUsers((current) => current.filter((user) => user.userId !== userId))
    setTotal((current) => Math.max(0, current - 1))
    void fetchUserStats().then(setStats).catch(() => undefined)
  }

  const showDashboard = authenticated === true

  return (
    <div className="min-h-svh bg-background">
      <Toaster richColors closeButton />

      <header className="border-b bg-card">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-6 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-primary/10 p-2 text-primary">
              <DatabaseIcon />
            </div>
            <div className="flex flex-col gap-1">
              <h1 className="text-2xl font-semibold tracking-tight">Users dashboard</h1>
              <p className="text-sm text-muted-foreground">
                {username
                  ? `Signed in as ${username}`
                  : "Visualize and manage Azure SQL registrations"}
              </p>
            </div>
          </div>
          {showDashboard ? (
            <div className="flex flex-wrap items-center gap-2">
              <a href="/" className={buttonVariants({ variant: "outline" })}>
                Back to chat
              </a>
              <Button variant="outline" onClick={() => void loadDashboard()} disabled={refreshing}>
                <RefreshCwIcon
                  data-icon="inline-start"
                  className={refreshing ? "animate-spin" : undefined}
                />
                Refresh
              </Button>
              <Button variant="outline" onClick={() => void handleLogout()}>
                <LogOutIcon data-icon="inline-start" />
                Sign out
              </Button>
            </div>
          ) : null}
        </div>
      </header>

      <main className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-6 sm:px-6">
        {authenticated === false ? (
          <>
            {!databaseConfigured ? (
              <Card className="max-w-md mx-auto w-full">
                <CardHeader>
                  <CardTitle>Database not configured</CardTitle>
                  <CardDescription>
                    Set AZURE_SQL_SERVER and AZURE_SQL_DATABASE in backend/.env, then restart
                    the server.
                  </CardDescription>
                </CardHeader>
              </Card>
            ) : (
              <LoginForm onSuccess={handleLoginSuccess} />
            )}
          </>
        ) : null}

        {showDashboard ? (
          <>
            <StatsCards stats={stats} loading={loadingStats} />

            <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
              <UsersTable
                users={users}
                total={total}
                limit={PAGE_SIZE}
                offset={offset}
                loading={loadingUsers}
                search={search}
                onSearchChange={setSearch}
                onPageChange={setOffset}
                onEdit={setEditUser}
                onAdd={() => setCreateOpen(true)}
                onDeleted={handleUserDeleted}
              />
              <CountryChart stats={stats} loading={loadingStats} />
            </div>
          </>
        ) : null}
      </main>

      <UserFormDialog
        user={editUser}
        mode="edit"
        open={Boolean(editUser)}
        onOpenChange={(open) => !open && setEditUser(null)}
        onSaved={handleUserSaved}
      />

      <UserFormDialog
        user={null}
        mode="create"
        open={createOpen}
        onOpenChange={setCreateOpen}
        onSaved={handleUserCreated}
      />
    </div>
  )
}
