"""
Tests for the ROS-independent logic. Run these tonight, on Windows, with
no ROS and no hardware:

    python3 -m pytest test/test_logic.py -v

or, without pytest installed:

    python3 test/test_logic.py
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kitting_logic.qr_logic import normalize_mode
from kitting_logic.checklist_logic import get_required_items
from kitting_logic.vision_logic import item_present, find_missing_items
from kitting_logic.notify_logic import format_missing_message, FakeEmailNotifier, RateLimitedNotifier
from kitting_logic.dobot_logic import SimulatedDobot, run_pick_and_place


def test_normalize_mode():
    assert normalize_mode("MODE_1") == "mode_1"
    assert normalize_mode("mode-2") == "mode_2"
    assert normalize_mode("1") == "mode_1"
    assert normalize_mode(None) is None
    assert normalize_mode("") is None


def test_get_required_items():
    checklists = {"mode_1": ["a", "b"], "mode_2": ["c"]}
    assert get_required_items(checklists, "mode_1") == ["a", "b"]
    assert get_required_items(checklists, "mode_9") == []


def _make_solid_color_frame(h, w, bgr):
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:, :] = bgr
    return frame


def test_item_present_detects_matching_color():
    # Pure red in BGR is (0, 0, 255); its HSV hue is ~0.
    red_frame = _make_solid_color_frame(100, 100, (0, 0, 255))
    red_range = ((0, 100, 100), (10, 255, 255))
    assert item_present(red_frame, red_range, min_area=100) is True


def test_item_present_rejects_non_matching_color():
    # Pure blue in BGR is (255, 0, 0); should NOT match a red HSV range.
    blue_frame = _make_solid_color_frame(100, 100, (255, 0, 0))
    red_range = ((0, 100, 100), (10, 255, 255))
    assert item_present(blue_frame, red_range, min_area=100) is False


def test_find_missing_items():
    red_frame = _make_solid_color_frame(200, 200, (0, 0, 255))  # only red present
    item_colors = {
        "red_thing": {"hsv_low": [0, 100, 100], "hsv_high": [10, 255, 255], "min_area": 100},
        "blue_thing": {"hsv_low": [100, 100, 100], "hsv_high": [130, 255, 255], "min_area": 100},
    }
    missing = find_missing_items(red_frame, ["red_thing", "blue_thing"], item_colors)
    assert missing == ["blue_thing"]


def test_format_missing_message():
    assert "Still missing" in format_missing_message("mode_1", ["a", "b"])
    assert "complete" in format_missing_message("mode_1", [])


def test_rate_limited_notifier_dedupes():
    fake = FakeEmailNotifier()
    limiter = RateLimitedNotifier(fake, min_interval=100)
    limiter.maybe_send("missing: a", now=0)
    limiter.maybe_send("missing: a", now=1)  # same body, too soon — should NOT resend
    limiter.maybe_send("missing: b", now=2)  # changed — should send
    assert fake.sent == ["missing: a", "missing: b"]


def test_simulated_dobot_pick_and_place_runs_without_error():
    dobot = SimulatedDobot()
    dobot.connect()
    sequence = [
        {"action": "home"},
        {"action": "move", "x": 200, "y": 0, "z": 50, "r": 0},
        {"action": "suck", "on": True},
        {"action": "move", "x": 150, "y": 150, "z": 0, "r": 0},
        {"action": "suck", "on": False},
        {"action": "home"},
    ]
    run_pick_and_place(dobot, sequence)  # should not raise


if __name__ == "__main__":
    # Minimal runner if pytest isn't installed.
    import traceback
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL: {t.__name__}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
