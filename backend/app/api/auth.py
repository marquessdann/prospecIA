from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Organization, Role, User
from app.schemas import LoginIn, RegisterIn, UserCreate, UserOut, UserUpdate
from app.security import (
    COOKIE_NAME,
    create_token,
    get_current_user,
    hash_password,
    login_limiter,
    require_role,
    verify_password,
)

router = APIRouter(prefix="/api", tags=["auth"])


def _set_cookie(resp: Response, token: str) -> None:
    resp.set_cookie(COOKIE_NAME, token, httponly=True, secure=settings.cookie_secure, samesite="lax",
                    max_age=settings.access_token_minutes * 60, path="/")


@router.post("/auth/register", response_model=UserOut, status_code=201)
def register(data: RegisterIn, response: Response, db: Session = Depends(get_db)):
    """Cria uma organização e seu primeiro usuário (administrador)."""
    first_user = (db.scalar(select(func.count(User.id))) or 0) == 0
    if not first_user and (settings.single_user_mode or not settings.allow_registration):
        raise HTTPException(403, "Cadastro desabilitado. Peça um convite ao administrador.")
    if db.scalar(select(User).where(func.lower(User.email) == data.email.lower())):
        raise HTTPException(409, "E-mail já cadastrado")
    org = Organization(name=data.organization)
    db.add(org)
    db.flush()
    user = User(org_id=org.id, email=data.email.lower(), name=data.name, password_hash=hash_password(data.password),
                role=Role.admin.value, monthly_budget_usd=settings.default_monthly_budget_usd,
                max_results_per_search=settings.default_max_results_per_search)
    db.add(user)
    db.commit()
    _set_cookie(response, create_token(user))
    return user


@router.get("/auth/options")
def auth_options(db: Session = Depends(get_db)):
    """Informa à tela de login se ainda é possível criar conta."""
    has_users = (db.scalar(select(func.count(User.id))) or 0) > 0
    open_ = not has_users or (settings.allow_registration and not settings.single_user_mode)
    return {"registration_open": open_, "single_user_mode": settings.single_user_mode}


@router.post("/auth/login")
def login(data: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    login_limiter.check(request.client.host if request.client else "unknown")
    user = db.scalar(select(User).where(func.lower(User.email) == data.email.lower()))
    if not user or not verify_password(data.password, user.password_hash) or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou senha inválidos")
    token = create_token(user)
    _set_cookie(response, token)
    return {"access_token": token, "token_type": "bearer", "user": UserOut.model_validate(user)}


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return list(db.scalars(select(User).where(User.org_id == user.org_id).order_by(User.name)))


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(data: UserCreate, admin: User = Depends(require_role(Role.admin)), db: Session = Depends(get_db)):
    if settings.single_user_mode:
        raise HTTPException(403, "Modo de usuário único ativo (SINGLE_USER_MODE=true).")
    if db.scalar(select(User).where(func.lower(User.email) == data.email.lower())):
        raise HTTPException(409, "E-mail já cadastrado")
    u = User(org_id=admin.org_id, email=data.email.lower(), name=data.name, password_hash=hash_password(data.password),
             role=data.role.value, monthly_budget_usd=data.monthly_budget_usd,
             max_results_per_search=data.max_results_per_search)
    db.add(u)
    db.commit()
    return u


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, data: UserUpdate, admin: User = Depends(require_role(Role.admin)),
                db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u or u.org_id != admin.org_id:
        raise HTTPException(404, "Usuário não encontrado")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(u, k, v.value if hasattr(v, "value") else v)
    db.commit()
    return u
