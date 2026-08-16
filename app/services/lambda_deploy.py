import asyncio
import io
import time
import zipfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from app.config import get_settings

FUNCTION_NAME = "project-size-recalculator"
HANDLER_PATH = Path(__file__).resolve().parents[2] / "lambda" / "size_recalculator" / "handler.py"
_ACTIVE_WAIT_TIMEOUT_SECONDS = 60
_ACTIVE_WAIT_POLL_SECONDS = 1


def _build_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(HANDLER_PATH, arcname="handler.py")
    return buffer.getvalue()


def _deploy_function_sync() -> str:
    settings = get_settings()
    client = boto3.client(
        "lambda", region_name=settings.aws_region, endpoint_url=settings.aws_endpoint_url
    )
    zip_bytes = _build_zip()
    env = {
        "Variables": {
            "API_BASE_URL": settings.api_base_url,
            "INTERNAL_API_SECRET": settings.internal_api_secret,
        }
    }

    exists = True
    try:
        client.get_function(FunctionName=FUNCTION_NAME)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
            raise
        exists = False

    if exists:
        client.update_function_code(FunctionName=FUNCTION_NAME, ZipFile=zip_bytes)
        _wait_until_active(client)
        client.update_function_configuration(FunctionName=FUNCTION_NAME, Environment=env)
    else:
        client.create_function(
            FunctionName=FUNCTION_NAME,
            Runtime="python3.12",
            Role="arn:aws:iam::000000000000:role/lambda-role",
            Handler="handler.handler",
            Code={"ZipFile": zip_bytes},
            Environment=env,
            Timeout=30,
        )
        try:
            client.add_permission(
                FunctionName=FUNCTION_NAME,
                StatementId="AllowS3Invoke",
                Action="lambda:InvokeFunction",
                Principal="s3.amazonaws.com",
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ResourceConflictException":
                raise

    _wait_until_active(client)
    response = client.get_function(FunctionName=FUNCTION_NAME)
    return response["Configuration"]["FunctionArn"]


def _wait_until_active(client) -> None:
    deadline = time.monotonic() + _ACTIVE_WAIT_TIMEOUT_SECONDS
    while True:
        response = client.get_function(FunctionName=FUNCTION_NAME)
        config = response["Configuration"]
        state = config.get("State")
        last_update_status = config.get("LastUpdateStatus")
        if state == "Active" and last_update_status in (None, "Successful"):
            return
        if state == "Failed" or last_update_status == "Failed":
            raise RuntimeError(
                f"Lambda {FUNCTION_NAME} failed to become active: "
                f"state={state} last_update_status={last_update_status}"
            )
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"Timed out waiting for Lambda {FUNCTION_NAME} to become active "
                f"(state={state}, last_update_status={last_update_status})"
            )
        time.sleep(_ACTIVE_WAIT_POLL_SECONDS)


def _configure_bucket_notification_sync(function_arn: str) -> None:
    settings = get_settings()
    client = boto3.client(
        "s3", region_name=settings.aws_region, endpoint_url=settings.aws_endpoint_url
    )
    client.put_bucket_notification_configuration(
        Bucket=settings.s3_bucket,
        NotificationConfiguration={
            "LambdaFunctionConfigurations": [
                {
                    "LambdaFunctionArn": function_arn,
                    "Events": ["s3:ObjectCreated:*", "s3:ObjectRemoved:*"],
                    "Filter": {
                        "Key": {"FilterRules": [{"Name": "prefix", "Value": "projects/"}]}
                    },
                }
            ]
        },
    )


async def ensure_lambda_deployed() -> None:
    function_arn = await asyncio.to_thread(_deploy_function_sync)
    await asyncio.to_thread(_configure_bucket_notification_sync, function_arn)
