from opskit import Finding, Status, check
from opskit.checks.aws import paginate


@check(
    "acme.ec2.missing_required_tags",
    title="Instances missing required tags",
    tags=["aws", "ec2", "governance"],
)
def missing_required_tags(ctx, required: list[str] | None = None):
    """Flags EC2 instances that lack any of the required tags."""
    required = required or ["Owner", "Environment"]
    findings = []
    for region in ctx.regions:
        ec2 = ctx.aws("ec2", region)
        for res in paginate(ec2, "describe_instances", "Reservations"):
            for inst in res["Instances"]:
                keys = {t["Key"] for t in inst.get("Tags", [])}
                missing = [k for k in required if k not in keys]
                if missing:
                    findings.append(
                        Finding(
                            resource=inst["InstanceId"],
                            region=region,
                            status=Status.WARN,
                            message=f"missing tags: {', '.join(missing)}",
                        )
                    )
    return findings
