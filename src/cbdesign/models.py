"""Strict, versioned plan schema. All lengths are integer micrometres."""
from __future__ import annotations
from typing import Annotated, Literal, Union
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator
from .dimensions import Micrometres


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Stock(StrictModel):
    id: str = Field(min_length=1)
    species: str = Field(min_length=1)
    size: list[Micrometres] = Field(min_length=3, max_length=3)
    # Source grain is immutable and always source +Y.


class Cut(StrictModel):
    kind: Literal["cut"]
    id: str
    input: str
    # outputs[0] is the commanded retained child; outputs[1] is residual stock/offcut.
    outputs: list[str] = Field(min_length=2, max_length=2)
    axis: Literal[0, 1, 2]
    retained: Micrometres
    kerf: Micrometres
    tool: str = "saw"
    category: Literal["trim", "other_offcuts"] = "other_offcuts"


class Surface(StrictModel):
    kind: Literal["surface"]
    id: str
    input: str
    output: str
    removed: str
    axis: Literal[0, 1, 2]
    side: Literal["min", "max"]
    amount: Micrometres
    category: Literal["milling", "trim", "other_offcuts"] = "milling"
    process: str


class Rotate(StrictModel):
    kind: Literal["rotate"]
    id: str
    input: str
    output: str
    perm: list[Literal[0, 1, 2]] = Field(min_length=3, max_length=3)
    sign: list[Literal[-1, 1]] = Field(min_length=3, max_length=3)


class Glue(StrictModel):
    kind: Literal["glue"]
    id: str
    inputs: list[str] = Field(min_length=2)
    output: str
    axis: Literal[0, 1, 2]
    stage: Literal["first", "final"]
    prepared_faces: bool
    negligible_glue_line: Literal[True]


Operation = Annotated[Union[Cut, Surface, Rotate, Glue], Field(discriminator="kind")]
OPERATION_ADAPTER = TypeAdapter(list[Operation])


class Finishing(StrictModel):
    terminal: str
    method: Literal["drum_sander", "wide_belt_sander", "router_sled", "cnc_surfacer"]
    end_grain_supported: Literal[True]


class Disposition(StrictModel):
    part: str
    # Surface removals retain their operation-derived category; ordinary retained
    # terminals are other_offcuts. Kerf is accepted only to produce a precise replay
    # diagnostic: cuts create kerf directly and never create a terminal part.
    category: Literal["kerf", "milling", "trim", "other_offcuts"]
    reusable: bool = False


class ShopProfile(StrictModel):
    manufacturing_increment: Micrometres
    saw_kerf: Micrometres | None = None
    max_workpiece: list[Micrometres] | None = Field(default=None, min_length=3, max_length=3)
    max_slice_length: Micrometres | None = None


class Recipe(StrictModel):
    id: str
    sequence: list[str] = Field(min_length=1)


class RowAssignment(StrictModel):
    rotated_part: str
    recipe: str
    reversed: bool = False


class Template(StrictModel):
    """Optional declaration checked against replay; it does not supply geometry."""
    recipes: list[Recipe] = Field(default_factory=list)
    rows: list[RowAssignment] = Field(default_factory=list)


class Plan(StrictModel):
    schema_version: Literal["cbdesign-plan/v1"]
    title: str = Field(min_length=1)
    assumptions: list[str] = Field(min_length=1)
    shop: ShopProfile
    stock: list[Stock] = Field(min_length=1)
    operations: list[Operation] = Field(min_length=1)
    finishing: Finishing
    dispositions: list[Disposition]
    expected_final_size: list[Micrometres] = Field(min_length=3, max_length=3)
    template: Template = Field(default_factory=Template)

    @model_validator(mode="after")
    def unique_roots(self):
        ids = [s.id for s in self.stock]
        if len(ids) != len(set(ids)):
            raise ValueError("stock IDs must be globally unique")
        return self

    @classmethod
    def from_json_obj(cls, obj: object) -> "Plan":
        # Pydantic's discriminated unions remain strict through model validation.
        return cls.model_validate(obj)


def load_plan(obj: object) -> "Plan | object":
    """Load a plan by its explicit schema version without implicit migration."""
    if not isinstance(obj, dict):
        raise ValueError("plan must be a JSON object")
    version = obj.get("schema_version")
    if version == "cbdesign-plan/v1":
        return Plan.from_json_obj(obj)
    if version == "cbdesign-plan/v2":
        # Local import avoids a module cycle: V2 intentionally reuses V1 primitives.
        from .models_v2 import PlanV2
        return PlanV2.from_json_obj(obj)
    raise ValueError(f"unsupported schema_version: {version!r}")
