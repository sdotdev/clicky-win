"""Tests for Neon Scan box sourcing (demo generation + tag parsing)."""

from clicky.effects.scan_layout import ScanBox, demo_boxes, parse_scan_boxes


def test_demo_boxes_count_and_bounds():
    boxes = demo_boxes(1920, 1080, count=10, seed=7)
    assert len(boxes) == 10
    for b in boxes:
        assert 0 <= b.x1 < b.x2 <= 1920
        assert 0 <= b.y1 < b.y2 <= 1080
        assert b.label


def test_demo_boxes_are_sorted_top_to_bottom():
    boxes = demo_boxes(1600, 900, count=8, seed=3)
    ys = [b.y1 for b in boxes]
    assert ys == sorted(ys)
    assert [b.color_index for b in boxes] == list(range(len(boxes)))


def test_demo_boxes_deterministic_with_seed():
    a = demo_boxes(1280, 720, count=6, seed=99)
    b = demo_boxes(1280, 720, count=6, seed=99)
    assert a == b


def test_parse_scan_boxes_rescales_to_screen():
    # Image is half the screen size → coords should double.
    boxes = parse_scan_boxes(
        "[BOX:100,50:200,100:nav_bar]",
        image_width=960, image_height=540,
        screen_width=1920, screen_height=1080,
    )
    assert len(boxes) == 1
    b = boxes[0]
    assert (b.x1, b.y1, b.x2, b.y2) == (200, 100, 400, 200)
    assert b.label == "nav_bar"


def test_parse_scan_boxes_applies_origin_offset():
    boxes = parse_scan_boxes(
        "[BOX:0,0:100,100:x]",
        image_width=100, image_height=100,
        screen_width=100, screen_height=100,
        origin_x=1920, origin_y=0,
    )
    assert boxes[0].x1 == 1920


def test_parse_scan_boxes_normalizes_inverted_corners():
    boxes = parse_scan_boxes(
        "[BOX:200,200:100,100:x]",
        image_width=400, image_height=400,
        screen_width=400, screen_height=400,
    )
    b = boxes[0]
    assert b.x1 < b.x2 and b.y1 < b.y2


def test_parse_scan_boxes_skips_zero_area():
    boxes = parse_scan_boxes(
        "[BOX:10,10:11,11:tiny] [BOX:0,0:200,200:ok]",
        image_width=400, image_height=400,
        screen_width=400, screen_height=400,
    )
    labels = [b.label for b in boxes]
    assert "tiny" not in labels
    assert "ok" in labels


def test_parse_scan_boxes_ignores_garbage():
    boxes = parse_scan_boxes(
        "here is some prose with no tags at all",
        image_width=400, image_height=400,
        screen_width=400, screen_height=400,
    )
    assert boxes == []
