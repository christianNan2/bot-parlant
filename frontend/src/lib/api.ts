import type { User, UserFormData, UserListResponse, UserStats } from "@/types/user"

export type DashboardSession = {
  authenticated: boolean
  username: string | null
  databaseConfigured: boolean
}

class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json")
  }

  const response = await fetch(path, {
    ...init,
    headers,
    credentials: "include",
  })
  const payload = await response.json().catch(() => ({}))

  if (!response.ok) {
    throw new ApiError(
      typeof payload.error === "string" ? payload.error : "Request failed.",
      response.status
    )
  }

  return payload as T
}

export async function fetchDashboardSession(): Promise<DashboardSession> {
  return request<DashboardSession>("/api/dashboard/session")
}

export async function login(username: string, password: string): Promise<DashboardSession> {
  return request<DashboardSession>("/api/dashboard/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  })
}

export async function logout(): Promise<void> {
  await request("/api/dashboard/logout", { method: "POST" })
}

export async function fetchUserStats(): Promise<UserStats> {
  return request<UserStats>("/api/users/stats")
}

export async function fetchUsers(params: {
  limit?: number
  offset?: number
  search?: string
}): Promise<UserListResponse> {
  const query = new URLSearchParams()
  if (params.limit != null) query.set("limit", String(params.limit))
  if (params.offset != null) query.set("offset", String(params.offset))
  if (params.search) query.set("search", params.search)
  const suffix = query.toString() ? `?${query.toString()}` : ""
  return request<UserListResponse>(`/api/users${suffix}`)
}

export async function createUser(data: UserFormData): Promise<User> {
  return request<User>("/api/users", {
    method: "POST",
    body: JSON.stringify({
      firstName: data.firstName,
      lastName: data.lastName,
      email: data.email,
      birthDate: data.birthDate || undefined,
      phoneNumber: data.phoneNumber || undefined,
      streetAddress: data.streetAddress || undefined,
      zipCode: data.zipCode || undefined,
      city: data.city || undefined,
      country: data.country || undefined,
    }),
  })
}

export async function updateUser(userId: number, data: UserFormData): Promise<User> {
  return request<User>(`/api/users/${userId}`, {
    method: "PUT",
    body: JSON.stringify({
      firstName: data.firstName,
      lastName: data.lastName,
      email: data.email,
      birthDate: data.birthDate || undefined,
      phoneNumber: data.phoneNumber || undefined,
      streetAddress: data.streetAddress || undefined,
      zipCode: data.zipCode || undefined,
      city: data.city || undefined,
      country: data.country || undefined,
    }),
  })
}

export async function deleteUser(userId: number): Promise<void> {
  await request(`/api/users/${userId}`, { method: "DELETE" })
}

export { ApiError }
