import asyncio
from functools import lru_cache

import boto3

from app.config import get_settings


@lru_cache
def _client():
    settings = get_settings()
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        endpoint_url=settings.aws_endpoint_url,
    )


async def delete(s3_key: str) -> None:
    await delete_many([s3_key])


async def delete_many(s3_keys: list[str]) -> None:
    if not s3_keys:
        return
    settings = get_settings()
    await asyncio.to_thread(
        _client().delete_objects,
        Bucket=settings.s3_bucket,
        Delete={"Objects": [{"Key": key} for key in s3_keys]},
    )
