"""Exact half-open boxes and proper signed rotations."""
from __future__ import annotations
from dataclasses import dataclass
from itertools import permutations, product


@dataclass(frozen=True)
class Box:
    origin: tuple[int, int, int]
    size: tuple[int, int, int]

    def __post_init__(self):
        if any(isinstance(v, bool) or not isinstance(v, int) for v in self.origin + self.size):
            raise ValueError("box coordinates must be integers")
        if any(v <= 0 for v in self.size):
            raise ValueError("box sizes must be positive")

    @property
    def volume(self) -> int:
        return self.size[0] * self.size[1] * self.size[2]

    def intersect(self, other: "Box") -> "Box | None":
        lo = tuple(max(self.origin[i], other.origin[i]) for i in range(3))
        hi = tuple(min(self.origin[i] + self.size[i], other.origin[i] + other.size[i]) for i in range(3))
        if any(hi[i] <= lo[i] for i in range(3)):
            return None
        return Box(lo, tuple(hi[i] - lo[i] for i in range(3)))

    def cut(self, axis: int, retained: int, kerf: int) -> tuple["Box", "Box", "Box"]:
        if axis not in (0, 1, 2) or retained <= 0 or kerf <= 0 or retained + kerf >= self.size[axis]:
            raise ValueError("cut does not create two positive children and a positive kerf")
        sizes_a = list(self.size); sizes_a[axis] = retained
        sizes_k = list(self.size); sizes_k[axis] = kerf
        sizes_b = list(self.size); sizes_b[axis] = self.size[axis] - retained - kerf
        kerf_origin = list(self.origin); kerf_origin[axis] += retained
        b_origin = list(kerf_origin); b_origin[axis] += kerf
        return Box(self.origin, tuple(sizes_a)), Box(tuple(kerf_origin), tuple(sizes_k)), Box(tuple(b_origin), tuple(sizes_b))

    def remove_face(self, axis: int, side: str, amount: int) -> tuple["Box", "Box"]:
        if axis not in (0, 1, 2) or side not in ("min", "max") or amount <= 0 or amount >= self.size[axis]:
            raise ValueError("invalid face removal")
        kept_size = list(self.size); kept_size[axis] -= amount
        if side == "min":
            removed_size = list(self.size); removed_size[axis] = amount
            kept_origin = list(self.origin); kept_origin[axis] += amount
            return Box(tuple(kept_origin), tuple(kept_size)), Box(self.origin, tuple(removed_size))
        removed_size = list(self.size); removed_size[axis] = amount
        removed_origin = list(self.origin); removed_origin[axis] += self.size[axis] - amount
        return Box(self.origin, tuple(kept_size)), Box(tuple(removed_origin), tuple(removed_size))


@dataclass(frozen=True)
class Rotation:
    """Signed permutation: output axis i receives sign[i] * input axis perm[i]."""
    perm: tuple[int, int, int]
    sign: tuple[int, int, int]

    def __post_init__(self):
        if sorted(self.perm) != [0, 1, 2] or any(v not in (-1, 1) for v in self.sign):
            raise ValueError("rotation must be a signed axis permutation")
        if self.determinant != 1:
            raise ValueError("reflection is not a proper rotation")

    @property
    def determinant(self) -> int:
        inversions = sum(self.perm[i] > self.perm[j] for i in range(3) for j in range(i + 1, 3))
        return (-1 if inversions % 2 else 1) * self.sign[0] * self.sign[1] * self.sign[2]

    def apply_vector(self, vector: tuple[int, int, int]) -> tuple[int, int, int]:
        return tuple(self.sign[i] * vector[self.perm[i]] for i in range(3))

    def output_size(self, size: tuple[int, int, int]) -> tuple[int, int, int]:
        return tuple(size[self.perm[i]] for i in range(3))

    def inverse(self) -> "Rotation":
        p = [0, 0, 0]; s = [0, 0, 0]
        for out_axis, in_axis in enumerate(self.perm):
            p[in_axis] = out_axis; s[in_axis] = self.sign[out_axis]
        return Rotation(tuple(p), tuple(s))


PROPER_ROTATIONS = tuple(Rotation(tuple(p), tuple(s)) for p in permutations(range(3)) for s in product((-1, 1), repeat=3) if Rotation.__new__(Rotation) and ((-1 if sum(p[i] > p[j] for i in range(3) for j in range(i+1,3)) % 2 else 1) * s[0]*s[1]*s[2] == 1))
