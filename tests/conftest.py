import pytest

from app.db import engine
from app.services import storage


@pytest.fixture(scope="session", autouse=True)
async def _ensure_test_bucket():
    await storage.ensure_bucket_exists()


@pytest.fixture(autouse=True)
async def _isolate_event_loop_per_test():
    yield
    await engine.dispose()
