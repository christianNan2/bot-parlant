"use client"

import { useMemo, useState } from "react"
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  MoreHorizontalIcon,
  PencilIcon,
  PlusIcon,
  SearchIcon,
  Trash2Icon,
} from "lucide-react"
import { toast } from "sonner"

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { deleteUser } from "@/lib/api"
import { formatDateTime, fullName } from "@/lib/user-format"
import type { User } from "@/types/user"

type UsersTableProps = {
  users: User[]
  total: number
  limit: number
  offset: number
  loading: boolean
  search: string
  onSearchChange: (value: string) => void
  onPageChange: (offset: number) => void
  onEdit: (user: User) => void
  onAdd: () => void
  onDeleted: (userId: number) => void
}

export function UsersTable({
  users,
  total,
  limit,
  offset,
  loading,
  search,
  onSearchChange,
  onPageChange,
  onEdit,
  onAdd,
  onDeleted,
}: UsersTableProps) {
  const [deleteTarget, setDeleteTarget] = useState<User | null>(null)
  const [deleting, setDeleting] = useState(false)

  const page = Math.floor(offset / limit) + 1
  const pageCount = Math.max(1, Math.ceil(total / limit))
  const rangeStart = total === 0 ? 0 : offset + 1
  const rangeEnd = Math.min(offset + users.length, total)

  const pageLabel = useMemo(
    () => `Page ${page} of ${pageCount}`,
    [page, pageCount]
  )

  async function confirmDelete() {
    if (!deleteTarget?.userId) return
    setDeleting(true)
    try {
      await deleteUser(deleteTarget.userId)
      toast.success("User deleted")
      onDeleted(deleteTarget.userId)
      setDeleteTarget(null)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Delete failed")
    } finally {
      setDeleting(false)
    }
  }

  return (
    <>
      <Card>
        <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-col gap-1">
            <CardTitle>Users</CardTitle>
            <CardDescription>
              Browse, add, edit, and delete records from dbo.Users
            </CardDescription>
          </div>
          <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
            <div className="relative w-full sm:w-64">
              <SearchIcon className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted-foreground" />
              <Input
                className="pl-9"
                placeholder="Search name or email…"
                value={search}
                onChange={(event) => onSearchChange(event.target.value)}
              />
            </div>
            <Button onClick={onAdd}>
              <PlusIcon data-icon="inline-start" />
              Add user
            </Button>
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>User</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Location</TableHead>
                  <TableHead>Registered</TableHead>
                  <TableHead className="w-[72px] text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading
                  ? Array.from({ length: 5 }).map((_, index) => (
                      <TableRow key={index}>
                        {Array.from({ length: 5 }).map((__, cellIndex) => (
                          <TableCell key={cellIndex}>
                            <Skeleton className="h-5 w-full" />
                          </TableCell>
                        ))}
                      </TableRow>
                    ))
                  : users.length === 0
                    ? (
                        <TableRow>
                          <TableCell colSpan={5} className="h-24 text-center text-muted-foreground">
                            No users found.
                          </TableCell>
                        </TableRow>
                      )
                    : users.map((user) => (
                        <TableRow key={user.userId}>
                          <TableCell>
                            <div className="flex flex-col gap-1">
                              <span className="font-medium">{fullName(user)}</span>
                              <span className="text-xs text-muted-foreground">
                                ID {user.userId}
                              </span>
                            </div>
                          </TableCell>
                          <TableCell>{user.email ?? "—"}</TableCell>
                          <TableCell>
                            {user.city || user.country ? (
                              <div className="flex flex-wrap gap-1">
                                {user.city ? <Badge variant="secondary">{user.city}</Badge> : null}
                                {user.country ? <Badge variant="outline">{user.country}</Badge> : null}
                              </div>
                            ) : (
                              "—"
                            )}
                          </TableCell>
                          <TableCell>{formatDateTime(user.createdAt)}</TableCell>
                          <TableCell className="text-right">
                            <DropdownMenu>
                              <DropdownMenuTrigger
                                render={
                                  <Button variant="ghost" size="icon-sm">
                                    <MoreHorizontalIcon />
                                    <span className="sr-only">Open menu</span>
                                  </Button>
                                }
                              />
                              <DropdownMenuContent align="end">
                                <DropdownMenuItem onClick={() => onEdit(user)}>
                                  <PencilIcon data-icon="inline-start" />
                                  Edit
                                </DropdownMenuItem>
                                <DropdownMenuItem
                                  variant="destructive"
                                  onClick={() => setDeleteTarget(user)}
                                >
                                  <Trash2Icon data-icon="inline-start" />
                                  Delete
                                </DropdownMenuItem>
                              </DropdownMenuContent>
                            </DropdownMenu>
                          </TableCell>
                        </TableRow>
                      ))}
              </TableBody>
            </Table>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-muted-foreground">
              Showing {rangeStart}–{rangeEnd} of {total.toLocaleString()} users
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={offset <= 0 || loading}
                onClick={() => onPageChange(Math.max(0, offset - limit))}
              >
                <ChevronLeftIcon data-icon="inline-start" />
                Previous
              </Button>
              <span className="text-sm text-muted-foreground">{pageLabel}</span>
              <Button
                variant="outline"
                size="sm"
                disabled={offset + limit >= total || loading}
                onClick={() => onPageChange(offset + limit)}
              >
                Next
                <ChevronRightIcon data-icon="inline-end" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <AlertDialog open={Boolean(deleteTarget)} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete user?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently removes{" "}
              <strong>{deleteTarget ? fullName(deleteTarget) : "this user"}</strong> from the
              database. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={deleting}
              onClick={confirmDelete}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
