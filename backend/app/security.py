"""Autenticação (JWT em cookie httpOnly ou header Bearer) e controle de acesso por papel."""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Role, User

COOKIE_NAME = "prospecia_token"
ALGORITHM = "HS256"
ROLE_RANK = {Role.member.value: 1, Role.manager.value: 2, Role.admin.value: 3}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:72], hashed.encode())
    except ValueError:
        return False


def create_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user.id), "org": user.org_id, "role": user.role, "iat": now,
               "exp": now + timedelta(minutes=settings.access_token_minutes)}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = None
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:]
    else:
        token = request.cookies.get(COOKIE_NAME)
        # Mitigação de CSRF para autenticação por cookie: métodos de escrita exigem header customizado.
        if token and request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-requested-with") != "prospecia":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Cabeçalho X-Requested-With ausente")
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Não autenticado")
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão inválida ou expirada")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuário inativo")
    return user


def require_role(minimum: Role):
    def dep(user: User = Depends(get_current_user)) -> User:
        if ROLE_RANK.get(user.role, 0) < ROLE_RANK[minimum.value]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Permissão insuficiente")
        return user

    return dep


class LoginRateLimiter:
    """Limita tentativas de login por IP (proteção contra força bruta)."""

    def __init__(self, max_attempts: int = 10, window_s: int = 300):
        self.max_attempts, self.window_s = max_attempts, window_s
        self.hits: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> None:
        now = time.time()
        self.hits[key] = [t for t in self.hits[key] if now - t < self.window_s]
        if len(self.hits[key]) >= self.max_attempts:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Muitas tentativas. Aguarde alguns minutos.")
        self.hits[key].append(now)


login_limiter = LoginRateLimiter()
