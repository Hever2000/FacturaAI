"""Pytest configuration and fixtures for FacturaAI tests."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.security import create_access_token
from src.db.session import Base


# ---------------------------------------------------------------------------
# Test database — SQLite in-memory for speed and isolation
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def test_engine():
    """Create a SQLite in-memory engine for tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False},
    )
    return engine


@pytest_asyncio.fixture(scope="function")
async def init_db(test_engine):
    """Create all tables for each test function."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def db_session_factory(test_engine, init_db):
    """Create a session factory for each test function."""
    return async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


@pytest_asyncio.fixture(scope="function")
async def db_session(db_session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Provide a fresh db session for each test with rollback after."""
    async with db_session_factory() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# App + async client fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client with overridden dependencies."""
    from src.api.main import app
    from src.db import get_db

    # Override get_db to use test session
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # Patch Redis-based rate limiter to always allow
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value="0")
    mock_redis.pipeline = AsyncMock()
    mock_redis.pipeline.return_value.incr = AsyncMock()
    mock_redis.pipeline.return_value.expire = AsyncMock()
    mock_redis.pipeline.return_value.execute = AsyncMock()
    mock_redis.ttl = AsyncMock(return_value=30)
    with (
        patch("src.db.redis.get_redis", return_value=mock_redis),
        patch(
            "src.api.deps.rate_limiter.is_allowed",
            new_callable=AsyncMock,
            return_value=(True, 1, 60),
        ),
        patch(
            "src.api.deps.rate_limiter.get_current_usage",
            new_callable=AsyncMock,
            return_value=(1, 60),
        ),
        patch("src.api.deps.rate_limiter.get_ttl", new_callable=AsyncMock, return_value=30),
        patch(
            "src.services.apikey.rate_limiter.is_allowed",
            new_callable=AsyncMock,
            return_value=(True, 1, 60),
        ),
        patch(
            "src.services.apikey.rate_limiter.get_current_usage",
            new_callable=AsyncMock,
            return_value=(1, 60),
        ),
        patch("src.services.apikey.rate_limiter.get_ttl", new_callable=AsyncMock, return_value=30),
    ):

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession):
    """Create a verified test user."""
    from src.core.security import get_password_hash
    from src.models.user import User

    user = User(
        email="test@facturaai.com",
        full_name="Test User",
        hashed_password=get_password_hash("TestPass123!"),
        is_active=True,
        is_verified=True,
        subscription_tier="free",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_headers(test_user) -> dict[str, str]:
    """Return Authorization headers with a valid JWT."""
    token = create_access_token(subject=str(test_user.id))
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient, auth_headers: dict) -> AsyncClient:
    """Client pre-authenticated with JWT."""
    client.headers.update(auth_headers)
    return client


# ---------------------------------------------------------------------------
# Mock data fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_ocr_result() -> dict:
    """Mock successful OCR result."""
    return {
        "raw_text": [{"text": "FACTURA A #001-00012345", "confidence": 0.99}],
        "full_text": "FACTURA A #001-00012345 | Total: $150.000,00",
        "status": "OCR_COMPLETED",
        "ocr_engine": "paddleocr",
    }


@pytest.fixture
def mock_llm_extraction() -> dict:
    """Mock successful LLM extraction result."""
    return {
        "tipo_comprobante": "FC",
        "letra_comprobante": "A",
        "punto_de_venta": "0001",
        "numero_comprobante": "00012345",
        "fecha_emision": "2025-03-15",
        "cae": "12345678901234",
        "fecha_vencimiento_cae": "2025-04-14",
        "razon_social_vendedor": "Acme SA",
        "vendedor_cuit": "30-12345678-9",
        "vendedor_condicion_iva": "IVA Responsable Inscripto",
        "vendedor_domicilio": "Av. Corrientes 1234",
        "vendedor_localidad": "CABA, CP 1043",
        "razon_social_cliente": "Cliente Ejemplo SRL",
        "cliente_cuit": "30-87654321-0",
        "cliente_condicion_iva": "IVA Responsable Inscripto",
        "cliente_domicilio": "Calle Falsa 123",
        "cliente_localidad": "Buenos Aires",
        "subtotal": 123966.94,
        "total": 150000.00,
        "importe_neto_gravado": 123966.94,
        "importe_neto_no_gravado": 0.0,
        "importe_exento": 0.0,
        "iva_21": 26013.06,
        "iva_10_5": 0.0,
        "iva_5": 0.0,
        "iva_27": 0.0,
        "total_iva": 26013.06,
        "condicion_pago": "Contado",
        "items": [
            {
                "item_numero": 1,
                "descripcion": "Servicio de desarrollo",
                "cantidad": 1.0,
                "precio_unitario": 123966.94,
                "total_item": 150000.00,
            }
        ],
    }


@pytest.fixture
def mock_mp_preapproval_created() -> dict:
    """Mock MP preapproval.created webhook body."""
    return {
        "id": 12345,
        "live_mode": False,
        "type": "preapproval",
        "date_created": "2025-03-15T10:00:00.000-03:00",
        "user_id": "44444",
        "api_version": "v1",
        "action": "preapproval.created",
        "data": {"id": "MP-PREAPPROVAL-123"},
    }


@pytest.fixture
def mock_mp_preapproval_cancelled() -> dict:
    """Mock MP preapproval.cancelled webhook body."""
    return {
        "id": 12346,
        "live_mode": False,
        "type": "preapproval",
        "date_created": "2025-03-15T10:00:00.000-03:00",
        "user_id": "44444",
        "api_version": "v1",
        "action": "preapproval.cancelled",
        "data": {"id": "MP-PREAPPROVAL-123"},
    }


# ---------------------------------------------------------------------------
# Storage fixture
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_storage(tmp_path, monkeypatch):
    """Use a temp directory for file storage in tests."""
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    monkeypatch.setattr("src.core.config.settings.STORAGE_PATH", str(storage_dir))
    return storage_dir
