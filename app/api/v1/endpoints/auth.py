from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import Any
from app.api.deps import get_db, get_current_user
from app.services.user_service import UserService
from app.schemas.user import Token, LoginRequest, RefreshTokenRequest, UserResponse
from app.models import User

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


@router.post("/login", response_model=Token)
def login(
    *,
    db: Session = Depends(get_db),
    form_data: LoginRequest,
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    user = UserService.authenticate(
        db, 
        username=form_data.username, 
        password=form_data.password
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    elif not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )
    
    return UserService.create_tokens(db, user)


@router.post("/refresh", response_model=Token)
def refresh_token(
    *,
    db: Session = Depends(get_db),
    token_data: RefreshTokenRequest,
) -> Any:
    """
    Refresh access token
    """
    user = UserService.verify_refresh_token(db, token_data.refresh_token)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    
    return UserService.create_tokens(db, user)


@router.post("/logout")
def logout(
    *,
    db: Session = Depends(get_db),
    token_data: RefreshTokenRequest,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Revoke refresh token (logout)
    """
    success = UserService.revoke_refresh_token(db, token_data.refresh_token)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid refresh token",
        )
    
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserResponse)
def read_users_me(
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get current user
    """
    return current_user