from __future__ import annotations

from opskit import Finding, Status, check
from opskit.checks.aws import paginate


@check(
    "aws.elbv2.target_health",
    title="Load balancer target health",
    tags=["aws", "elb", "health"],
)
def target_health(ctx, min_healthy_pct: int = 50):
    """Checks ALB/NLB target groups for unhealthy targets and low healthy capacity."""
    findings = []
    for region in ctx.regions:
        elb = ctx.aws("elbv2", region)
        for tg in paginate(elb, "describe_target_groups", "TargetGroups"):
            if not tg.get("LoadBalancerArns"):
                continue  # not attached to a load balancer, nothing to serve
            descs = elb.describe_target_health(TargetGroupArn=tg["TargetGroupArn"])[
                "TargetHealthDescriptions"
            ]
            name = tg["TargetGroupName"]
            if not descs:
                findings.append(
                    Finding(resource=name, region=region, status=Status.WARN,
                            message="target group has no registered targets")
                )
                continue
            states = [d["TargetHealth"]["State"] for d in descs]
            healthy = states.count("healthy")
            unhealthy = [
                d["Target"]["Id"] for d in descs if d["TargetHealth"]["State"] == "unhealthy"
            ]
            pct = round(100 * healthy / len(states))
            if healthy == 0:
                status = Status.CRITICAL
            elif pct < min_healthy_pct or unhealthy:
                status = Status.WARN
            else:
                continue
            findings.append(
                Finding(
                    resource=name,
                    region=region,
                    status=status,
                    message=f"{healthy}/{len(states)} targets healthy ({pct}%)",
                    details={"unhealthy_targets": unhealthy, "states": states},
                )
            )
    return findings
