"""
"Is this item on the table?" logic — no ROS, no hardware dependency.

Each item is identified by a YOLOv8 class name (configured in
config/checklists.yaml under item_classes), and we call it "present" if
the model detects that class in the camera frame with at least the
configured confidence. This replaced an earlier HSV colour-blob approach,
which broke down under lighting changes and couldn't tell two same-
coloured items apart.

To get a working model:
    1. Take ~30-50 photos of each item, varying angle/background/lighting
       a bit (tools/capture_training_images.py does this for you).
    2. Label them with a free tool (Roboflow's web UI or LabelImg), using
       the SAME class names as `item_classes` in config/checklists.yaml
       (e.g. "red_block"). Export in YOLOv8 format — this gives you a
       data.yaml plus labelled image folders.
    3. Train:
           yolo detect train data=data.yaml model=yolov8n.pt epochs=50 imgsz=640
       A few dozen images per class and 50 epochs is enough for a fixed
       tabletop demo; ultralytics prints the best.pt path when it's done
       (usually runs/detect/train/weights/best.pt).
    4. Copy that best.pt to the path config/checklists.yaml's `yolo.weights`
       points at (default: models/best.pt).

Until a model exists at that path, YoloDetector raises YoloNotConfigured
with those same steps, rather than silently detecting nothing.
"""
from typing import Dict, List, Optional, Protocol
import os

import numpy as np


class Detector(Protocol):
    """Anything with this method can stand in for a real YOLO model — this
    is what lets tests (and the no-camera demo) run without loading any
    model, downloading weights, or touching a camera."""

    def detect(self, frame: np.ndarray) -> Dict[str, float]:
        """Return, for every class detected in `frame`, its highest
        confidence score (0.0-1.0). Classes not seen are simply absent
        from the dict."""
        ...


class YoloNotConfigured(RuntimeError):
    """Raised when no trained weights file exists yet at the configured path."""
    pass


class YoloDetector:
    """
    Thin wrapper around an Ultralytics YOLOv8 model. Loads the weights
    once — that's the expensive part — then .detect() is just a forward
    pass per frame.
    """

    def __init__(self, weights_path: str, min_predict_confidence: float = 0.1):
        if not os.path.exists(weights_path):
            raise YoloNotConfigured(
                f"No YOLO weights found at {weights_path!r}. Train a model on "
                f"your own items and point config/checklists.yaml's yolo.weights "
                f"at it — see the steps at the top of kitting_logic/vision_logic.py."
            )
        from ultralytics import YOLO  # imported lazily: importing this module
        # (e.g. for tests, or the no-camera demo) shouldn't require
        # ultralytics/torch unless a real detector is actually built.
        self._model = YOLO(weights_path)
        # Ask the model for anything even remotely plausible; per-item
        # confidence thresholds (below) do the real filtering. This just
        # avoids YOLO's own default cutoff discarding a box before we get
        # a chance to apply an item's configured threshold.
        self._min_predict_confidence = min_predict_confidence

    def detect(self, frame: np.ndarray) -> Dict[str, float]:
        results = self._model.predict(
            frame, conf=self._min_predict_confidence, verbose=False
        )[0]
        best: Dict[str, float] = {}
        names = results.names
        for box in results.boxes:
            name = names[int(box.cls[0])]
            conf = float(box.conf[0])
            if conf > best.get(name, 0.0):
                best[name] = conf
        return best


_detector_cache: Dict[str, "YoloDetector"] = {}


def get_detector(weights_path: str) -> YoloDetector:
    """Loads (and caches) a YoloDetector for a given weights file, so
    perception_node / demo_integration only pay the model-load cost once."""
    key = os.path.abspath(weights_path)
    if key not in _detector_cache:
        _detector_cache[key] = YoloDetector(weights_path)
    return _detector_cache[key]


def item_present(detections: Dict[str, float], class_name: str, confidence: float) -> bool:
    """True if `class_name` was detected with at least `confidence` score."""
    return detections.get(class_name, 0.0) >= confidence


def find_missing_items(
    detector: Detector,
    frame: np.ndarray,
    required_items: List[str],
    item_classes: Dict[str, dict],
    default_confidence: float = 0.5,
) -> List[str]:
    """
    Runs the detector once on `frame`, then for each required item name
    looks up its YOLO class name (and optional per-item confidence) in
    item_classes and returns the list of required items NOT found.
    item_classes[name] looks like:
        {"class_name": "red_block", "confidence": 0.5}   # confidence optional
    """
    detections = detector.detect(frame)
    missing = []
    for name in required_items:
        cfg = item_classes.get(name)
        if cfg is None:
            # No class configured for this item yet — treat as missing so
            # it's obvious in testing rather than silently always-passing.
            missing.append(name)
            continue
        class_name = cfg.get("class_name", name)
        confidence = cfg.get("confidence", default_confidence)
        if not item_present(detections, class_name, confidence):
            missing.append(name)
    return missing
