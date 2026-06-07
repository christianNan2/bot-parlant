"""In-memory dashboard sessions backed by SQL username/password."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from threading import Lock

SESSION_COOKIE = "dashboard_session"
SESSION_TTL_SECONDS = 8 * 60 * 60


@dataclass
class DashboardSession:
    username: str
    password: str
    created_at: float


_store: dict[str, DashboardSession] = {}
_lock = Lock()


def _purge_expired(now: float | None = None) -> None:
    current = now if now is not None else time.time()
    expired = [
        token
        for token, session in _store.items()
        if current - session.created_at > SESSION_TTL_SECONDS
    ]
    for token in expired:
        _store.pop(token, None)


def create_session(username: str, password: str) -> str:
    token = secrets.token_urlsafe(32)
    with _lock:
        _purge_expired()
        _store[token] = DashboardSession(
            username=username,
            password=password,
            created_at=time.time(),
        )
    return token


def get_session(token: str | None) -> DashboardSession | None:
    if not token:
        return None
    with _lock:
        _purge_expired()
        session = _store.get(token)
        if session is None:
            return None
        if time.time() - session.created_at > SESSION_TTL_SECONDS:
            _store.pop(token, None)
            return None
        return session


def destroy_session(token: str | None) -> None:
    if not token:
        return
    with _lock:
        _store.pop(token, None)
