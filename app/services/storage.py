import asyncio
from collections.abc import AsyncIterator
from functools import lru_cache

import boto3
from botocore.exceptions import ClientError

from app.config import get_settings

_CHUNK_SIZE = 1024 * 1024


@lru_cache
def _client():
    settings = get_settings()
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        endpoint_url=settings.aws_endpoint_url,)


async def ensure_bucket_exists() -> None:
    settings = get_settings()
    client = _client()
    try:
        await asyncio.to_thread(client.head_bucket, Bucket=settings.s3_bucket)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code not in ("404", "NoSuchBucket"):
            raise
        await asyncio.to_thread(client.create_bucket, Bucket=settings.s3_bucket)


async def upload(s3_key: str, body: bytes, content_type: str) -> None:
    settings = get_settings()
    await asyncio.to_thread(
        _client().put_object,
        Bucket=settings.s3_bucket,
        Key=s3_key,
        Body=body,
        ContentType=content_type,)


async def download(s3_key: str) -> bytes:
    settings = get_settings()
    response = await asyncio.to_thread(
        _client().get_object, Bucket=settings.s3_bucket, Key=s3_key
    )
    return await asyncio.to_thread(response["Body"].read)


async def download_stream(s3_key: str) -> AsyncIterator[bytes]:
    settings = get_settings()
    response = await asyncio.to_thread(
        _client().get_object, Bucket=settings.s3_bucket, Key=s3_key)
    body = response["Body"]
    try:
        while True:
            chunk = await asyncio.to_thread(body.read, _CHUNK_SIZE)
            if not chunk:
                break
            yield chunk
    finally:
        body.close()


async def delete(s3_key: str) -> None:
    await delete_many([s3_key])


async def delete_many(s3_keys: list[str]) -> None:
    if not s3_keys:
        return
    settings = get_settings()
    await asyncio.to_thread(
        _client().delete_objects,
        Bucket=settings.s3_bucket,
        Delete={"Objects": [{"Key": key} for key in s3_keys]},)
