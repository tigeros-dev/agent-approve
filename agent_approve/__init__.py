"""agent-approve: a yes counts only for exactly what the human saw."""
from __future__ import annotations

from .approve import Decision, approve, verify_before_effect
from .request import create

__version__ = "0.1.0"

__all__ = ["Decision", "approve", "create", "verify_before_effect", "__version__"]
