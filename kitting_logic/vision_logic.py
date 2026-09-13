"""
"Is this item on the table?" logic — no ROS, no hardware dependency.

Deliberately simple: each item is identified by a colour range (HSV), and
we call it "present" if a big enough blob of that colour shows up in the
camera frame. This is far more reliable to get working in one evening than
training an object detector, and it's plenty convincing for a demo on a
fixed tabletop with fixed lighting.

Tune the HSV ranges in config/checklists.yaml against your ACTUAL objects
and ACTUAL lighting — use tools/color_picker.py to make that fast.
"""
from typing import Dict, List, Tuple
import cv2
import numpy as np

# HSV range type: ((h_low, s_low, v_low), (h_high, s_high, v_high))
HsvRange = Tuple[Tuple[int, int, int], Tuple[int, int, int]]


def item_present(frame: np.ndarray, hsv_range: HsvRange, min_area: int = 800) -> bool:
    """True if a blob of the given HSV colour range, at least min_area pixels, is visible."""
    if frame is None:
        return False
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lower = np.array(hsv_range[0], dtype=np.uint8)
    upper = np.array(hsv_range[1], dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)
    # clean up small noise so stray pixels don't count as a "found" item
    mask = cv2.erode(mask, None, iterations=2)
    mask = cv2.dilate(mask, None, iterations=2)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return any(cv2.contourArea(c) >= min_area for c in contours)


def find_missing_items(
    frame: np.ndarray,
    required_items: List[str],
    item_colors: Dict[str, dict],
) -> List[str]:
    """
    For each required item name, look up its HSV range in item_colors and
    check whether it's visible in `frame`. Returns the list of items NOT
    found. item_colors[name] looks like:
        {"hsv_low": [h, s, v], "hsv_high": [h, s, v], "min_area": 800}
    """
    missing = []
    for name in required_items:
        cfg = item_colors.get(name)
        if cfg is None:
            # No colour configured for this item yet — treat as missing so
            # it's obvious in testing rather than silently always-passing.
            missing.append(name)
            continue
        hsv_range = (tuple(cfg["hsv_low"]), tuple(cfg["hsv_high"]))
        min_area = cfg.get("min_area", 800)
        if not item_present(frame, hsv_range, min_area):
            missing.append(name)
    return missing
