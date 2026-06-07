"use client"

import { useEffect, useState } from "react"
import { Loader2Icon } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Field,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { createUser, updateUser } from "@/lib/api"
import { userToFormData } from "@/lib/user-format"
import type { User, UserFormData } from "@/types/user"

const EMPTY_FORM: UserFormData = {
  firstName: "",
  lastName: "",
  email: "",
  birthDate: "",
  phoneNumber: "",
  streetAddress: "",
  zipCode: "",
  city: "",
  country: "",
}

type UserFormDialogProps = {
  user: User | null
  mode: "create" | "edit"
  open: boolean
  onOpenChange: (open: boolean) => void
  onSaved: (user: User) => void
}

export function UserFormDialog({
  user,
  mode,
  open,
  onOpenChange,
  onSaved,
}: UserFormDialogProps) {
  const [form, setForm] = useState<UserFormData>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const isCreate = mode === "create"

  useEffect(() => {
    if (!open) return
    if (isCreate) {
      setForm(EMPTY_FORM)
      return
    }
    if (user) {
      setForm(userToFormData(user))
    }
  }, [open, isCreate, user])

  function updateField<K extends keyof UserFormData>(key: K, value: UserFormData[K]) {
    setForm((current) => ({ ...current, [key]: value }))
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (!isCreate && !user?.userId) return

    setSaving(true)
    try {
      const saved = isCreate
        ? await createUser(form)
        : await updateUser(user!.userId, form)
      toast.success(isCreate ? "User created" : "User updated")
      onSaved(saved)
      onOpenChange(false)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Save failed")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{isCreate ? "Add user" : "Edit user"}</DialogTitle>
          <DialogDescription>
            {isCreate
              ? "Create a new record in dbo.Users."
              : `Update registration details for user #${user?.userId}.`}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit}>
          <FieldGroup>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field>
                <FieldLabel htmlFor="firstName">First name</FieldLabel>
                <Input
                  id="firstName"
                  value={form.firstName}
                  onChange={(event) => updateField("firstName", event.target.value)}
                  required
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="lastName">Last name</FieldLabel>
                <Input
                  id="lastName"
                  value={form.lastName}
                  onChange={(event) => updateField("lastName", event.target.value)}
                  required
                />
              </Field>
            </div>

            <Field>
              <FieldLabel htmlFor="email">Email</FieldLabel>
              <Input
                id="email"
                type="email"
                value={form.email}
                onChange={(event) => updateField("email", event.target.value)}
                required
              />
            </Field>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field>
                <FieldLabel htmlFor="birthDate">Birth date</FieldLabel>
                <Input
                  id="birthDate"
                  type="date"
                  value={form.birthDate}
                  onChange={(event) => updateField("birthDate", event.target.value)}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="phoneNumber">Phone</FieldLabel>
                <Input
                  id="phoneNumber"
                  value={form.phoneNumber}
                  onChange={(event) => updateField("phoneNumber", event.target.value)}
                />
              </Field>
            </div>

            <Field>
              <FieldLabel htmlFor="streetAddress">Street address</FieldLabel>
              <Input
                id="streetAddress"
                value={form.streetAddress}
                onChange={(event) => updateField("streetAddress", event.target.value)}
              />
            </Field>

            <div className="grid gap-4 sm:grid-cols-3">
              <Field>
                <FieldLabel htmlFor="zipCode">Zip</FieldLabel>
                <Input
                  id="zipCode"
                  value={form.zipCode}
                  onChange={(event) => updateField("zipCode", event.target.value)}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="city">City</FieldLabel>
                <Input
                  id="city"
                  value={form.city}
                  onChange={(event) => updateField("city", event.target.value)}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="country">Country</FieldLabel>
                <Input
                  id="country"
                  value={form.country}
                  onChange={(event) => updateField("country", event.target.value)}
                />
              </Field>
            </div>
          </FieldGroup>

          <DialogFooter className="mt-6">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? <Loader2Icon data-icon="inline-start" className="animate-spin" /> : null}
              {isCreate ? "Create user" : "Save changes"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
