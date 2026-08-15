import pytest

from app.db import engine


@pytest.fixture(autouse=True)
async def _isolate_event_loop_per_test():
    yield
    await engine.dispose()
