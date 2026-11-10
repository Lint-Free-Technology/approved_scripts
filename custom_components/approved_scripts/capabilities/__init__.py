"""Shared capability types and the self-registering action library."""

from .base import ActionCapability
from .library import load_capabilities

__all__ = [
    "ActionCapability",
    "load_capabilities",
]
