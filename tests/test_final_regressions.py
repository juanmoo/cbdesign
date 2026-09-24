from fractions import Fraction
from types import SimpleNamespace

from cbdesign.geometry import Box
from cbdesign.replay import Region, Part
from cbdesign.search import _replay_score
from cbdesign.target import FrozenTarget
from cbdesign.visualization import difference_svg


def test_partial_cell_mismatch_has_independent_area_oracle():
    # Finished rectangle 10x8; B occupies x=[0,3). Target B occupies [0,5).
    # Mismatch is the 2x8 gap, not an untrimmed grid-cell comparison.
    a = Box((3, 0, 0), (7, 8, 2))
    b = Box((0, 0, 0), (3, 8, 2))
    regions = (Region('b', 'walnut', b, b, (0, 0, 1)),
               Region('a', 'maple', a, a, (0, 0, 1)))
    terminal = SimpleNamespace(size=(10, 8, 2), regions=regions)
    replay = SimpleNamespace(parts={'finished': terminal}, terminal='finished')
    target = FrozenTarget(((1, 0),))
    score, mismatch, area = _replay_score(SimpleNamespace(replay=replay), target, 'walnut')
    assert (score, mismatch, area) == (Fraction(1, 5), Fraction(16), Fraction(80))
    svg = difference_svg(replay, target, {'A': 'maple', 'B': 'walnut'})
    assert 'fill="#78548b"' in svg  # explicit agreement, not renderer-dependent alpha
