import uuid

import boto3
import pytest
from botocore.exceptions import ClientError

from app.config import get_settings
from app.services import storage


def _s3_client():
    settings = get_settings()
    return boto3.client(
        "s3", region_name=settings.aws_region, endpoint_url=settings.aws_endpoint_url)


async def test_upload_and_download_round_trip():
    s3_key = f"test-storage/{uuid.uuid4().hex}.txt"
    body = b"hello from task 4.1"

    await storage.upload(s3_key, body, content_type="text/plain")
    downloaded = await storage.download(s3_key)

    assert downloaded == body

    await storage.delete(s3_key)


async def test_delete_removes_object():
    s3_key = f"test-storage/{uuid.uuid4().hex}.txt"
    await storage.upload(s3_key, b"to be deleted", content_type="text/plain")

    await storage.delete(s3_key)

    with pytest.raises(ClientError):
        _s3_client().head_object(Bucket=get_settings().s3_bucket, Key=s3_key)
