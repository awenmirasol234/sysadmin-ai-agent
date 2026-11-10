"""Plugin system for hot-mounting custom sysadmin tools."""

from typing import Callable, Dict, List

_PLUGINS: Dict[str, Callable] = {}


def sysadmin_plugin(name: str):
    """Decorator to register a custom tool function as an agent plugin."""
    def decorator(fn: Callable):
        _PLUGINS[name] = fn
        return fn
    return decorator


def get_registered_plugins() -> Dict[str, Callable]:
    """Returns all dynamically registered plugins."""
    return dict(_PLUGINS)
