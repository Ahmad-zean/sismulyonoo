import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

import models
from config import settings
from database import get_db
from email_service import EmailDeliveryError, send_password_reset_email
from schema import (
    CreateUser,
    PasswordChange,
    PasswordReset,
    PasswordResetRequest,
    PasswordResetRequestResponse,
    RegistrationResponse,
    Token,
    UserPublic,
    UserResponse,
    UserUpdate,
)
from security import require_header_csrf
from services import (
    ACCESS_TOKEN_COOKIE,
    PASSWORD_RESET,
    authenticate_user,
    clear_login_rate_limit,
    create_access_token,
    enforce_login_rate_limit,
    hash_password,
    login_rate_limit_keys,
    create_email_action_token,
    register_user,
    record_failed_login,
    require_authenticated_user,
    reset_user_password,
    update_user_account,
    verify_password,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/Users", tags=["Users"])


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> models.User:
    return require_authenticated_user(request, db)


def clear_access_cookie(response: Response) -> None:
    response.delete_cookie(
        key=ACCESS_TOKEN_COOKIE,
        path="/",
        secure=settings.app_env == "production",
        samesite="lax",
    )


def set_access_cookie(response: Response, user: models.User) -> str:
    access_token = create_access_token(user.id, user.auth_version)
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=access_token,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )
    return access_token


@router.post("", response_model=RegistrationResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    request: Request,
    user: CreateUser,
    response: Response,
    db: Session = Depends(get_db),
):
    rate_limit_keys = login_rate_limit_keys(request, f"register:{user.email}")
    enforce_login_rate_limit(db, rate_limit_keys)
    record_failed_login(db, rate_limit_keys)
    created_user = register_user(user, user.confirm_password, db)
    set_access_cookie(response, created_user)
    return RegistrationResponse(
        user=created_user,
        message="Akun berhasil dibuat.",
    )


@router.post(
    "/password/forgot",
    response_model=PasswordResetRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_password_reset(
    request: Request,
    payload: PasswordResetRequest,
    db: Session = Depends(get_db),
):
    rate_limit_keys = login_rate_limit_keys(
        request,
        f"password-reset:{payload.email}",
    )
    enforce_login_rate_limit(db, rate_limit_keys)
    record_failed_login(db, rate_limit_keys)

    user = db.execute(
        select(models.User).where(models.User.email == payload.email)
    ).scalars().first()
    if user is not None:
        token = create_email_action_token(user, PASSWORD_RESET, db)
        try:
            send_password_reset_email(user.email, token)
        except EmailDeliveryError:
            logger.exception(
                "Password reset email could not be delivered for user_id=%s.",
                user.id,
            )
            if settings.app_env == "development":
                return PasswordResetRequestResponse(
                    message="Email tidak dapat dikirim. Gunakan tautan reset ini.",
                    reset_url=str(
                        request.url_for("reset_password_page", token=token)
                    ),
                )

    return PasswordResetRequestResponse(
        message="Jika email terdaftar, tautan reset password akan dikirim."
    )


@router.post("/password/reset")
def reset_password(
    payload: PasswordReset,
    response: Response,
    db: Session = Depends(get_db),
):
    if payload.new_password != payload.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New passwords do not match.",
        )
    if not reset_user_password(payload.token, payload.new_password, db):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset link is invalid or has expired. Request a new one.",
        )

    clear_access_cookie(response)
    return {"message": "Password berhasil diubah. Silakan masuk kembali."}


@router.get("/me", response_model=UserResponse)
def read_current_user(user: models.User = Depends(get_current_user)):
    return user


@router.patch("/me")
def update_current_user(
    profile: UserUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
    _: None = Depends(require_header_csrf),
):
    updated_user = update_user_account(user, profile, db)
    return UserResponse.model_validate(updated_user).model_dump(mode="json")


@router.post("/me/password")
def change_password(
    payload: PasswordChange,
    response: Response,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
    _: None = Depends(require_header_csrf),
):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )
    if payload.new_password != payload.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New passwords do not match.",
        )

    update_user_account(
        user,
        UserUpdate(),
        db,
        password_hash=hash_password(payload.new_password),
    )
    clear_access_cookie(response)
    return {"message": "Password changed. Please log in again."}


@router.post("/logout")
def logout(
    response: Response,
    _: None = Depends(require_header_csrf),
):
    clear_access_cookie(response)
    return {"message": "Logged out."}


@router.get("/{user_id}", response_model=UserPublic)
def read_user(user_id: int, db: Session = Depends(get_db)):
    user = db.execute(
        select(models.User).where(models.User.id == user_id)
    ).scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


@router.post("/token", response_model=Token)
def login_for_access_token(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    rate_limit_keys = login_rate_limit_keys(request, form_data.username)
    enforce_login_rate_limit(db, rate_limit_keys)
    try:
        user = authenticate_user(form_data.username, form_data.password, db)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            record_failed_login(db, rate_limit_keys)
        raise
    clear_login_rate_limit(db, rate_limit_keys)
    access_token = set_access_cookie(response, user)
    return Token(
        access_token=access_token,
        token_type="bearer",
    )
