"""
FastAPI application dependencies — configuration, auth, and service injection.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic_settings import BaseSettings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database import get_session
from src.api.db_models import User
from src.utils.logger import get_logger

logger = get_logger("dependencies")


# ---------------------------------------------------------------------------
# Settings (from .env)
# ---------------------------------------------------------------------------
class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    db_url: str = "sqlite+aiosqlite:///./data/candidate_ai.db"

    # Security
    secret_key: str = "change-me-to-a-random-32-character-minimum-string"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Models
    model_path: str = "./models"
    faiss_index_path: str = "./models/embeddings/faiss_index.faiss"
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    ranker_model_path: str = "./models/ranker/xgboost_ranker_v1.json"
    authenticity_model_path: str = "./models/authenticity/evidence_model_v1.pkl"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # API
    log_level: str = "INFO"
    max_upload_size_mb: int = 10
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Retrieval
    top_k_retrieval: int = 500
    top_k_rerank: int = 100

    # Features
    feature_config_path: str = "./configs/feature_config.json"
    feature_version: str = "v1"

    # Upload
    upload_dir: str = "./data/uploads"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


# Singleton settings
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get application settings (singleton)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


# ---------------------------------------------------------------------------
# JWT Tokens
# ---------------------------------------------------------------------------
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a JWT access token."""
    settings = get_settings()
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.access_token_expire_minutes
        )

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    """
    FastAPI dependency: extract and validate current user from JWT.

    Raises:
        HTTPException 401 if token is invalid or user not found.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await session.execute(
        select(User).where(User.username == username)
    )
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise credentials_exception

    return user
