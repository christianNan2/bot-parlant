import type { UserFormData, User } from "@/types/user"

export function userToFormData(user: User): UserFormData {
  return {
    firstName: user.firstName ?? "",
    lastName: user.lastName ?? "",
    email: user.email ?? "",
    birthDate: user.birthDate?.slice(0, 10) ?? "",
    phoneNumber: user.phoneNumber ?? "",
    streetAddress: user.streetAddress ?? "",
    zipCode: user.zipCode ?? "",
    city: user.city ?? "",
    country: user.country ?? "",
  }
}

export function formatDate(value?: string) {
  if (!value) return "—"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  })
}

export function formatDateTime(value?: string) {
  if (!value) return "—"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export function fullName(user: User) {
  return [user.firstName, user.lastName].filter(Boolean).join(" ") || "Unknown"
}
