"""Azure SQL persistence for dbo.Users."""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterator

import pyodbc
from azure.identity import DefaultAzureCredential

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SQL_COPT_SS_ACCESS_TOKEN = 1256
SQL_AZURE_AD_SCOPE = "https://database.windows.net/.default"

# Logical field → possible SQL column names (first match wins).
_USERS_COLUMN_CANDIDATES: dict[str, tuple[str, ...]] = {
    "first_name": ("FirstName", "firstName", "first_name"),
    "last_name": ("LastName", "lastName", "last_name"),
    "birth_date": ("BirthDate", "birthDate", "birth_date"),
    "email": ("Email", "email"),
    "phone_number": ("PhoneNumber", "phone", "phoneNumber", "phone_number"),
    "street_address": ("StreetAddress", "street", "streetAddress", "street_address"),
    "zip_code": ("ZipCode", "zip", "zipCode", "zip_code"),
    "city": ("City", "city"),
    "country": ("Country", "country"),
    "created_at": ("CreatedAt", "createdAt", "created_at"),
}
_USERS_ID_CANDIDATES = ("UserId", "id", "userId", "user_id")

_users_columns_cache: set[str] | None = None


class UserRegistrationError(Exception):
    """Validation or persistence error for user registration."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class UserRecord:
    first_name: str
    last_name: str
    email: str
    birth_date: date | None = None
    phone_number: str | None = None
    street_address: str | None = None
    zip_code: str | None = None
    city: str | None = None
    country: str | None = None


def is_sql_configured() -> bool:
    if (os.getenv("AZURE_SQL_CONNECTION_STRING") or "").strip():
        return True
    server = (os.getenv("AZURE_SQL_SERVER") or "").strip()
    database = (os.getenv("AZURE_SQL_DATABASE") or "").strip()
    if not server or not database:
        return False
    if _use_aad_auth():
        return True
    user = (os.getenv("AZURE_SQL_USER") or "").strip()
    password = os.getenv("AZURE_SQL_PASSWORD")
    return bool(user and password)


def _use_aad_auth() -> bool:
    explicit = (os.getenv("AZURE_SQL_USE_AAD") or "").strip().lower()
    if explicit in ("1", "true", "yes"):
        return True
    if explicit in ("0", "false", "no"):
        return False
    # Default: AAD when no SQL password is set.
    return not (os.getenv("AZURE_SQL_PASSWORD") or "").strip()


def _build_connection_string(*, include_sql_auth: bool) -> str:
    override = (os.getenv("AZURE_SQL_CONNECTION_STRING") or "").strip()
    if override:
        if _use_aad_auth() and "Authentication=" in override:
            parts = [
                part.strip()
                for part in override.split(";")
                if part.strip() and not part.strip().lower().startswith("authentication=")
            ]
            return ";".join(parts) + ";"
        return override

    server = (os.getenv("AZURE_SQL_SERVER") or "").strip()
    database = (os.getenv("AZURE_SQL_DATABASE") or "").strip()
    port = (os.getenv("AZURE_SQL_PORT") or "1433").strip()
    if not server or not database:
        raise UserRegistrationError(
            "SQL is not configured. Set AZURE_SQL_SERVER and AZURE_SQL_DATABASE (or AZURE_SQL_CONNECTION_STRING).",
            status_code=503,
        )

    host = server if server.startswith("tcp:") else f"tcp:{server},{port}"
    conn_str = (
        f"Driver={{ODBC Driver 18 for SQL Server}};"
        f"Server={host};"
        f"Database={database};"
        f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )

    if include_sql_auth:
        user = (os.getenv("AZURE_SQL_USER") or "").strip()
        password = os.getenv("AZURE_SQL_PASSWORD") or ""
        if not user or not password:
            raise UserRegistrationError(
                "SQL password is missing. Set AZURE_SQL_PASSWORD, or set AZURE_SQL_USE_AAD=true "
                "and sign in with Azure CLI (az login) / managed identity in Azure.",
                status_code=503,
            )
        conn_str += f"Uid={user};Pwd={password};"

    return conn_str


def _open_connection() -> pyodbc.Connection:
    if _use_aad_auth():
        conn_str = _build_connection_string(include_sql_auth=False)
        try:
            credential = DefaultAzureCredential()
            token = credential.get_token(SQL_AZURE_AD_SCOPE).token
        except Exception as exc:
            raise UserRegistrationError(
                "Azure AD sign-in failed. Run `az login` locally or configure managed identity in Azure.",
                status_code=503,
            ) from exc
        token_bytes = token.encode("utf-16-le")
        return pyodbc.connect(
            conn_str,
            attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_bytes},
        )

    return pyodbc.connect(_build_connection_string(include_sql_auth=True))


@contextmanager
def _connection() -> Iterator[pyodbc.Connection]:
    conn = _open_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _pick(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _parse_birth_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError as exc:
        raise UserRegistrationError("birthDate must be YYYY-MM-DD.") from exc


def user_from_payload(payload: dict[str, Any]) -> UserRecord:
    first_name = _pick(payload, "firstName", "first_name")
    last_name = _pick(payload, "lastName", "last_name")
    email = (_pick(payload, "email") or "").lower()

    if not first_name or not last_name:
        raise UserRegistrationError("firstName and lastName are required.")
    if not email or not EMAIL_RE.match(email):
        raise UserRegistrationError("A valid email is required.")

    birth_raw = _pick(payload, "birthDate", "birth_date")
    return UserRecord(
        first_name=first_name,
        last_name=last_name,
        email=email,
        birth_date=_parse_birth_date(birth_raw),
        phone_number=_pick(payload, "phoneNumber", "phone_number"),
        street_address=_pick(payload, "streetAddress", "street_address"),
        zip_code=_pick(payload, "zipCode", "zip_code"),
        city=_pick(payload, "city"),
        country=_pick(payload, "country"),
    )


def _load_users_columns(conn: pyodbc.Connection) -> set[str]:
    global _users_columns_cache
    if _users_columns_cache is not None:
        return _users_columns_cache

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'Users'
        """
    )
    _users_columns_cache = {str(row[0]) for row in cursor.fetchall()}
    if not _users_columns_cache:
        raise UserRegistrationError(
            "Table dbo.Users was not found or has no columns.",
            status_code=503,
        )
    return _users_columns_cache


def _resolve_column(available: set[str], logical: str) -> str | None:
    for candidate in _USERS_COLUMN_CANDIDATES.get(logical, ()):
        if candidate in available:
            return candidate
    return None


def _build_insert(user: UserRecord, available: set[str]) -> tuple[str, list[Any], str | None]:
    """Build INSERT for dbo.Users based on actual column names."""
    id_col = next((name for name in _USERS_ID_CANDIDATES if name in available), None)

    value_map: dict[str, Any] = {
        "first_name": user.first_name,
        "last_name": user.last_name,
        "birth_date": user.birth_date,
        "email": user.email,
        "phone_number": user.phone_number,
        "street_address": user.street_address,
        "zip_code": user.zip_code,
        "city": user.city,
        "country": user.country,
    }

    columns: list[str] = []
    placeholders: list[str] = []
    params: list[Any] = []

    for logical, value in value_map.items():
        if logical in ("first_name", "last_name", "email") and value is None:
            raise UserRegistrationError(f"{logical} is required.", status_code=400)
        if value is None:
            continue
        col = _resolve_column(available, logical)
        if not col:
            if logical in ("first_name", "last_name", "email"):
                raise UserRegistrationError(
                    f"dbo.Users is missing a column for {logical} "
                    f"(tried: {', '.join(_USERS_COLUMN_CANDIDATES[logical])}).",
                    status_code=503,
                )
            continue
        columns.append(col)
        placeholders.append("?")
        params.append(value)

    created_col = _resolve_column(available, "created_at")
    if created_col and created_col not in columns:
        columns.append(created_col)
        placeholders.append("SYSUTCDATETIME()")

    if not columns:
        raise UserRegistrationError("No writable columns resolved for dbo.Users.", status_code=503)

    output = f"OUTPUT INSERTED.[{id_col}]" if id_col else ""
    sql = (
        f"INSERT INTO dbo.Users ({', '.join(f'[{c}]' for c in columns)}) "
        f"{output} "
        f"VALUES ({', '.join(placeholders)});"
    )
    return sql, params, id_col


def register_user(user: UserRecord) -> dict[str, Any]:
    id_col: str | None = None
    try:
        with _connection() as conn:
            available = _load_users_columns(conn)
            sql, params, id_col = _build_insert(user, available)
            row = conn.cursor().execute(sql, params).fetchone()
    except pyodbc.IntegrityError as exc:
        if "UNIQUE" in str(exc).upper() or "2627" in str(exc):
            raise UserRegistrationError(
                f"A user with email {user.email} is already registered.",
                status_code=409,
            ) from exc
        raise UserRegistrationError(f"Database error: {exc}", status_code=500) from exc
    except pyodbc.Error as exc:
        raise UserRegistrationError(f"Database error: {exc}", status_code=500) from exc

    user_id: int | None = None
    created_at: str | None = None
    if row and row[0] is not None:
        user_id = int(row[0])
        if len(row) > 1 and isinstance(row[1], datetime):
            created_at = row[1].isoformat()

    if user_id is None and id_col:
        raise UserRegistrationError("Registration failed with no row returned.", status_code=500)

    if created_at is None:
        created_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    result: dict[str, Any] = {"email": user.email, "createdAt": created_at}
    if user_id is not None:
        result["userId"] = user_id
    return result
