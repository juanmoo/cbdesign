"""Exact clipping preserves orientation, including equal-sized source axes."""
from hypothesis import given, strategies as st

from cbdesign.geometry import Box, PROPER_ROTATIONS
from cbdesign.replay import Region, clip_regions, transformed_region


@given(st.sampled_from(PROPER_ROTATIONS), st.integers(4, 100), st.integers(0, 2))
def test_rotated_cube_cut_clips_source_partition(rotation, length, axis):
    root = Box((0, 0, 0), (length, length, length))
    region = Region('root', 'maple', root, root, (0, 1, 0))
    rotated = transformed_region(region, rotation, root.size)
    # Repeated dimensions must not hide nonidentity source-axis permutations.
    left, kerf, right = root.cut(axis, 1, 1)
    clips = [clip_regions((rotated,), box, box.origin)[0] for box in (left, kerf, right)]
    assert sum(piece.source.volume for piece in clips) == root.volume
    assert all(root.intersect(piece.source) == piece.source for piece in clips)
    assert all(clips[i].source.intersect(clips[j].source) is None
               for i in range(3) for j in range(i + 1, 3))
    for piece in clips:
        restored = transformed_region(piece, rotation.inverse(), piece.current.size)
        assert restored.axis_map == (0, 1, 2)
        assert restored.axis_sign == (1, 1, 1)
        assert restored.grain == (0, 1, 0)
        assert restored.source == piece.source
