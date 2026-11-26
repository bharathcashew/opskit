# opskit

A pluggable IT ops toolkit. Write a check once as a small Python function, then run it from the command line, from cron or CI, or as a REST service with Prometheus metrics.

v0.1 ships with read-only AWS checks for health, security and cost. The framework is designed so anyone can add their own checks as a separate pip package without touching this repo.

```
$ opskit run --region us-east-1
                    opskit run 3f9a1c2b7e10
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━┓
┃ Check                        ┃ Status   ┃ Findings ┃   Time ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━┩
│ aws.cloudwatch.alarms_firing │ critical │        1 │ 212 ms │
│ aws.ec2.open_security_groups │ critical │        2 │ 340 ms │
│ aws.ec2.status_checks        │ ok       │        0 │ 188 ms │
│ aws.ec2.unattached_volumes   │ warn     │        3 │ 151 ms │
│ aws.elbv2.target_health      │ ok       │        0 │ 410 ms │
│ aws.iam.access_key_age       │ warn     │        1 │ 290 ms │
└──────────────────────────────┴──────────┴──────────┴────────┘
```

## Why

Most teams end up with a folder of one-off scripts that check the same things: is anything unhealthy behind the load balancer, is port 22 open to the world, are we paying for volumes nobody uses. opskit gives those scripts a common shape: one result model, one config file, one runner, and two front doors (CLI and API).

## Install

```bash
pip install git+https://github.com/bharathcashew/opskit.git
# or for development
git clone https://github.com/bharathcashew/opskit.git && cd opskit
pip install -e ".[dev]"
```

Requires Python 3.10+. AWS credentials are picked up the usual boto3 way (env vars, `~/.aws`, instance role). The built-in checks only need read access; see [docs/iam-policy.json](docs/iam-policy.json).

## Quick start

```bash
opskit init                       # writes a sample opskit.yaml
opskit list                       # see every check, its tags and tunable params
opskit run                        # run all enabled checks
opskit run --tag security         # only security checks
opskit run aws.ec2.status_checks  # one check
opskit run -r us-east-1 -r eu-west-1 --profile prod
opskit run -f json -o report.json
opskit run -f markdown            # paste-ready for a ticket or Slack
```

Exit codes are `0` ok, `1` warnings, `2` critical or check errors, so `opskit run` drops straight into cron, CI gates or a Nagios-style wrapper.

## Built-in checks

| ID | What it flags | Tags |
|---|---|---|
| `aws.ec2.status_checks` | Running instances with impaired system/instance checks | health |
| `aws.elbv2.target_health` | Target groups with unhealthy targets or low healthy capacity | health |
| `aws.cloudwatch.alarms_firing` | Metric alarms in ALARM (optionally INSUFFICIENT_DATA) | health |
| `aws.ec2.open_security_groups` | 0.0.0.0/0 or ::/0 on SSH, RDP, DB ports or all ports | security |
| `aws.iam.access_key_age` | Active access keys older than N days | security |
| `aws.ec2.unattached_volumes` | EBS volumes in `available` state | cost |
| `aws.ec2.unassociated_eips` | Elastic IPs not attached to anything | cost |

## Run it as a service

```bash
export OPSKIT_API_TOKEN=$(openssl rand -hex 24)
opskit serve --host 0.0.0.0 --port 8080
```

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness probe, no auth |
| GET | `/v1/checks?tag=security` | List checks |
| POST | `/v1/runs` | Run checks, returns the full report |
| GET | `/v1/runs` | Recent run summaries |
| GET | `/v1/runs/{run_id}` | One full report |
| GET | `/metrics` | Prometheus gauges for the latest run |
| GET | `/docs` | Interactive OpenAPI docs |

```bash
curl -s -X POST localhost:8080/v1/runs \
  -H "Authorization: Bearer $OPSKIT_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tags": ["security"], "regions": ["us-east-1"]}'
```

Docker:

```bash
docker build -t opskit .
docker run -p 8080:8080 -e OPSKIT_API_TOKEN=... -e AWS_REGION=us-east-1 \
  -v ~/.aws:/home/opskit/.aws:ro opskit
```

On ECS or EKS, give the task an IAM role with the read-only policy instead of mounting credentials.

## Configuration

`opskit.yaml` is optional. Lookup order: `--config`, `$OPSKIT_CONFIG`, `./opskit.yaml`, `~/.config/opskit/config.yaml`.

```yaml
aws:
  regions: [us-east-1, us-west-2]
  assume_role_arn: arn:aws:iam::123456789012:role/opskit-readonly   # optional
checks:
  aws.iam.access_key_age:
    max_age_days: 60
  aws.ec2.unassociated_eips:
    enabled: false
plugins: [my_local_checks]   # extra modules to import
```

Environment overrides: `OPSKIT_AWS_PROFILE`, `OPSKIT_AWS_REGIONS` (comma separated), `OPSKIT_API_TOKEN`.

## Writing your own check

A check is a function that takes a context and returns findings. No findings means OK.

```python
from opskit import check, Finding, Status

@check("acme.ec2.missing_owner_tag", title="Instances without an Owner tag", tags=["aws", "governance"])
def missing_owner_tag(ctx, tag_key: str = "Owner"):
    findings = []
    for region in ctx.regions:
        for res in ctx.aws("ec2", region).describe_instances()["Reservations"]:
            for inst in res["Instances"]:
                keys = {t["Key"] for t in inst.get("Tags", [])}
                if tag_key not in keys:
                    findings.append(Finding(resource=inst["InstanceId"], region=region,
                                            status=Status.WARN, message=f"no {tag_key} tag"))
    return findings
```

Keyword arguments after `ctx` become tunable params that show up in `opskit list` and can be set in `opskit.yaml`.

To share checks, publish them as their own package and register an entry point. [examples/custom_plugin](examples/custom_plugin) is a complete, installable example:

```toml
[project.entry-points."opskit.checks"]
acme = "acme_checks"
```

After `pip install acme-opskit-checks`, the checks appear in `opskit list` and in the API automatically.

## Project layout

```
src/opskit/
  core/        models, registry, config, context, runner (no AWS-specific code)
  checks/aws/  built-in AWS checks
  api/         FastAPI service
  cli.py       Typer CLI
  reporters.py table / json / markdown output
examples/      installable plugin example
tests/         moto-backed tests, no real AWS needed
```

## Roadmap

- Linux host checks over SSH (disk, memory, failed systemd units)
- Web endpoint checks (HTTP status, TLS expiry, DNS)
- Notifiers: Slack, PagerDuty, email
- Scheduled runs inside the service and persistent run history (SQLite/Postgres)
- Optional remediation actions with dry-run by default

Contributions welcome, see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
