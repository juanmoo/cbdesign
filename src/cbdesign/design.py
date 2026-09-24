"""Strict high-level input schema for the N2 compiler, separate from PlanV2."""
from __future__ import annotations
from typing import Literal, Mapping, Sequence
from pydantic import Field, field_validator, model_validator
from .models import StrictModel


class DesignError(ValueError):
    def __init__(self, code: str, message: str): self.code = code; super().__init__(message)


class StockType(StrictModel):
    id: str = Field(min_length=1)
    species: str = Field(min_length=1)
    width: int = Field(gt=0, le=10_000_000)
    thickness: int = Field(gt=0, le=10_000_000)
    available_lengths: list[int] = Field(min_length=1)
    @field_validator("available_lengths")
    @classmethod
    def positive_lengths(cls, values):
        if any(isinstance(v, bool) or v <= 0 for v in values): raise ValueError("available lengths must be positive integers")
        return values


class ShopProfile(StrictModel):
    increment: int = Field(default=1000, gt=0)
    kerf: int = Field(default=3000, gt=0)
    x_allowance: int = Field(default=1000, gt=0)
    y_allowance: int = Field(default=8000, gt=0)
    z_allowance: int = Field(default=3000, gt=0)
    panel_face_removal: int = Field(default=1000, gt=0)
    final_face_removal: int = Field(default=1000, gt=0)
    final_x_trim: int = Field(default=10000, gt=0)
    final_y_trim: int = Field(default=10000, gt=0)
    slice_reserve: int = Field(default=160000, gt=0)
    min_rip_width: int = Field(default=25000, gt=0)
    max_workpiece: list[int] = Field(default_factory=lambda: [1_000_000]*3, min_length=3, max_length=3)


class FinalDimensions(StrictModel):
    x: int = Field(gt=0, le=10_000_000); y: int = Field(gt=0, le=10_000_000); z: int = Field(gt=0, le=10_000_000)


class DesignRequest(StrictModel):
    """Design intent. Matrix symbols map to species; no PlanV2 IDs are exposed."""
    schema_version: Literal["cbdesign-design/v1"] = "cbdesign-design/v1"
    matrix: list[list[str]] = Field(min_length=2, max_length=32)
    species: Mapping[str, str]
    final: FinalDimensions
    stock_types: list[StockType] = Field(min_length=1)
    shop: ShopProfile = Field(default_factory=ShopProfile)
    title: str = Field(default="Compiled end-grain board", min_length=1)

    @model_validator(mode="after")
    def exact_design_contract(self):
        if not self.matrix[0] or len(self.matrix[0]) > 32 or any(len(row) != len(self.matrix[0]) for row in self.matrix):
            raise ValueError("matrix must be rectangular with 2..32 rows and 1..32 columns")
        symbols = {cell for row in self.matrix for cell in row}
        if not all(isinstance(cell, str) and cell.isascii() and cell.isalnum() and len(cell) <= 16 for cell in symbols):
            raise ValueError("matrix symbols must be nonempty ASCII alphanumeric identifiers up to 16 characters")
        if not symbols <= set(self.species): raise ValueError("species mapping must name every matrix symbol")
        if len(self.species) != 2 or len(set(self.species.values())) != 2: raise ValueError("exactly two distinct mapped species must be configured; either may be unused")
        if not all(isinstance(species, str) and species for species in self.species.values()): raise ValueError("mapped species must be nonempty strings")
        if len(self.stock_types) != 2 or len({s.id for s in self.stock_types}) != 2: raise ValueError("exactly two uniquely identified stock types must be supplied")
        available = {s.species for s in self.stock_types}
        if len(available) != 2: raise ValueError("the two stock types must have distinct species")
        if set(self.species.values()) != available: raise ValueError("mapped species must exactly equal supplied stock species")
        inc = self.shop.increment
        vals = [self.final.x,self.final.y,self.final.z,*self.shop.model_dump(exclude={"max_workpiece"}).values(), *self.shop.max_workpiece, *(length for stock in self.stock_types for length in stock.available_lengths), *(dimension for stock in self.stock_types for dimension in (stock.width, stock.thickness))]
        if any(not isinstance(v, int) or v % inc for v in vals): raise ValueError("all dimensional inputs, capacities, and stock lengths must be shop-increment integers")
        return self


def illustrative_request(matrix: Sequence[Sequence[str]] | None = None) -> DesignRequest:
    default = [list("AAAABBAAAABB"), list("BBAAAABBAAAA")] * 6
    bitmap = [list(row) for row in (matrix if matrix is not None else default)]
    symbols = {cell for row in bitmap for cell in row}
    if not symbols <= {"A", "B"}:
        raise DesignError("illustrative_symbols", "illustrative_request accepts only A/B symbols; construct DesignRequest for other mappings")
    # Map an all-A or all-B illustration without falsely requiring both symbols in its mapping.
    mapping = {"A":"maple", "B":"walnut"}
    return DesignRequest(matrix=bitmap, species=mapping,
      final={"x":290000,"y":290000,"z":30000}, stock_types=[
       {"id":"maple","species":"maple","width":108000,"thickness":33000,"available_lengths":[419000]*144},
       {"id":"walnut","species":"walnut","width":83000,"thickness":37000,"available_lengths":[419000]*144}])
