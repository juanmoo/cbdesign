"""Strict rough-stock schema for ``cbdesign-plan/v2``.

V2 deliberately keeps the replay operation vocabulary but makes stock provenance,
machine constraints, and construction declarations explicit.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import Field, TypeAdapter, model_validator
from pydantic_core import core_schema

from .dimensions import Micrometres, require_increment
from .models import (
    Cut,
    Disposition,
    Finishing,
    Glue,
    Rotate,
    Stock,
    StrictModel,
    Surface,
)


class NonnegativeMicrometres(int):
    """An integer dimensional amount which may be zero."""

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        def validate(value):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("must be an integer number of micrometres")
            if value < 0:
                raise ValueError("must be nonnegative")
            return cls(value)
        return core_schema.no_info_plain_validator_function(validate)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        return {"type": "integer", "minimum": 0, "description": "nonnegative micrometres"}


Dimensions = list[Micrometres]


class PreparationV2(StrictModel):
    x_min: NonnegativeMicrometres
    x_max: NonnegativeMicrometres
    y_min: NonnegativeMicrometres
    y_max: NonnegativeMicrometres
    z_min: NonnegativeMicrometres
    z_max: NonnegativeMicrometres


class StockTypeV2(StrictModel):
    id: str = Field(min_length=1)
    species: str = Field(min_length=1)
    width: Micrometres
    thickness: Micrometres
    grain: list[Literal[0, 1]] = Field(min_length=3, max_length=3)
    preparation: PreparationV2

    @model_validator(mode="after")
    def source_grain_is_y(self):
        if self.grain != [0, 1, 0]:
            raise ValueError("stock type grain must be [0, 1, 0]")
        return self


class SourceSegmentV2(StrictModel):
    id: str = Field(min_length=1)
    stock_type: str = Field(min_length=1)
    length: Micrometres
    boundary: Literal["allocated_window"]
    separation_operation: str = Field(min_length=1)


class CutProfileV2(StrictModel):
    kerf: Micrometres
    min_input: Dimensions = Field(min_length=3, max_length=3)
    max_input: Dimensions = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def ordered_limits(self):
        if any(int(lo) > int(hi) for lo, hi in zip(self.min_input, self.max_input)):
            raise ValueError("profile min_input must not exceed max_input")
        return self


class CuttingProfileV2(StrictModel):
    separation: CutProfileV2
    preparation: CutProfileV2
    slicing: CutProfileV2
    final_trim: CutProfileV2
    minimum_rip_width: Micrometres
    slice_min: Micrometres
    slice_max: Micrometres
    slicing_reserve: Micrometres
    new_face_jointing: Micrometres

    @model_validator(mode="after")
    def ordered_slice_limits(self):
        if int(self.slice_min) > int(self.slice_max):
            raise ValueError("slice_min must not exceed slice_max")
        return self


class SurfacingProfileV2(StrictModel):
    process: Literal["jointer", "thickness_planer", "drum_sander", "wide_belt_sander", "router_sled", "cnc_surfacer"]
    axes: list[Literal[0, 1, 2]] = Field(min_length=1, max_length=3)
    min_input: Dimensions = Field(min_length=3, max_length=3)
    max_input: Dimensions = Field(min_length=3, max_length=3)
    glue_ready: bool
    end_grain_supported: bool

    @model_validator(mode="after")
    def valid_axes_and_limits(self):
        if len(set(self.axes)) != len(self.axes):
            raise ValueError("surfacing axes must be unique")
        if any(int(lo) > int(hi) for lo, hi in zip(self.min_input, self.max_input)):
            raise ValueError("profile min_input must not exceed max_input")
        return self


class ShopV2(StrictModel):
    max_workpiece: Dimensions = Field(min_length=3, max_length=3)
    manufacturing_increment: Micrometres
    cutting: CuttingProfileV2
    surfacing: list[SurfacingProfileV2] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_processes(self):
        names = [profile.process for profile in self.surfacing]
        if len(names) != len(set(names)):
            raise ValueError("surfacing process names must be unique")
        return self

    # Compatibility accessors intentionally do not invent a legacy profile.
    @property
    def saw_kerf(self) -> None:
        return None

    @property
    def max_slice_length(self) -> None:
        return None


class GridV2(StrictModel):
    pitch: Micrometres
    columns: int = Field(ge=1)
    strip_thickness: Micrometres
    panel_thickness: Micrometres
    slice_length: Micrometres


class CutV2(Cut):
    retained_side: Literal["min", "max"]


V2Operation = Annotated[Union[CutV2, Surface, Rotate, Glue], Field(discriminator="kind")]
V2_OPERATION_ADAPTER = TypeAdapter(list[V2Operation])


class RecipeV2(StrictModel):
    id: str = Field(min_length=1)
    cells: list[str] = Field(min_length=1)


class PanelV2(StrictModel):
    id: str = Field(min_length=1)
    part: str = Field(min_length=1)
    recipe: str = Field(min_length=1)
    strips: list[str] = Field(min_length=1)


class RowV2(StrictModel):
    rotated_part: str = Field(min_length=1)
    panel: str = Field(min_length=1)
    recipe: str = Field(min_length=1)
    reversed: bool = False


class TemplateV2(StrictModel):
    recipes: list[RecipeV2] = Field(min_length=1)
    panels: list[PanelV2] = Field(min_length=1)
    rows: list[RowV2] = Field(min_length=2)

    @model_validator(mode="after")
    def unique_and_referenced(self):
        recipe_ids = [recipe.id for recipe in self.recipes]
        panel_ids = [panel.id for panel in self.panels]
        row_ids = [row.rotated_part for row in self.rows]
        if len(recipe_ids) != len(set(recipe_ids)):
            raise ValueError("template recipe IDs must be unique")
        if len(panel_ids) != len(set(panel_ids)):
            raise ValueError("template panel IDs must be unique")
        if len(row_ids) != len(set(row_ids)):
            raise ValueError("template rotated row parts must be unique")
        recipes = set(recipe_ids)
        panels = set(panel_ids)
        for panel in self.panels:
            if panel.recipe not in recipes:
                raise ValueError(f"panel {panel.id!r} references unknown recipe {panel.recipe!r}")
        for row in self.rows:
            if row.panel not in panels:
                raise ValueError(f"row {row.rotated_part!r} references unknown panel {row.panel!r}")
            if row.recipe not in recipes:
                raise ValueError(f"row {row.rotated_part!r} references unknown recipe {row.recipe!r}")
        return self


class PlanV2(StrictModel):
    schema_version: Literal["cbdesign-plan/v2"]
    title: str = Field(min_length=1)
    assumptions: list[str] = Field(min_length=1)
    shop: ShopV2
    stock_types: list[StockTypeV2] = Field(min_length=2, max_length=2)
    source_segments: list[SourceSegmentV2] = Field(min_length=1)
    grid: GridV2
    template: TemplateV2
    operations: list[V2Operation] = Field(min_length=1)
    finishing: Finishing
    dispositions: list[Disposition]
    expected_final_size: Dimensions = Field(min_length=3, max_length=3)

    @property
    def stock(self) -> list[Stock]:
        """Derived v1-shaped roots for shared replay consumers."""
        types = {stock_type.id: stock_type for stock_type in self.stock_types}
        return [Stock(id=segment.id, species=types[segment.stock_type].species,
                      size=[types[segment.stock_type].width, segment.length,
                            types[segment.stock_type].thickness])
                for segment in self.source_segments]

    @model_validator(mode="after")
    def validate_contract(self):
        types = {stock_type.id: stock_type for stock_type in self.stock_types}
        type_ids = [stock_type.id for stock_type in self.stock_types]
        species = [stock_type.species for stock_type in self.stock_types]
        segment_ids = [segment.id for segment in self.source_segments]
        if len(type_ids) != len(set(type_ids)):
            raise ValueError("stock type IDs must be unique")
        if len(species) != len(set(species)):
            raise ValueError("stock type species must be unique")
        if len(segment_ids) != len(set(segment_ids)):
            raise ValueError("source segment IDs must be unique")
        operation_ids = [operation.id for operation in self.operations]
        if len(operation_ids) != len(set(operation_ids)):
            raise ValueError("operation IDs must be unique")
        cuts = {operation.id: operation for operation in self.operations if isinstance(operation, CutV2)}
        for segment in self.source_segments:
            if segment.stock_type not in types:
                raise ValueError(f"source segment {segment.id!r} references unknown stock type")
            cut = cuts.get(segment.separation_operation)
            if cut is None:
                raise ValueError(f"source segment {segment.id!r} references unknown separation cut")
            if cut.input != segment.id or cut.axis != 1:
                raise ValueError(f"source separation {cut.id!r} must cut source {segment.id!r} along Y")
            if cut.retained_side != "min":
                raise ValueError("source separation must retain the minimum-side allocated window")
            if int(cut.retained) + int(cut.kerf) >= int(segment.length):
                raise ValueError("source separation must leave a positive terminal reserve")

        species_names = set(species)
        for recipe in self.template.recipes:
            if len(recipe.cells) != self.grid.columns:
                raise ValueError(f"recipe {recipe.id!r} cell count must equal grid columns")
            unknown = set(recipe.cells) - species_names
            if unknown:
                raise ValueError(f"recipe {recipe.id!r} contains unknown species: {sorted(unknown)!r}")

        known_parts = set(segment_ids)
        for operation in self.operations:
            inputs = [operation.input] if hasattr(operation, "input") else operation.inputs
            outputs = list(operation.outputs) if isinstance(operation, CutV2) else [operation.output] + ([operation.removed] if isinstance(operation, Surface) else [])
            for item in inputs:
                if item not in known_parts:
                    raise ValueError(f"operation {operation.id!r} has missing or forward input {item!r}")
            if len(inputs) != len(set(inputs)):
                raise ValueError(f"operation {operation.id!r} repeats an input")
            if len(outputs) != len(set(outputs)):
                raise ValueError(f"operation {operation.id!r} repeats an output")
            for item in outputs:
                if item in known_parts:
                    raise ValueError(f"part IDs must be globally unique: {item!r}")
            known_parts.update(outputs)

        increment = int(self.shop.manufacturing_increment)
        values: list[tuple[int, str]] = []
        values.extend((int(value), "shop max workpiece") for value in self.shop.max_workpiece)
        for stock_type in self.stock_types:
            values.extend([(int(stock_type.width), "stock width"), (int(stock_type.thickness), "stock thickness")])
            values.extend((int(value), "stock preparation") for value in stock_type.preparation.__dict__.values())
        for segment in self.source_segments:
            values.append((int(segment.length), "source segment length"))
        values.extend((int(value), "grid dimension") for value in (self.grid.pitch, self.grid.strip_thickness, self.grid.panel_thickness, self.grid.slice_length))
        values.extend((int(value), "expected final size") for value in self.expected_final_size)
        for profile in (self.shop.cutting.separation, self.shop.cutting.preparation, self.shop.cutting.slicing, self.shop.cutting.final_trim):
            values.append((int(profile.kerf), "cutting kerf"))
            values.extend((int(value), "cutting profile") for value in [*profile.min_input, *profile.max_input])
        values.extend((int(value), "cutting constraint") for value in (self.shop.cutting.minimum_rip_width, self.shop.cutting.slice_min, self.shop.cutting.slice_max, self.shop.cutting.slicing_reserve, self.shop.cutting.new_face_jointing))
        for profile in self.shop.surfacing:
            values.extend((int(value), "surfacing profile") for value in [*profile.min_input, *profile.max_input])
        for operation in self.operations:
            if isinstance(operation, CutV2):
                values.extend([(int(operation.retained), f"cut {operation.id} retained"), (int(operation.kerf), f"cut {operation.id} kerf")])
            elif isinstance(operation, Surface):
                values.append((int(operation.amount), f"surface {operation.id} amount"))
        for value, label in values:
            require_increment(value, increment, label)
        return self

    @classmethod
    def from_json_obj(cls, obj: object) -> "PlanV2":
        return cls.model_validate(obj)
