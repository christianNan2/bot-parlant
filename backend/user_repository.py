"""Azure SQL persistence for dbo.Users."""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterator

import pyodbc
from azure.identity import DefaultAzureCredential

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PLACEHOLDER_EMAIL_LOCALS = frozenset({"none", "null", "undefined", "n/a", "na", "unknown"})
SQL_COPT_SS_ACCESS_TOKEN = 1256
SQL_AZURE_AD_SCOPE = "https://database.windows.net/.default"

# Logical field → possible SQL column names (first match wins).
# Current dbo.Users schema: id, firstName, lastName, email, birthDate,
# phone, street, zip, city, country.
_USERS_COLUMN_CANDIDATES: dict[str, tuple[str, ...]] = {
    "first_name": ("firstName", "FirstName", "first_name"),
    "last_name": ("lastName", "LastName", "last_name"),
    "birth_date": ("birthDate", "BirthDate", "birth_date"),
    "email": ("email", "Email"),
    "phone_number": ("phone", "PhoneNumber", "phoneNumber", "phone_number"),
    "street_address": ("street", "StreetAddress", "streetAddress", "street_address"),
    "zip_code": ("zip", "ZipCode", "zipCode", "zip_code"),
    "city": ("city", "City"),
    "country": ("country", "Country"),
    "created_at": ("createdAt", "CreatedAt", "created_at"),
}
_USERS_ID_CANDIDATES = ("id", "UserId", "userId", "user_id")

_users_columns_cache: set[str] | None = None


@dataclass(frozen=True)
class SqlCredentials:
    username: str
    password: str


_sql_credentials_override: ContextVar[SqlCredentials | None] = ContextVar(
    "sql_credentials_override",
    default=None,
)


def set_sql_credentials_override(credentials: SqlCredentials | None) -> Token:
    return _sql_credentials_override.set(credentials)


def reset_sql_credentials_override(token: Token) -> None:
    _sql_credentials_override.reset(token)


def is_dashboard_sql_configured() -> bool:
    """True when server/database are set; dashboard login supplies credentials."""
    if (os.getenv("AZURE_SQL_CONNECTION_STRING") or "").strip():
        return True
    server = (os.getenv("AZURE_SQL_SERVER") or "").strip()
    database = (os.getenv("AZURE_SQL_DATABASE") or "").strip()
    return bool(server and database)


class UserRegistrationError(Exception):
    """Validation or persistence error for user registration."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _database_error(exc: pyodbc.Error) -> UserRegistrationError:
    message = str(exc).lower()
    if "not allowed to access the server" in message or "40615" in message:
        return UserRegistrationError(
            "Database firewall blocked the server. In Azure Portal, open the SQL server "
            "Networking page and allow Azure services, or add this App Service outbound IPs.",
            status_code=503,
        )
    return UserRegistrationError(f"Database error: {exc}", status_code=500)


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
    if _sql_credentials_override.get() is not None:
        return False
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
        override = _sql_credentials_override.get()
        if override is not None:
            conn_str += f"Uid={override.username};Pwd={override.password};"
        else:
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


def verify_sql_login(username: str, password: str) -> None:
    """Validate SQL credentials by opening a connection."""
    username = username.strip()
    if not username or not password:
        raise UserRegistrationError("Username and password are required.", status_code=400)
    if not is_dashboard_sql_configured():
        raise UserRegistrationError(
            "Database server is not configured. Set AZURE_SQL_SERVER and AZURE_SQL_DATABASE.",
            status_code=503,
        )

    token = set_sql_credentials_override(SqlCredentials(username=username, password=password))
    try:
        with _connection() as conn:
            conn.cursor().execute("SELECT 1;")
    except pyodbc.Error as exc:
        message = str(exc).lower()
        if "login failed" in message or "18456" in message:
            raise UserRegistrationError("Invalid username or password.", status_code=401) from exc
        raise UserRegistrationError(f"Database connection failed: {exc}", status_code=503) from exc
    finally:
        reset_sql_credentials_override(token)


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
    local_part = email.split("@", 1)[0]
    if local_part in _PLACEHOLDER_EMAIL_LOCALS:
        raise UserRegistrationError("A valid email is required (not a placeholder).")

    birth_raw = _pick(payload, "birthDate", "birth_date")
    return UserRecord(
        first_name=first_name,
        last_name=last_name,
        email=email,
        birth_date=_parse_birth_date(birth_raw),
        phone_number=_pick(payload, "phone", "phoneNumber", "phone_number"),
        street_address=_pick(payload, "street", "streetAddress", "street_address"),
        zip_code=_pick(payload, "zip", "zipCode", "zip_code"),
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
        raise _database_error(exc) from exc
    except pyodbc.Error as exc:
        raise _database_error(exc) from exc

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


def _resolve_id_column(available: set[str]) -> str:
    col = next((name for name in _USERS_ID_CANDIDATES if name in available), None)
    if not col:
        raise UserRegistrationError("dbo.Users has no id column.", status_code=503)
    return col


def _row_to_user(row: pyodbc.Row, columns: list[str], available: set[str]) -> dict[str, Any]:
    """Map a SQL row to a camelCase API dict."""
    data = {columns[i]: row[i] for i in range(len(columns))}
    id_col = _resolve_id_column(available)

    def get_logical(logical: str) -> Any:
        col = _resolve_column(available, logical)
        if not col:
            return None
        value = data.get(col)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        return value

    user: dict[str, Any] = {
        "userId": data.get(id_col),
        "firstName": get_logical("first_name"),
        "lastName": get_logical("last_name"),
        "email": get_logical("email"),
        "birthDate": get_logical("birth_date"),
        "phoneNumber": get_logical("phone_number"),
        "streetAddress": get_logical("street_address"),
        "zipCode": get_logical("zip_code"),
        "city": get_logical("city"),
        "country": get_logical("country"),
        "createdAt": get_logical("created_at"),
    }
    return {k: v for k, v in user.items() if v is not None or k == "userId"}


def _select_columns(available: set[str]) -> list[str]:
    id_col = _resolve_id_column(available)
    cols = [id_col]
    for logical in _USERS_COLUMN_CANDIDATES:
        col = _resolve_column(available, logical)
        if col and col not in cols:
            cols.append(col)
    return cols


def list_users(*, limit: int = 50, offset: int = 0, search: str | None = None) -> dict[str, Any]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    search = (search or "").strip()

    try:
        with _connection() as conn:
            available = _load_users_columns(conn)
            cols = _select_columns(available)
            id_col = _resolve_id_column(available)
            email_col = _resolve_column(available, "email")
            first_col = _resolve_column(available, "first_name")
            last_col = _resolve_column(available, "last_name")
            created_col = _resolve_column(available, "created_at")

            where = ""
            params: list[Any] = []
            if search and email_col:
                clauses = [f"[{email_col}] LIKE ?"]
                params.append(f"%{search}%")
                if first_col:
                    clauses.append(f"[{first_col}] LIKE ?")
                    params.append(f"%{search}%")
                if last_col:
                    clauses.append(f"[{last_col}] LIKE ?")
                    params.append(f"%{search}%")
                where = "WHERE " + " OR ".join(clauses)

            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM dbo.Users {where};", params)
            total = int(cursor.fetchone()[0])

            order = f"ORDER BY [{created_col or id_col}] DESC" if (created_col or id_col) else ""
            select_list = ", ".join(f"[{c}]" for c in cols)
            cursor.execute(
                f"SELECT {select_list} FROM dbo.Users {where} {order} "
                f"OFFSET ? ROWS FETCH NEXT ? ROWS ONLY;",
                [*params, offset, limit],
            )
            rows = cursor.fetchall()
            users = [_row_to_user(row, cols, available) for row in rows]
    except pyodbc.Error as exc:
        raise UserRegistrationError(f"Database error: {exc}", status_code=500) from exc

    return {"users": users, "total": total, "limit": limit, "offset": offset}


def get_user(user_id: int) -> dict[str, Any]:
    try:
        with _connection() as conn:
            available = _load_users_columns(conn)
            cols = _select_columns(available)
            id_col = _resolve_id_column(available)
            select_list = ", ".join(f"[{c}]" for c in cols)
            row = conn.cursor().execute(
                f"SELECT {select_list} FROM dbo.Users WHERE [{id_col}] = ?;",
                (user_id,),
            ).fetchone()
    except pyodbc.Error as exc:
        raise UserRegistrationError(f"Database error: {exc}", status_code=500) from exc

    if not row:
        raise UserRegistrationError(f"User {user_id} not found.", status_code=404)
    return _row_to_user(row, cols, available)


def update_user(user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    user = user_from_payload({**payload, "userId": user_id})
    try:
        with _connection() as conn:
            available = _load_users_columns(conn)
            id_col = _resolve_id_column(available)
            existing = conn.cursor().execute(
                f"SELECT 1 FROM dbo.Users WHERE [{id_col}] = ?;",
                (user_id,),
            ).fetchone()
            if not existing:
                raise UserRegistrationError(f"User {user_id} not found.", status_code=404)

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

            set_parts: list[str] = []
            params: list[Any] = []
            for logical, value in value_map.items():
                col = _resolve_column(available, logical)
                if not col:
                    continue
                set_parts.append(f"[{col}] = ?")
                params.append(value)

            if not set_parts:
                raise UserRegistrationError("No updatable columns resolved.", status_code=503)

            params.append(user_id)
            conn.cursor().execute(
                f"UPDATE dbo.Users SET {', '.join(set_parts)} WHERE [{id_col}] = ?;",
                params,
            )
    except pyodbc.IntegrityError as exc:
        if "UNIQUE" in str(exc).upper() or "2627" in str(exc):
            raise UserRegistrationError(
                f"A user with email {user.email} is already registered.",
                status_code=409,
            ) from exc
        raise UserRegistrationError(f"Database error: {exc}", status_code=500) from exc
    except pyodbc.Error as exc:
        raise UserRegistrationError(f"Database error: {exc}", status_code=500) from exc

    return get_user(user_id)


def delete_user(user_id: int) -> None:
    try:
        with _connection() as conn:
            available = _load_users_columns(conn)
            id_col = _resolve_id_column(available)
            cursor = conn.cursor()
            cursor.execute(f"DELETE FROM dbo.Users WHERE [{id_col}] = ?;", (user_id,))
            if cursor.rowcount == 0:
                raise UserRegistrationError(f"User {user_id} not found.", status_code=404)
    except pyodbc.Error as exc:
        raise UserRegistrationError(f"Database error: {exc}", status_code=500) from exc


def get_user_stats() -> dict[str, Any]:
    try:
        with _connection() as conn:
            available = _load_users_columns(conn)
            created_col = _resolve_column(available, "created_at")
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM dbo.Users;")
            total = int(cursor.fetchone()[0])

            today = 0
            week = 0
            if created_col:
                cursor.execute(
                    f"""
                    SELECT
                        SUM(CASE WHEN CAST([{created_col}] AS date) = CAST(SYSUTCDATETIME() AS date) THEN 1 ELSE 0 END),
                        SUM(CASE WHEN [{created_col}] >= DATEADD(day, -7, SYSUTCDATETIME()) THEN 1 ELSE 0 END)
                    FROM dbo.Users;
                    """
                )
                row = cursor.fetchone()
                today = int(row[0] or 0)
                week = int(row[1] or 0)

            by_country: list[dict[str, Any]] = []
            country_col = _resolve_column(available, "country")
            if country_col:
                cursor.execute(
                    f"""
                    SELECT [{country_col}], COUNT(*)
                    FROM dbo.Users
                    WHERE [{country_col}] IS NOT NULL AND LTRIM(RTRIM([{country_col}])) <> ''
                    GROUP BY [{country_col}]
                    ORDER BY COUNT(*) DESC;
                    """
                )
                by_country = [{"country": str(r[0]), "count": int(r[1])} for r in cursor.fetchall()]
    except pyodbc.Error as exc:
        raise UserRegistrationError(f"Database error: {exc}", status_code=500) from exc

    return {"total": total, "registeredToday": today, "registeredThisWeek": week, "byCountry": by_country}
