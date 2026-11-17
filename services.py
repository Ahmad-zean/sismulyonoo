from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import HTTPException, Request, status
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
from config import settings
from schema import UserCreate, UserUpdate

ACCESS_TOKEN_COOKIE = (
    "__Host-access_token" if settings.app_env == "production" else "access_token"
)
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes
PASSWORD_RESET = "reset_password"
PASSWORD_RESET_TTL = timedelta(minutes=30)


def create_user_record(user: UserCreate, db: Session) -> models.User:
    existing_username = db.execute(
        select(models.User).where(models.User.username == user.username)
    ).scalars().first()
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )

    existing_email = db.execute(
        select(models.User).where(models.User.email == user.email)
    ).scalars().first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists",
        )

    new_user = models.User(
        username=user.username,
        email=user.email,
        password_hash=hash_password(user.password),
        auth_version=0,
    )
    db.add(new_user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already exists",
        ) from exc
    db.refresh(new_user)
    return new_user


def register_user(
    user: UserCreate,
    confirm_password: str,
    db: Session,
) -> models.User:
    if user.password != confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match",
        )
    return create_user_record(user, db)


def update_user_account(
    user: models.User,
    profile: UserUpdate,
    db: Session,
    *,
    password_hash: str | None = None,
    image_file: str | None = None,
) -> models.User:
    if profile.username is not None:
        existing_username = db.execute(
            select(models.User).where(
                models.User.username == profile.username,
                models.User.id != user.id,
            )
        ).scalars().first()
        if existing_username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists",
            )

    if profile.email is not None:
        existing_email = db.execute(
            select(models.User).where(
                models.User.email == profile.email,
                models.User.id != user.id,
            )
        ).scalars().first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already exists",
            )

    if profile.username is not None:
        user.username = profile.username
    if profile.email is not None:
        user.email = profile.email
    if password_hash is not None:
        user.password_hash = password_hash
    if image_file is not None:
        user.image_file = image_file
    if password_hash is not None:
        user.auth_version += 1

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already exists",
        ) from exc
    db.refresh(user)
    return user


def authenticate_user(
    identifier: str,
    password: str,
    db: Session,
) -> models.User:
    user = db.execute(
        select(models.User).where(
            or_(
                models.User.username == identifier,
                models.User.email == identifier,
            )
        )
    ).scalars().first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username/email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def create_access_token(user_id: int, auth_version: int) -> str:
    expires_at = datetime.now(UTC) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES,
    )
    return jwt.encode(
        {"sub": str(user_id), "ver": auth_version, "exp": expires_at},
        settings.secret_key.get_secret_value(),
        algorithm=settings.algorithm,
    )


def get_user_from_access_token(
    token: str | None,
    db: Session,
) -> models.User | None:
    if not token:
        return None

    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.algorithm],
            options={"require": ["exp", "sub", "ver"]},
        )
        user_id = int(payload["sub"])
        auth_version = int(payload["ver"])
    except (jwt.InvalidTokenError, TypeError, ValueError):
        return None

    user = db.get(models.User, user_id)
    if not user or user.auth_version != auth_version:
        return None
    return user


def get_request_user(request: Request, db: Session) -> models.User | None:
    token = request.cookies.get(ACCESS_TOKEN_COOKIE)
    authorization = request.headers.get("authorization", "")
    if not token and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    return get_user_from_access_token(token, db)


def require_authenticated_user(
    request: Request,
    db: Session,
) -> models.User:
    user = get_request_user(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please log in to continue",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    password_hash = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=64,
    )
    return f"scrypt${salt.hex()}${password_hash.hex()}"


def verify_password(password: str, stored_hash: str | None) -> bool:
    if stored_hash is None:
        return False

    try:
        algorithm, salt_hex, hash_hex = stored_hash.split("$")
        salt = bytes.fromhex(salt_hex)
        expected_hash = bytes.fromhex(hash_hex)
    except ValueError:
        return False

    if algorithm != "scrypt" or len(expected_hash) != 64:
        return False

    actual_hash = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=len(expected_hash),
    )
    return hmac.compare_digest(actual_hash, expected_hash)


def email_action_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_email_action_token(
    user: models.User,
    purpose: str,
    db: Session,
) -> str:
    if purpose != PASSWORD_RESET:
        raise ValueError("Unsupported email token purpose.")
    expires_in = PASSWORD_RESET_TTL

    db.execute(
        delete(models.EmailActionToken).where(
            models.EmailActionToken.user_id == user.id,
            models.EmailActionToken.purpose == purpose,
        )
    )
    token = secrets.token_urlsafe(32)
    db.add(
        models.EmailActionToken(
            user_id=user.id,
            token_hash=email_action_token_hash(token),
            purpose=purpose,
            expires_at=datetime.now(UTC) + expires_in,
        )
    )
    db.commit()
    return token


def verify_email_action_token(
    token: str,
    purpose: str,
    db: Session,
) -> models.EmailActionToken | None:
    if not token or len(token) > 128:
        return None
    return db.execute(
        select(models.EmailActionToken)
        .where(
            models.EmailActionToken.token_hash == email_action_token_hash(token),
            models.EmailActionToken.purpose == purpose,
            models.EmailActionToken.consumed_at.is_(None),
            models.EmailActionToken.expires_at > datetime.now(UTC),
        )
        .with_for_update()
    ).scalars().first()


def reset_user_password(token: str, new_password: str, db: Session) -> bool:
    action_token = verify_email_action_token(token, PASSWORD_RESET, db)
    if not action_token:
        return False

    now = datetime.now(UTC)
    claimed = db.execute(
        update(models.EmailActionToken)
        .where(
            models.EmailActionToken.id == action_token.id,
            models.EmailActionToken.purpose == PASSWORD_RESET,
            models.EmailActionToken.consumed_at.is_(None),
            models.EmailActionToken.expires_at > now,
        )
        .values(consumed_at=now)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        return False

    user = db.get(models.User, action_token.user_id)
    if not user:
        db.rollback()
        return False
    user.password_hash = hash_password(new_password)
    user.auth_version += 1
    db.execute(
        delete(models.EmailActionToken).where(
            models.EmailActionToken.user_id == user.id,
            models.EmailActionToken.purpose == PASSWORD_RESET,
        )
    )
    db.commit()
    return True


def login_rate_limit_keys(request: Request, identifier: str) -> list[str]:
    secret = settings.secret_key.get_secret_value().encode("utf-8")
    client_ip = request.client.host if request.client else "unknown"
    values = (f"ip:{client_ip}", f"identifier:{identifier.strip().casefold()}")
    return [
        hmac.new(secret, value.encode("utf-8"), hashlib.sha256).hexdigest()
        for value in values
    ]


def enforce_login_rate_limit(
    db: Session,
    bucket_hashes: list[str],
) -> None:
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=settings.login_rate_window_seconds)
    db.execute(
        delete(models.RateLimitHit).where(
            models.RateLimitHit.created_at < now - timedelta(days=1)
        )
    )
    counts = db.execute(
        select(
            models.RateLimitHit.bucket_hash,
            func.count(models.RateLimitHit.id),
        )
        .where(
            models.RateLimitHit.bucket_hash.in_(bucket_hashes),
            models.RateLimitHit.created_at >= cutoff,
        )
        .group_by(models.RateLimitHit.bucket_hash)
    ).all()
    if any(count >= settings.login_rate_limit for _, count in counts):
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please wait before trying again.",
            headers={"Retry-After": str(settings.login_rate_window_seconds)},
        )


def record_failed_login(db: Session, bucket_hashes: list[str]) -> None:
    now = datetime.now(UTC)
    db.add_all(
        models.RateLimitHit(bucket_hash=bucket_hash, created_at=now)
        for bucket_hash in bucket_hashes
    )
    db.commit()


def clear_login_rate_limit(db: Session, bucket_hashes: list[str]) -> None:
    db.execute(
        delete(models.RateLimitHit).where(
            models.RateLimitHit.bucket_hash.in_(bucket_hashes)
        )
    )
    db.commit()


