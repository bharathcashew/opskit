import boto3
import pytest
from fastapi.testclient import TestClient

from conftest import REGION
from opskit.api.app import create_app


@pytest.fixture
def client(aws, config):
    return TestClient(create_app(config))


@pytest.fixture
def secured(aws, config):
    config.api.token = "s3cret"
    return TestClient(create_app(config))


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_list_checks_by_tag(client):
    checks = client.get("/v1/checks", params={"tag": "cost"}).json()
    assert {c["id"] for c in checks} == {"aws.ec2.unattached_volumes", "aws.ec2.unassociated_eips"}
    assert all("params" in c for c in checks)


def test_run_store_and_metrics(client):
    boto3.client("ec2", region_name=REGION).allocate_address(Domain="vpc")
    resp = client.post("/v1/runs", json={"checks": ["aws.ec2.unassociated_eips"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "warn"

    assert client.get(f"/v1/runs/{body['run_id']}").json()["run_id"] == body["run_id"]
    assert client.get("/v1/runs").json()[0]["run_id"] == body["run_id"]
    assert client.get("/v1/runs/missing").status_code == 404

    m = client.get("/metrics").text
    assert 'opskit_check_status{check="aws.ec2.unassociated_eips"} 1' in m
    assert 'opskit_check_findings{check="aws.ec2.unassociated_eips"} 1' in m


def test_unknown_check_is_400(client):
    assert client.post("/v1/runs", json={"checks": ["nope"]}).status_code == 400


def test_auth(secured):
    assert secured.get("/health").status_code == 200  # probes stay open
    assert secured.get("/v1/checks").status_code == 401
    assert secured.get("/v1/checks", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert secured.get("/v1/checks", headers={"Authorization": "Bearer s3cret"}).status_code == 200
