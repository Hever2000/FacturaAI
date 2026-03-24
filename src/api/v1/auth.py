from fastapi import APIRouter, HTTPException, status

from src.api.deps import CurrentUser, DBSession
from src.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    Token,
    UserCreate,
    UserMeResponse,
    UserResponse,
)
from src.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    db: DBSession,
) -> UserResponse:
    """Register a new user account."""
    auth_service = AuthService(db)

    existing_user = await auth_service.get_user_by_email(user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    user = await auth_service.create_user(user_data)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=Token)
async def login(
    login_data: LoginRequest,
    db: DBSession,
) -> Token:
    """Login with email and password."""
    auth_service = AuthService(db)

    user = await auth_service.authenticate_user(
        login_data.email,
        login_data.password,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return await auth_service.create_tokens_for_user(user)


@router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_data: RefreshTokenRequest,
    db: DBSession,
) -> Token:
    """Refresh access token using refresh token."""
    auth_service = AuthService(db)

    tokens = await auth_service.refresh_tokens(refresh_data.refresh_token)
    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return tokens


@router.get("/me", response_model=UserMeResponse)
async def get_current_user_info(
    current_user: CurrentUser,
) -> UserMeResponse:
    """Get current user information."""
    return UserMeResponse(
        **UserResponse.model_validate(current_user).model_dump(),
        monthly_limit=current_user.request_limit,
        requests_remaining=current_user.request_limit - current_user.monthly_request_count,
    )


@router.post("/logout")
async def logout(
    logout_data: LogoutRequest,
    db: DBSession,
) -> dict:
    """
    Logout a user by invalidating their refresh token.
    """
    auth_service = AuthService(db)

    success = await auth_service.logout(logout_data.refresh_token)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid refresh token",
        )

    return {"message": "Successfully logged out"}
