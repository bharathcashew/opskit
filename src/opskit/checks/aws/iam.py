from __future__ import annotations

from datetime import datetime, timezone

from opskit import Finding, Status, check
from opskit.checks.aws import paginate


@check(
    "aws.iam.access_key_age",
    title="Old IAM access keys",
    tags=["aws", "iam", "security"],
)
def access_key_age(ctx, max_age_days: int = 90):
    """Active access keys older than max_age_days (warn) or twice that (critical)."""
    iam = ctx.aws("iam")  # global service
    now = datetime.now(timezone.utc)
    findings = []
    for user in paginate(iam, "list_users", "Users"):
        for key in iam.list_access_keys(UserName=user["UserName"])["AccessKeyMetadata"]:
            if key["Status"] != "Active":
                continue
            age = (now - key["CreateDate"]).days
            if age <= max_age_days:
                continue
            findings.append(
                Finding(
                    resource=f"{user['UserName']}/{key['AccessKeyId']}",
                    status=Status.CRITICAL if age > 2 * max_age_days else Status.WARN,
                    message=f"active key is {age} days old (limit {max_age_days})",
                    details={"age_days": age},
                )
            )
    return findings
