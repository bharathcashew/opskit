import os

import pytest
from moto import mock_aws

from opskit.core.config import Config
from opskit.core.registry import load_plugins

REGION = "us-east-1"


@pytest.fixture(autouse=True)
def fake_aws_env(monkeypatch):
    for k, v in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": REGION,
    }.items():
        monkeypatch.setenv(k, v)
    for k in ("AWS_PROFILE", "OPSKIT_API_TOKEN", "OPSKIT_CONFIG", "OPSKIT_AWS_REGIONS"):
        monkeypatch.delenv(k, raising=False)
    os.chdir(os.path.dirname(__file__))  # avoid picking up a stray ./opskit.yaml
    load_plugins()


@pytest.fixture
def aws():
    with mock_aws():
        yield


@pytest.fixture
def config():
    cfg = Config()
    cfg.aws.regions = [REGION]
    return cfg
