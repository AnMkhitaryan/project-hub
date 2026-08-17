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


class _FakeBucketClient:
    def __init__(self, error_code: str | None):
        self.error_code = error_code
        self.created = False

    def head_bucket(self, Bucket):
        if self.error_code is not None:
            raise ClientError({"Error": {"Code": self.error_code}}, "HeadBucket")

    def create_bucket(self, Bucket):
        self.created = True


async def test_ensure_bucket_exists_creates_bucket_when_missing(monkeypatch):
    fake = _FakeBucketClient(error_code="404")
    monkeypatch.setattr(storage, "_client", lambda: fake)

    await storage.ensure_bucket_exists()

    assert fake.created is True


async def test_ensure_bucket_exists_reraises_unexpected_error(monkeypatch):
    fake = _FakeBucketClient(error_code="AccessDenied")
    monkeypatch.setattr(storage, "_client", lambda: fake)

    with pytest.raises(ClientError):
        await storage.ensure_bucket_exists()
