"""Tests for authentication endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test health check endpoint (no auth required)."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "factura-ai"


@pytest.mark.asyncio
async def test_docs_available(client: AsyncClient):
    """Test OpenAPI docs are available."""
    response = await client.get("/docs")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    """Test user registration with valid data."""
    response = await client.post(
        "/v1/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "SecurePass123!",
            "full_name": "New User",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert data["full_name"] == "New User"
    assert data["is_active"] is True
    assert data["is_verified"] is False
    assert data["subscription_tier"] == "free"
    assert "id" in data
    assert "password" not in data
    assert "hashed_password" not in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, test_user):
    """Test registration fails with duplicate email."""
    response = await client.post(
        "/v1/auth/register",
        json={
            "email": test_user.email,
            "password": "SecurePass123!",
        },
    )
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"]


@pytest.mark.asyncio
async def test_register_invalid_email(client: AsyncClient):
    """Test registration fails with invalid email format."""
    response = await client.post(
        "/v1/auth/register",
        json={
            "email": "not-an-email",
            "password": "SecurePass123!",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_short_password(client: AsyncClient):
    """Test registration fails with too-short password."""
    response = await client.post(
        "/v1/auth/register",
        json={
            "email": "user@example.com",
            "password": "short",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user):
    """Test login with correct credentials."""
    response = await client.post(
        "/v1/auth/login",
        json={
            "email": test_user.email,
            "password": "TestPass123!",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert "expires_in" in data


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, test_user):
    """Test login fails with wrong password."""
    response = await client.post(
        "/v1/auth/login",
        json={
            "email": test_user.email,
            "password": "WrongPassword!",
        },
    )
    assert response.status_code == 401
    assert "Incorrect email or password" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    """Test login fails for non-existent user."""
    response = await client.post(
        "/v1/auth/login",
        json={
            "email": "nobody@example.com",
            "password": "AnyPassword123!",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_success(auth_client: AsyncClient, test_user):
    """Test getting current user info."""
    response = await auth_client.get("/v1/auth/me")
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_user.email
    assert data["full_name"] == test_user.full_name
    assert data["subscription_tier"] == "free"
    assert "monthly_limit" in data
    assert "requests_remaining" in data


@pytest.mark.asyncio
async def test_get_me_unauthorized(client: AsyncClient):
    """Test /me endpoint requires authentication."""
    response = await client.get("/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient, test_user):
    """Test token refresh flow."""
    # Login to get tokens
    login_response = await client.post(
        "/v1/auth/login",
        json={"email": test_user.email, "password": "TestPass123!"},
    )
    tokens = login_response.json()
    refresh_token = tokens["refresh_token"]

    # Use refresh token
    response = await client.post(
        "/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_refresh_token_invalid(client: AsyncClient):
    """Test refresh fails with invalid token."""
    response = await client.post(
        "/v1/auth/refresh",
        json={"refresh_token": "invalid.token.here"},
    )
    assert response.status_code == 401
