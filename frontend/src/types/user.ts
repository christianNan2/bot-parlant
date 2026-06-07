export type User = {
  userId: number
  firstName?: string
  lastName?: string
  email?: string
  birthDate?: string
  phoneNumber?: string
  streetAddress?: string
  zipCode?: string
  city?: string
  country?: string
  createdAt?: string
}

export type UserListResponse = {
  users: User[]
  total: number
  limit: number
  offset: number
}

export type UserStats = {
  total: number
  registeredToday: number
  registeredThisWeek: number
  byCountry: Array<{ country: string; count: number }>
}

export type UserFormData = {
  firstName: string
  lastName: string
  email: string
  birthDate: string
  phoneNumber: string
  streetAddress: string
  zipCode: string
  city: string
  country: string
}
