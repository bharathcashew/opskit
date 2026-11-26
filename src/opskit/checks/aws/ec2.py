from __future__ import annotations

from opskit import Finding, Status, check
from opskit.checks.aws import name_tag, paginate


@check(
    "aws.ec2.status_checks",
    title="EC2 instance status checks",
    tags=["aws", "ec2", "health"],
)
def ec2_status_checks(ctx):
    """Flags running instances whose system or instance status check is not 'ok'."""
    findings = []
    for region in ctx.regions:
        ec2 = ctx.aws("ec2", region)
        for st in paginate(ec2, "describe_instance_status", "InstanceStatuses"):
            if st["InstanceState"]["Name"] != "running":
                continue
            sys_s = st["SystemStatus"]["Status"]
            inst_s = st["InstanceStatus"]["Status"]
            if sys_s == "impaired" or inst_s == "impaired":
                status = Status.CRITICAL
            elif sys_s in ("ok", "not-applicable") and inst_s in ("ok", "not-applicable"):
                continue
            else:  # initializing / insufficient-data
                status = Status.WARN
            findings.append(
                Finding(
                    resource=st["InstanceId"],
                    region=region,
                    status=status,
                    message=f"system={sys_s}, instance={inst_s}",
                )
            )
    return findings


DEFAULT_SENSITIVE_PORTS = (22, 3389, 3306, 5432, 6379, 9200, 27017)


@check(
    "aws.ec2.open_security_groups",
    title="Security groups open to the internet",
    tags=["aws", "ec2", "security"],
)
def open_security_groups(ctx, sensitive_ports: list[int] | tuple[int, ...] = DEFAULT_SENSITIVE_PORTS):
    """Flags security groups that allow 0.0.0.0/0 or ::/0 on sensitive ports or all ports."""
    ports = set(sensitive_ports)
    findings = []
    for region in ctx.regions:
        ec2 = ctx.aws("ec2", region)
        for sg in paginate(ec2, "describe_security_groups", "SecurityGroups"):
            for perm in sg.get("IpPermissions", []):
                world = [r["CidrIp"] for r in perm.get("IpRanges", []) if r.get("CidrIp") == "0.0.0.0/0"]
                world += [
                    r["CidrIpv6"] for r in perm.get("Ipv6Ranges", []) if r.get("CidrIpv6") == "::/0"
                ]
                if not world:
                    continue
                proto = perm.get("IpProtocol")
                if proto == "-1":
                    exposed = "all ports"
                else:
                    lo, hi = perm.get("FromPort", 0), perm.get("ToPort", 65535)
                    hit = sorted(p for p in ports if lo <= p <= hi)
                    if not hit:
                        continue
                    exposed = ", ".join(map(str, hit))
                findings.append(
                    Finding(
                        resource=f"{sg['GroupId']} ({sg.get('GroupName', '')})",
                        region=region,
                        status=Status.CRITICAL,
                        message=f"{exposed} open to {', '.join(world)}",
                        details={"protocol": proto, "vpc_id": sg.get("VpcId")},
                    )
                )
    return findings


@check(
    "aws.ec2.unattached_volumes",
    title="Unattached EBS volumes",
    tags=["aws", "ec2", "cost"],
)
def unattached_volumes(ctx):
    """EBS volumes in 'available' state are billed but not used."""
    findings = []
    for region in ctx.regions:
        ec2 = ctx.aws("ec2", region)
        for v in paginate(
            ec2, "describe_volumes", "Volumes", Filters=[{"Name": "status", "Values": ["available"]}]
        ):
            label = name_tag(v.get("Tags"))
            findings.append(
                Finding(
                    resource=v["VolumeId"] + (f" ({label})" if label else ""),
                    region=region,
                    status=Status.WARN,
                    message=f"{v['Size']} GiB {v['VolumeType']} volume not attached",
                    details={"size_gib": v["Size"], "type": v["VolumeType"]},
                )
            )
    return findings


@check(
    "aws.ec2.unassociated_eips",
    title="Unassociated Elastic IPs",
    tags=["aws", "ec2", "cost"],
)
def unassociated_eips(ctx):
    """Elastic IPs not attached to anything still cost money."""
    findings = []
    for region in ctx.regions:
        ec2 = ctx.aws("ec2", region)
        for addr in ec2.describe_addresses().get("Addresses", []):
            if addr.get("AssociationId") or addr.get("InstanceId"):
                continue
            findings.append(
                Finding(
                    resource=addr.get("PublicIp", addr.get("AllocationId", "?")),
                    region=region,
                    status=Status.WARN,
                    message="Elastic IP is not associated",
                )
            )
    return findings
