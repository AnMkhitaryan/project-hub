import pytest
from botocore.exceptions import ClientError

from app.services import lambda_deploy

ARN = "arn:aws:lambda:us-east-1:000000000000:function:project-size-recalculator"


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code}}, "SomeOperation")


class FakeLambdaClient:
    def __init__(self, exists: bool, active_states: list[str], add_permission_error=None):
        self.exists = exists
        self._states = list(active_states)
        self.add_permission_error = add_permission_error
        self.calls: list[tuple] = []

    def get_function(self, FunctionName):
        self.calls.append(("get_function",))
        if not self.exists:
            raise _client_error("ResourceNotFoundException")
        state = self._states[0] if len(self._states) == 1 else self._states.pop(0)
        return {
            "Configuration": {
                "FunctionArn": ARN,
                "State": state,
                "LastUpdateStatus": "Successful" if state == "Active" else None,
            }
        }

    def create_function(self, **kwargs):
        self.calls.append(("create_function", kwargs))
        self.exists = True

    def update_function_code(self, **kwargs):
        self.calls.append(("update_function_code", kwargs))

    def update_function_configuration(self, **kwargs):
        self.calls.append(("update_function_configuration", kwargs))

    def add_permission(self, **kwargs):
        self.calls.append(("add_permission", kwargs))
        if self.add_permission_error is not None:
            raise self.add_permission_error


class FakeS3Client:
    def __init__(self):
        self.calls: list[dict] = []

    def put_bucket_notification_configuration(self, **kwargs):
        self.calls.append(kwargs)


def test_wait_until_active_returns_immediately_when_active():
    client = FakeLambdaClient(exists=True, active_states=["Active"])

    lambda_deploy._wait_until_active(client)

    assert [c[0] for c in client.calls] == ["get_function"]


def test_wait_until_active_polls_until_active(monkeypatch):
    monkeypatch.setattr(lambda_deploy.time, "sleep", lambda _: None)
    client = FakeLambdaClient(exists=True, active_states=["Pending", "Pending", "Active"])

    lambda_deploy._wait_until_active(client)

    assert len(client.calls) == 3


def test_wait_until_active_raises_on_failed_state():
    client = FakeLambdaClient(exists=True, active_states=["Failed"])

    with pytest.raises(RuntimeError):
        lambda_deploy._wait_until_active(client)


def test_wait_until_active_raises_on_timeout(monkeypatch):
    ticks = iter([0, 1000])
    monkeypatch.setattr(lambda_deploy.time, "monotonic", lambda: next(ticks))
    client = FakeLambdaClient(exists=True, active_states=["Pending"])

    with pytest.raises(TimeoutError):
        lambda_deploy._wait_until_active(client)


def test_deploy_function_sync_creates_when_missing(monkeypatch):
    fake_lambda = FakeLambdaClient(exists=False, active_states=["Active"])
    monkeypatch.setattr(lambda_deploy.boto3, "client", lambda service, **kw: fake_lambda)

    arn = lambda_deploy._deploy_function_sync()

    assert arn == ARN
    call_names = [c[0] for c in fake_lambda.calls]
    assert "create_function" in call_names
    assert "add_permission" in call_names
    assert "update_function_code" not in call_names
    assert "update_function_configuration" not in call_names


def test_deploy_function_sync_updates_when_existing(monkeypatch):
    fake_lambda = FakeLambdaClient(exists=True, active_states=["Active"])
    monkeypatch.setattr(lambda_deploy.boto3, "client", lambda service, **kw: fake_lambda)

    arn = lambda_deploy._deploy_function_sync()

    assert arn == ARN
    call_names = [c[0] for c in fake_lambda.calls]
    assert "update_function_code" in call_names
    assert "update_function_configuration" in call_names
    assert "create_function" not in call_names
    assert "add_permission" not in call_names


def test_deploy_function_sync_swallows_existing_permission_conflict(monkeypatch):
    fake_lambda = FakeLambdaClient(
        exists=False, active_states=["Active"],
        add_permission_error=_client_error("ResourceConflictException"))
    monkeypatch.setattr(lambda_deploy.boto3, "client", lambda service, **kw: fake_lambda)

    arn = lambda_deploy._deploy_function_sync()

    assert arn == ARN


def test_deploy_function_sync_reraises_other_add_permission_error(monkeypatch):
    fake_lambda = FakeLambdaClient(
        exists=False, active_states=["Active"],
        add_permission_error=_client_error("AccessDenied"))
    monkeypatch.setattr(lambda_deploy.boto3, "client", lambda service, **kw: fake_lambda)

    with pytest.raises(ClientError):
        lambda_deploy._deploy_function_sync()


def test_configure_bucket_notification_sync_wires_events_and_prefix_filter(monkeypatch):
    fake_s3 = FakeS3Client()
    monkeypatch.setattr(lambda_deploy.boto3, "client", lambda service, **kw: fake_s3)

    lambda_deploy._configure_bucket_notification_sync(ARN)

    config = fake_s3.calls[0]["NotificationConfiguration"]["LambdaFunctionConfigurations"][0]
    assert config["LambdaFunctionArn"] == ARN
    assert set(config["Events"]) == {"s3:ObjectCreated:*", "s3:ObjectRemoved:*"}
    assert config["Filter"]["Key"]["FilterRules"] == [{"Name": "prefix", "Value": "projects/"}]


async def test_ensure_lambda_deployed_calls_deploy_then_configures_notification(monkeypatch):
    calls = []
    monkeypatch.setattr(
        lambda_deploy, "_deploy_function_sync",
        lambda: calls.append("deploy") or ARN)
    monkeypatch.setattr(
        lambda_deploy, "_configure_bucket_notification_sync",
        lambda function_arn: calls.append(("configure", function_arn)))

    await lambda_deploy.ensure_lambda_deployed()

    assert calls == ["deploy", ("configure", ARN)]
