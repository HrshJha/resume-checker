"""
Authentication router — JWT login and user management.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database import get_session
from src.api.db_models import User
from src.api.dependencies import (
    create_access_token,
    get_settings,
    hash_password,
    verify_password,
)
from src.api.models.request_models import (
    TokenResponse,
    UserCreateRequest,
)

router = APIRouter()


@router.post("/token", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
):
    """Authenticate and get JWT access token."""
    result = await session.execute(
        select(User).where(User.username == form_data.username)
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(form_data.password, user.hashed_password):  # type: ignore
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    settings = get_settings()
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(
    request: UserCreateRequest,
    session: AsyncSession = Depends(get_session),
):
    """Register a new user (admin only in production)."""
    # Check if username exists
    result = await session.execute(
        select(User).where(User.username == request.username)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )

    user = User(
        username=request.username,
        hashed_password=hash_password(request.password),
        role=request.role,
    )
    session.add(user)
    await session.flush()

    return {"user_id": user.user_id, "username": user.username, "role": user.role}
