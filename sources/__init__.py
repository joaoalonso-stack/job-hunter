"""Coletores plugáveis. Cada módulo expõe `coletar(...) -> list[Job]`."""
from . import gupy, linkedin_guest, portais, publico  # noqa: F401
from .base import Job  # noqa: F401
