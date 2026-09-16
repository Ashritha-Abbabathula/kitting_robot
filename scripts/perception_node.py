#!/usr/bin/env python3
"""
ROS1 node: owns the camera. Watches for a QR code to pick the task mode,
then keeps checking the required items against the camera feed.

This is a thin wrapper — all the actual logic lives in kitting_logic/,
which was written and tested without any ROS dependency. This file just
connects that logic to ROS topics.

Publishes:
    /task_mode          (std_msgs/String)   e.g. "mode_1"
    /required_items      (std_msgs/String)   JSON list, e.g. '["red_block", "blue_block"]'
    /missing_items        (std_msgs/String)   JSON list, e.g. '["blue_block"]'
    /verification_complete (std_msgs/Bool)

Re-scanning a different QR code at any time switches modes and resets
the checklist, per the "switch modes by rescanning" requirement.
"""
import json
import os
import sys

import cv2
import rospy
from std_msgs.msg import String, Bool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from kitting_logic.qr_logic import decode_qr, normalize_mode
from kitting_logic.checklist_logic import load_checklists, get_required_items
from kitting_logic.vision_logic import find_missing_items, build_detector, DetectorNotConfigured


def main():
    rospy.init_node("perception_node")

    camera_index = rospy.get_param("~camera_index", 0)
    config_path = rospy.get_param(
        "~checklist_config",
        os.path.join(os.path.dirname(__file__), "..", "config", "checklists.yaml"),
    )
    rate_hz = rospy.get_param("~rate_hz", 5.0)

    checklists = load_checklists(config_path)
    import yaml
    with open(config_path) as f:
        config = yaml.safe_load(f) or {}
    item_classes = config.get("item_classes", {})

    weights_path = os.path.join(
        os.path.dirname(config_path), "..", config.get("yolo", {}).get("weights", "models/best.pt")
    )
    secrets_path = os.path.join(os.path.dirname(config_path), "secrets.yaml")
    try:
        detector = build_detector(config, secrets_path, weights_path)
    except DetectorNotConfigured as e:
        rospy.logerr(f"perception_node: {e}")
        return

    mode_pub = rospy.Publisher("/task_mode", String, queue_size=1, latch=True)
    required_pub = rospy.Publisher("/required_items", String, queue_size=1, latch=True)
    missing_pub = rospy.Publisher("/missing_items", String, queue_size=1, latch=True)
    complete_pub = rospy.Publisher("/verification_complete", Bool, queue_size=1, latch=True)

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        rospy.logerr(f"perception_node: could not open camera index {camera_index}")
        return

    current_mode = None
    required_items = []

    rate = rospy.Rate(rate_hz)
    rospy.loginfo("perception_node: watching for a QR code...")

    while not rospy.is_shutdown():
        ok, frame = cap.read()
        if not ok:
            rospy.logwarn_throttle(5, "perception_node: camera frame read failed")
            rate.sleep()
            continue

        # Always check for a QR code, even mid-task, so re-scanning a
        # different code switches modes as required.
        raw = decode_qr(frame)
        mode = normalize_mode(raw)
        if mode and mode != current_mode and mode in checklists:
            current_mode = mode
            required_items = get_required_items(checklists, current_mode)
            rospy.loginfo(f"perception_node: mode switched to {current_mode}, "
                          f"requires {required_items}")
            mode_pub.publish(String(data=current_mode))
            required_pub.publish(String(data=json.dumps(required_items)))
            complete_pub.publish(Bool(data=False))

        if current_mode is not None:
            missing = find_missing_items(detector, frame, required_items, item_classes)
            missing_pub.publish(String(data=json.dumps(missing)))
            complete_pub.publish(Bool(data=(len(missing) == 0)))

        rate.sleep()

    cap.release()


if __name__ == "__main__":
    main()
