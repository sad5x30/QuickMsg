from pathlib import Path
import sys

import pytest
from httpx import ASGITransport, AsyncClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from main import app
from db import get_db

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


