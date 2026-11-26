"""Runtime context handed to every check: config plus cached cloud clients."""

from __future__ import annotations

import threading
from functools import cached_property
from typing import Any

import boto3

from opskit.core.config import Config


class Context:
    def __init__(self, config: Config):
        self.config = config
        self._clients: dict[tuple[str, str | None], Any] = {}
        self._lock = threading.Lock()

    @property
    def regions(self) -> list[str]:
        return self.config.aws.regions

    @cached_property
    def aws_session(self) -> boto3.Session:
        base = boto3.Session(profile_name=self.config.aws.profile)
        arn = self.config.aws.assume_role_arn
        if not arn:
            return base
        creds = base.client("sts").assume_role(RoleArn=arn, RoleSessionName="opskit")["Credentials"]
        return boto3.Session(
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        )

    def aws(self, service: str, region: str | None = None) -> Any:
        """Thread-safe cached boto3 client."""
        key = (service, region)
        with self._lock:
            if key not in self._clients:
                self._clients[key] = self.aws_session.client(service, region_name=region)
            return self._clients[key]
