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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kitting_logic.qr_logic import normalize_mode
from kitting_logic.checklist_logic import get_required_items
from kitting_logic.vision_logic import item_present, find_missing_items
from kitting_logic.notify_logic import format_missing_message, FakeEmailNotifier, RateLimitedNotifier
from kitting_logic.dobot_logic import SimulatedDobot, run_pick_and_place


class FakeDetector:
    """Conforms to vision_logic.Detector without loading a real YOLO model —
    reports exactly the class->confidence pairs it's constructed with."""

    def __init__(self, detections):
        self._detections = detections

    def detect(self, frame):
        return self._detections


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


def test_item_present_accepts_confident_detection():
    detections = {"red_block": 0.83}
    assert item_present(detections, "red_block", confidence=0.5) is True


def test_item_present_rejects_low_confidence():
    detections = {"red_block": 0.2}
    assert item_present(detections, "red_block", confidence=0.5) is False


def test_item_present_rejects_undetected_class():
    detections = {"blue_block": 0.9}
    assert item_present(detections, "red_block", confidence=0.5) is False


def test_find_missing_items():
    # Only red_thing was detected by the (fake) model.
    detector = FakeDetector({"red_thing": 0.9})
    item_classes = {
        "red_thing": {"class_name": "red_thing", "confidence": 0.5},
        "blue_thing": {"class_name": "blue_thing", "confidence": 0.5},
    }
    missing = find_missing_items(detector, frame=None, required_items=["red_thing", "blue_thing"],
                                  item_classes=item_classes)
    assert missing == ["blue_thing"]


def test_find_missing_items_respects_per_item_confidence():
    # Detected, but below this item's required confidence.
    detector = FakeDetector({"matchbox": 0.4})
    item_classes = {"matchbox": {"class_name": "matchbox", "confidence": 0.6}}
    missing = find_missing_items(detector, frame=None, required_items=["matchbox"],
                                  item_classes=item_classes)
    assert missing == ["matchbox"]


def test_format_missing_message():
    assert "Still missing" in format_missing_message("mode_1", ["a", "b"])
    assert "complete" in format_missing_message("mode_1", [])


def test_rate_limited_notifier_enforces_hard_minimum_gap():
    fake = FakeEmailNotifier()
    limiter = RateLimitedNotifier(fake, min_interval=100)
    limiter.maybe_send("missing: a", now=0)    # first call always sends
    limiter.maybe_send("missing: b", now=1)    # content changed, but too soon — should NOT resend
    limiter.maybe_send("missing: c", now=101)  # min_interval has now passed — should send
    assert fake.sent == ["missing: a", "missing: c"]


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
