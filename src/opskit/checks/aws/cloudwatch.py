from __future__ import annotations

from opskit import Finding, Status, check
from opskit.checks.aws import paginate


@check(
    "aws.cloudwatch.alarms_firing",
    title="CloudWatch alarms in ALARM state",
    tags=["aws", "cloudwatch", "health"],
)
def alarms_firing(ctx, warn_on_insufficient_data: bool = False):
    """Lists metric alarms currently firing, optionally also those with insufficient data."""
    states = ["ALARM"] + (["INSUFFICIENT_DATA"] if warn_on_insufficient_data else [])
    findings = []
    for region in ctx.regions:
        cw = ctx.aws("cloudwatch", region)
        for state in states:
            for alarm in paginate(cw, "describe_alarms", "MetricAlarms", StateValue=state):
                findings.append(
                    Finding(
                        resource=alarm["AlarmName"],
                        region=region,
                        status=Status.CRITICAL if state == "ALARM" else Status.WARN,
                        message=alarm.get("StateReason", state)[:300],
                        details={"metric": alarm.get("MetricName"), "namespace": alarm.get("Namespace")},
                    )
                )
    return findings
