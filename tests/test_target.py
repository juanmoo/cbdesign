from fractions import Fraction
from io import BytesIO
import json

import pytest
from PIL import Image

from cbdesign.patterns import checkerboard, mouse_head
from cbdesign.target import FrozenTarget, TargetDecodeError, decode_png, target_occupancy


def png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_frozen_target_is_rectangular_binary_and_json_serializable():
    target = FrozenTarget(((0, 1), (1, 0)), {"name": "test", "tags": ["a", 2]})
    assert target.rows == ((0, 1), (1, 0))
    assert json.loads(json.dumps(target.as_dict())) == {
        "rows": [[0, 1], [1, 0]], "metadata": {"name": "test", "tags": ["a", 2]}}
    with pytest.raises(ValueError, match="rectangular"):
        FrozenTarget(((0,), (1, 0)))
    with pytest.raises(ValueError, match="0 or 1"):
        FrozenTarget(((True,),))


def test_png_decode_is_deterministic_for_alpha_crop_threshold_and_mapping():
    image = Image.new("RGBA", (3, 1), (255, 255, 255, 255))
    image.putpixel((0, 0), (0, 0, 0, 255))
    image.putpixel((1, 0), (0, 0, 0, 0))  # alpha is composited over white
    image.putpixel((2, 0), (127, 127, 127, 255))
    assert decode_png(png(image), threshold=128).rows == ((1, 0, 1),)
    assert decode_png(png(image), crop=(1, 0, 3, 1), threshold=128, one_for_dark=False).rows == ((1, 0),)


def test_png_decode_rejects_bad_format_and_all_declared_limits():
    valid = png(Image.new("RGB", (2, 2), "black"))
    with pytest.raises(TargetDecodeError, match="byte"):
        decode_png(valid, max_bytes=1)
    with pytest.raises(TargetDecodeError, match="pixel"):
        decode_png(valid, max_pixels=3)
    jpeg = BytesIO(); Image.new("RGB", (1, 1)).save(jpeg, format="JPEG")
    with pytest.raises(TargetDecodeError, match="format"):
        decode_png(jpeg.getvalue())
    animated = BytesIO()
    first, second = Image.new("RGB", (2, 1), "black"), Image.new("RGB", (2, 1), "white")
    first.save(animated, format="GIF", save_all=True, append_images=[second], duration=100, loop=0)
    with pytest.raises(TargetDecodeError, match="frame"):
        decode_png(animated.getvalue(), formats=("GIF",), max_frames=1)
    with pytest.raises(TargetDecodeError, match="invalid image"):
        decode_png(b"not an image")


def test_occupancy_exactly_measures_source_overlap_without_trim():
    target = FrozenTarget(((1, 0), (0, 0)))
    assert target_occupancy(target, 1, 1) == ((Fraction(1, 4),),)
    assert target_occupancy(target, 1, 3) == ((Fraction(1, 2), Fraction(1, 4), Fraction(0)),)
    assert target_occupancy(target, row_bounds=(0, 1, 3), column_bounds=(0, 1, 2),
                            finished_width=2, finished_height=3) == (
                                (Fraction(1), Fraction(0)), (Fraction(1, 4), Fraction(0)))


def test_patterns_produce_immutable_binary_matrices_and_mouse_is_silhouette():
    board = checkerboard(2, 3)
    assert board.rows == ((0, 1, 0), (1, 0, 1))
    mouse = mouse_head()
    assert all(cell in (0, 1) for row in mouse.rows for cell in row)
    assert mouse.rows[mouse.height // 2][mouse.width // 2] == 1
    assert sum(map(sum, mouse.rows)) > 10
