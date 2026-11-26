import pytest

from opskit import Finding, Status, check
from opskit.core.config import load_config
from opskit.core.models import RunReport
from opskit.core.registry import get_check, list_checks
from opskit.core.runner import run_checks


@check("test.always_warn", title="always warns", tags=["test"])
def _always_warn(ctx, label: str = "x"):
    return [Finding(resource=label, message="hi", status=Status.WARN)]


@check("test.boom", title="raises", tags=["test-error"])
def _boom(ctx):
    raise RuntimeError("kaboom")


def test_worst_status():
    assert Status.worst([]) == Status.OK
    assert Status.worst([Status.OK, Status.WARN, Status.CRITICAL]) == Status.CRITICAL
    assert Status.worst([Status.ERROR, Status.WARN]) == Status.ERROR


def test_exit_codes():
    assert RunReport(status=Status.OK).exit_code == 0
    assert RunReport(status=Status.WARN).exit_code == 1
    assert RunReport(status=Status.CRITICAL).exit_code == 2
    assert RunReport(status=Status.ERROR).exit_code == 2


def test_builtin_checks_registered():
    ids = {s.id for s in list_checks()}
    assert {"aws.ec2.status_checks", "aws.elbv2.target_health", "aws.iam.access_key_age"} <= ids


def test_params_introspected():
    assert get_check("aws.iam.access_key_age").params == {"max_age_days": 90}


def test_tag_filter(config):
    report = run_checks(config, tags=["test"])
    assert [r.check_id for r in report.results] == ["test.always_warn"]
    assert report.status == Status.WARN


def test_params_from_config(config):
    config = config.model_validate(
        {**config.model_dump(), "checks": {"test.always_warn": {"params": {"label": "custom"}}}}
    )
    report = run_checks(config, check_ids=["test.always_warn"])
    assert report.results[0].findings[0].resource == "custom"


def test_exception_becomes_error(config):
    report = run_checks(config, check_ids=["test.boom"])
    r = report.results[0]
    assert r.status == Status.ERROR and "kaboom" in r.error


def test_disabled_check_skipped(config):
    off = {"test.always_warn": {"enabled": False}}
    config = config.model_validate({**config.model_dump(), "checks": off})
    assert run_checks(config, tags=["test"]).results == []


def test_unknown_check(config):
    with pytest.raises(KeyError):
        run_checks(config, check_ids=["nope"])


def test_config_shorthand(tmp_path, monkeypatch):
    p = tmp_path / "opskit.yaml"
    p.write_text("aws:\n  regions: [eu-west-1]\nchecks:\n  aws.iam.access_key_age:\n    max_age_days: 30\n")
    monkeypatch.setenv("OPSKIT_API_TOKEN", "secret")
    cfg = load_config(p)
    assert cfg.aws.regions == ["eu-west-1"]
    assert cfg.check_config("aws.iam.access_key_age").params == {"max_age_days": 30}
    assert cfg.api.token == "secret"
