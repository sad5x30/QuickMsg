from pathlib import Path
import sys

import pytest
from httpx import ASGITransport, AsyncClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from main import app
from models.users_models import Users
from services.auth import get_db, hash_password


class FakeResult:
    def __init__(self, user):
        self._user = user

    def scalar_one_or_none(self):
        return self._user


class FakeAsyncSession:
    def __init__(self):
        self.users_by_username = {}
        self._next_id = 1

    async def execute(self, statement):
        params = statement.compile().params
        username = next(iter(params.values()), None)
        user = self.users_by_username.get(username)
        return FakeResult(user)

    def add(self, user):
        if user.id is None:
            user.id = self._next_id
            self._next_id += 1
        self.users_by_username[user.username] = user

    async def commit(self):
        return None

    async def refresh(self, user):
        return user


@pytest.fixture
def fake_session():
    return FakeAsyncSession()


@pytest.fixture
async def client(fake_session):
    async def override_get_db():
        yield fake_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=False,
    ) as async_client:
        yield async_client

    app.dependency_overrides.clear()


def create_user(fake_session, username: str, password: str):
    user = Users(
        id=fake_session._next_id,
        username=username,
        password=hash_password(password),
    )
    fake_session._next_id += 1
    fake_session.users_by_username[username] = user
    return user


@pytest.mark.anyio
async def test_login_success_returns_redirect_and_cookie(client, fake_session):
    create_user(fake_session, "alice", "secret123")

    response = await client.post(
        "/login",
        data={"username": "alice", "password": "secret123"},
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert "access_token=" in response.headers["set-cookie"]


@pytest.mark.anyio
async def test_login_returns_404_for_unknown_user(client):
    response = await client.post(
        "/login",
        data={"username": "missing_user", "password": "secret123"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Not found"}


@pytest.mark.anyio
async def test_login_returns_401_for_wrong_password(client, fake_session):
    create_user(fake_session, "alice", "secret123")

    response = await client.post(
        "/login",
        data={"username": "alice", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "wrong password"}


@pytest.mark.anyio
async def test_registration_creates_user_and_redirects_to_login(client, fake_session):
    response = await client.post(
        "/register",
        data={"username": "sad", "password": "sosal?"},
    )

    saved_user = fake_session.users_by_username["sad"]

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert saved_user.username == "sad"
    assert saved_user.password != "sosal?"
    assert saved_user.password.startswith("$2")
