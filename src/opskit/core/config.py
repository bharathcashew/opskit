"""Configuration: YAML file plus environment overrides.

Lookup order for the file: --config flag, $OPSKIT_CONFIG, ./opskit.yaml, ~/.config/opskit/config.yaml.
Every setting has a sane default, so a config file is optional.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class AWSConfig(BaseModel):
    profile: str | None = None
    regions: list[str] = Field(default_factory=lambda: ["us-east-1"])
    # Optional role to assume, e.g. for running read-only checks across accounts.
    assume_role_arn: str | None = None


class CheckConfig(BaseModel):
    enabled: bool = True
    params: dict[str, Any] = Field(default_factory=dict)


class APIConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8080
    # Never put the token in the file you commit. Set OPSKIT_API_TOKEN instead.
    token: str | None = None
    history_size: int = 100


class Config(BaseModel):
    aws: AWSConfig = Field(default_factory=AWSConfig)
    checks: dict[str, CheckConfig] = Field(default_factory=dict)
    plugins: list[str] = Field(default_factory=list)  # extra modules to import
    max_workers: int = 8
    api: APIConfig = Field(default_factory=APIConfig)

    def check_config(self, check_id: str) -> CheckConfig:
        return self.checks.get(check_id, CheckConfig())


DEFAULT_PATHS = [Path("opskit.yaml"), Path.home() / ".config" / "opskit" / "config.yaml"]


def load_config(path: str | Path | None = None) -> Config:
    candidates: list[Path] = []
    if path:
        candidates.append(Path(path))
    elif os.environ.get("OPSKIT_CONFIG"):
        candidates.append(Path(os.environ["OPSKIT_CONFIG"]))
    else:
        candidates.extend(DEFAULT_PATHS)

    data: dict[str, Any] = {}
    for p in candidates:
        if p.is_file():
            data = yaml.safe_load(p.read_text()) or {}
            break
        if path:  # explicitly requested file must exist
            raise FileNotFoundError(f"config file not found: {p}")

    # Shorthand: allow `checks: {id: {max_age_days: 30}}` as well as the explicit form.
    for cid, raw in list((data.get("checks") or {}).items()):
        if isinstance(raw, dict) and "params" not in raw:
            enabled = raw.pop("enabled", True)
            data["checks"][cid] = {"enabled": enabled, "params": raw}

    cfg = Config.model_validate(data)

    # Environment overrides
    if os.environ.get("OPSKIT_AWS_PROFILE"):
        cfg.aws.profile = os.environ["OPSKIT_AWS_PROFILE"]
    if os.environ.get("OPSKIT_AWS_REGIONS"):
        cfg.aws.regions = [r.strip() for r in os.environ["OPSKIT_AWS_REGIONS"].split(",") if r.strip()]
    if os.environ.get("OPSKIT_API_TOKEN"):
        cfg.api.token = os.environ["OPSKIT_API_TOKEN"]
    return cfg


SAMPLE_CONFIG = """\
# opskit configuration. Every key is optional.
aws:
  profile: null            # or a named profile from ~/.aws/config
  regions: [us-east-1, us-west-2]
  assume_role_arn: null    # e.g. arn:aws:iam::123456789012:role/opskit-readonly

max_workers: 8

# Extra Python modules that define @check functions (besides installed plugins).
plugins: []

# Per-check settings. Use `opskit list` to see ids and tunable params.
checks:
  aws.iam.access_key_age:
    max_age_days: 90
  aws.ec2.open_security_groups:
    sensitive_ports: [22, 3389, 3306, 5432, 6379, 9200, 27017]
  aws.ec2.unattached_volumes:
    enabled: true

api:
  host: 127.0.0.1
  port: 8080
  history_size: 100
  # token: set OPSKIT_API_TOKEN in the environment instead of here
"""
