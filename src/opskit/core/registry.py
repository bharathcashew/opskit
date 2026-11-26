"""Check registry and plugin discovery.

A check is a plain function decorated with @check. It receives a Context and any
params from config, and returns a list of Findings. No findings means OK.

    from opskit import check, Finding, Status

    @check("acme.disk.free", title="Disk free space", tags=["linux", "capacity"])
    def disk_free(ctx, min_free_pct: int = 15):
        ...
        return [Finding(resource="/", message="Only 9% free", status=Status.WARN)]

Built-in checks live in opskit.checks. Third-party packages register theirs through
the "opskit.checks" entry point group, so `pip install acme-opskit-checks` is enough.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from typing import Any

log = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "opskit.checks"


@dataclass(frozen=True)
class CheckSpec:
    id: str
    title: str
    func: Callable[..., Any]
    description: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def params(self) -> dict[str, Any]:
        """Tunable params and their defaults, read from the function signature."""
        sig = inspect.signature(self.func)
        out = {}
        for name, p in list(sig.parameters.items())[1:]:  # skip ctx
            out[name] = None if p.default is inspect.Parameter.empty else p.default
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "tags": list(self.tags),
            "params": self.params,
        }


_REGISTRY: dict[str, CheckSpec] = {}
_loaded = False


def check(
    id: str,
    *,
    title: str,
    tags: list[str] | tuple[str, ...] = (),
    description: str = "",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if id in _REGISTRY and _REGISTRY[id].func is not func:
            log.warning("check %s registered twice; last one wins", id)
        desc = description or (inspect.getdoc(func) or "").split("\n\n")[0]
        _REGISTRY[id] = CheckSpec(id=id, title=title, func=func, description=desc, tags=tuple(tags))
        return func

    return decorator


def _import_package_tree(package_name: str) -> None:
    pkg = importlib.import_module(package_name)
    for mod in pkgutil.walk_packages(pkg.__path__, prefix=f"{package_name}."):
        importlib.import_module(mod.name)


def load_plugins(extra_modules: list[str] | None = None) -> None:
    """Import built-in checks, entry-point plugins, and any modules named in config."""
    global _loaded
    if not _loaded:
        _import_package_tree("opskit.checks")
        for ep in entry_points(group=ENTRY_POINT_GROUP):
            try:
                mod = ep.load()
                if inspect.ismodule(mod) and hasattr(mod, "__path__"):
                    _import_package_tree(mod.__name__)
            except Exception as exc:  # a broken plugin must not take down the tool
                log.error("failed to load plugin %s: %s", ep.name, exc)
        _loaded = True
    for name in extra_modules or []:
        try:
            importlib.import_module(name)
        except Exception as exc:
            log.error("failed to import plugin module %s: %s", name, exc)


def list_checks(tags: list[str] | None = None) -> list[CheckSpec]:
    specs = sorted(_REGISTRY.values(), key=lambda s: s.id)
    if tags:
        wanted = set(tags)
        specs = [s for s in specs if wanted & set(s.tags)]
    return specs


def get_check(check_id: str) -> CheckSpec:
    try:
        return _REGISTRY[check_id]
    except KeyError:
        raise KeyError(f"unknown check: {check_id}") from None
