"""opskit: a pluggable IT ops toolkit."""

from opskit.core.models import CheckResult, Finding, RunReport, Status
from opskit.core.registry import check, get_check, list_checks

__version__ = "0.1.0"

__all__ = [
    "CheckResult",
    "Finding",
    "RunReport",
    "Status",
    "__version__",
    "check",
    "get_check",
    "list_checks",
]
