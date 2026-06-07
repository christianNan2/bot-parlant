"use client"

import { useState } from "react"
import { Loader2Icon, LogInIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { login } from "@/lib/api"

type LoginFormProps = {
  onSuccess: (username: string) => void
}

export function LoginForm({ onSuccess }: LoginFormProps) {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)

    try {
      const session = await login(username, password)
      onSuccess(session.username ?? username)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Card className="mx-auto w-full max-w-md">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <LogInIcon />
          Sign in to database
        </CardTitle>
        <CardDescription>
          Use your Azure SQL username and password to access the dashboard.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit}>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="username">Username</FieldLabel>
              <Input
                id="username"
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="SQL login (e.g. ricardo)"
                required
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="password">Password</FieldLabel>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Your SQL password"
                required
              />
              <FieldDescription>
                Credentials are verified against Azure SQL and kept in a secure server session.
              </FieldDescription>
            </Field>
            {error ? (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            ) : null}
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? (
                <Loader2Icon data-icon="inline-start" className="animate-spin" />
              ) : (
                <LogInIcon data-icon="inline-start" />
              )}
              Sign in
            </Button>
          </FieldGroup>
        </form>
      </CardContent>
    </Card>
  )
}
