"""
Integration tests for FastAPI API endpoints.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# pyrefly: ignore [missing-import]
from src.api.dependencies import get_settings
# pyrefly: ignore [missing-import]
from src.api.main import app


@pytest_asyncio.fixture
async def client(tmp_path):
    """Create test client."""
    get_settings().db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest.mark.asyncio
async def test_health_check(client):
    """Test health endpoint returns 200."""
    response = await client.get("/api/v1/health/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "model_versions" in data
    assert "faiss_index_size" in data


@pytest.mark.asyncio
async def test_register_and_login(client):
    """Test user registration and login flow."""
    # Register
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": "testuser", "password": "testpassword123", "role": "recruiter"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "testuser"

    # Login
    response = await client.post(
        "/api/v1/auth/token",
        data={"username": "testuser", "password": "testpassword123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_upload_jd_requires_auth(client):
    """Test that JD upload requires authentication."""
    response = await client.post(
        "/api/v1/jobs/",
        json={"jd_text": "x" * 50},
    )
    assert response.status_code == 401
