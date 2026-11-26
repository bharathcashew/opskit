from datetime import datetime, timedelta

import boto3

from conftest import REGION
from opskit.core.models import Status
from opskit.core.runner import run_checks


def run(config, check_id, **params):
    if params:
        config = config.model_validate({**config.model_dump(), "checks": {check_id: {"params": params}}})
    return run_checks(config, check_ids=[check_id]).results[0]


def test_open_security_groups(aws, config):
    ec2 = boto3.client("ec2", region_name=REGION)
    bad = ec2.create_security_group(GroupName="bad", Description="x")["GroupId"]
    ec2.authorize_security_group_ingress(
        GroupId=bad,
        IpPermissions=[{"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22,
                        "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}],
    )
    ok = ec2.create_security_group(GroupName="web", Description="x")["GroupId"]
    ec2.authorize_security_group_ingress(
        GroupId=ok,
        IpPermissions=[{"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443,
                        "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}],
    )
    r = run(config, "aws.ec2.open_security_groups")
    assert r.status == Status.CRITICAL
    assert [f.resource.split()[0] for f in r.findings] == [bad]
    assert "22" in r.findings[0].message


def test_unattached_volumes(aws, config):
    ec2 = boto3.client("ec2", region_name=REGION)
    ec2.create_volume(AvailabilityZone=f"{REGION}a", Size=50, VolumeType="gp3")
    r = run(config, "aws.ec2.unattached_volumes")
    assert r.status == Status.WARN and len(r.findings) == 1
    assert r.findings[0].details["size_gib"] == 50


def test_unassociated_eips(aws, config):
    boto3.client("ec2", region_name=REGION).allocate_address(Domain="vpc")
    r = run(config, "aws.ec2.unassociated_eips")
    assert r.status == Status.WARN and len(r.findings) == 1


def test_ec2_status_checks_ok(aws, config):
    ec2 = boto3.client("ec2", region_name=REGION)
    ami = ec2.describe_images()["Images"][0]["ImageId"]
    ec2.run_instances(ImageId=ami, MinCount=1, MaxCount=1, InstanceType="t3.micro")
    assert run(config, "aws.ec2.status_checks").status == Status.OK


def test_alarms_firing(aws, config):
    cw = boto3.client("cloudwatch", region_name=REGION)
    cw.put_metric_alarm(
        AlarmName="high-cpu", MetricName="CPUUtilization", Namespace="AWS/EC2",
        Statistic="Average", Period=60, EvaluationPeriods=1, Threshold=80,
        ComparisonOperator="GreaterThanThreshold",
    )
    assert run(config, "aws.cloudwatch.alarms_firing").status == Status.OK
    cw.set_alarm_state(AlarmName="high-cpu", StateValue="ALARM", StateReason="CPU at 97%")
    r = run(config, "aws.cloudwatch.alarms_firing")
    assert r.status == Status.CRITICAL and r.findings[0].resource == "high-cpu"


def _shift_clock(monkeypatch, days):
    import opskit.checks.aws.iam as iam_mod

    real = datetime

    class Shifted(real):
        @classmethod
        def now(cls, tz=None):
            return real.now(tz) + timedelta(days=days)

    monkeypatch.setattr(iam_mod, "datetime", Shifted)


def test_access_key_age(aws, config, monkeypatch):
    iam = boto3.client("iam")
    iam.create_user(UserName="alice")
    iam.create_access_key(UserName="alice")
    assert run(config, "aws.iam.access_key_age").status == Status.OK

    _shift_clock(monkeypatch, 100)
    r = run(config, "aws.iam.access_key_age")
    assert r.status == Status.WARN and r.findings[0].resource.startswith("alice/")

    _shift_clock(monkeypatch, 200)
    assert run(config, "aws.iam.access_key_age").status == Status.CRITICAL


def test_target_health(aws, config):
    ec2 = boto3.client("ec2", region_name=REGION)
    elb = boto3.client("elbv2", region_name=REGION)
    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]["VpcId"]
    subnets = [
        ec2.create_subnet(
            VpcId=vpc, CidrBlock=f"10.0.{i}.0/24", AvailabilityZone=f"{REGION}{az}"
        )["Subnet"]["SubnetId"]
        for i, az in enumerate("ab")
    ]
    lb = elb.create_load_balancer(Name="web", Subnets=subnets)["LoadBalancers"][0]["LoadBalancerArn"]
    tg = elb.create_target_group(Name="web-tg", Protocol="HTTP", Port=80, VpcId=vpc)["TargetGroups"][0]
    elb.create_listener(LoadBalancerArn=lb, Protocol="HTTP", Port=80,
                        DefaultActions=[{"Type": "forward", "TargetGroupArn": tg["TargetGroupArn"]}])
    r = run(config, "aws.elbv2.target_health")
    # No registered targets behind a live LB is worth a warning.
    assert r.status == Status.WARN
    assert r.findings[0].resource == "web-tg"
