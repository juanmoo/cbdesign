"""Integer micrometre dimensions and representability checks."""
from __future__ import annotations

from pydantic_core import core_schema


class Micrometres(int):
    """A strictly positive integer dimensional value in micrometres."""

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        def validate(value):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("must be an integer number of micrometres")
            if value <= 0:
                raise ValueError("must be positive")
            return cls(value)
        return core_schema.no_info_plain_validator_function(validate)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        return {"type": "integer", "exclusiveMinimum": 0, "description": "positive micrometres"}


def require_increment(value: int, increment: int, label: str) -> None:
    if increment <= 0:
        raise ValueError("manufacturing increment must be positive")
    if value % increment:
        raise ValueError(f"{label}={value} um is not representable on increment {increment} um")


def um(value: int) -> str:
    return f"{value / 1000:g} mm"
