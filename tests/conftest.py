import boto3
import pytest
from botocore.exceptions import ClientError

from app.config import get_settings
from app.db import engine


@pytest.fixture(scope="session", autouse=True)
def _ensure_test_bucket():
    settings = get_settings()
    client = boto3.client(
        "s3", region_name=settings.aws_region, endpoint_url=settings.aws_endpoint_url
    )
    try:
        client.create_bucket(Bucket=settings.s3_bucket)
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            raise


@pytest.fixture(autouse=True)
async def _isolate_event_loop_per_test():
    yield
    await engine.dispose()
