#!/usr/bin/env python3
"""
ROS1 node: watches /verification_complete and /task_mode. The moment the
checklist becomes complete, runs the pick-and-place sequence for that
mode's required items.

Defaults to SIMULATION (~simulate:=true) so it's always safe to launch —
tomorrow at the lab, launch with `simulate:=false` to drive the real arm.
Nothing else about this node (or any other node) changes when you do that.
"""
import json
import os
import sys

import rospy
import yaml
from std_msgs.msg import String, Bool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from kitting_logic.dobot_logic import SimulatedDobot, RealDobot, run_pick_and_place

_state = {"mode": None, "required_items": [], "already_ran_for": None, "dobot": None, "coords": None}


def build_sequence(required_items, coords):
    """
    Builds a move/suck/move/suck sequence: for each required item, go to
    the pickup spot, suck on, lift, go to that item's bin, suck off, lift.
    Ends by returning home. Uses config/coordinates.yaml — fill in real
    numbers there tomorrow after jogging the arm.
    """
    home = coords["home"]
    pickup = coords["pickup"]["default"]
    hover = coords.get("hover_height_offset", 40)
    bins = coords["bins"]

    seq = [{"action": "home"}]
    for item in required_items:
        bin_pos = bins.get(item, home)  # falls back to home if a bin isn't configured yet
        seq += [
            {"action": "move", "x": pickup["x"], "y": pickup["y"], "z": pickup["z"] + hover, "r": pickup["r"]},
            {"action": "move", "x": pickup["x"], "y": pickup["y"], "z": pickup["z"], "r": pickup["r"]},
            {"action": "suck", "on": True},
            {"action": "move", "x": pickup["x"], "y": pickup["y"], "z": pickup["z"] + hover, "r": pickup["r"]},
            {"action": "move", "x": bin_pos["x"], "y": bin_pos["y"], "z": bin_pos["z"] + hover, "r": bin_pos["r"]},
            {"action": "move", "x": bin_pos["x"], "y": bin_pos["y"], "z": bin_pos["z"], "r": bin_pos["r"]},
            {"action": "suck", "on": False},
            {"action": "move", "x": bin_pos["x"], "y": bin_pos["y"], "z": bin_pos["z"] + hover, "r": bin_pos["r"]},
        ]
    seq.append({"action": "home"})
    return seq


def mode_callback(msg):
    _state["mode"] = msg.data


def required_callback(msg):
    _state["required_items"] = json.loads(msg.data)


def complete_callback(msg):
    if not msg.data:
        return
    mode = _state["mode"]
    if mode is None or mode == _state["already_ran_for"]:
        return  # already executed for this mode, or no mode known yet

    rospy.loginfo(f"dobot_node: checklist complete for {mode} — executing pick-and-place")
    sequence = build_sequence(_state["required_items"], _state["coords"])
    run_pick_and_place(_state["dobot"], sequence)
    _state["already_ran_for"] = mode
    rospy.loginfo(f"dobot_node: done with {mode}")


def main():
    rospy.init_node("dobot_node")

    simulate = rospy.get_param("~simulate", True)
    port = rospy.get_param("~port", "/dev/ttyUSB0")
    coords_path = rospy.get_param(
        "~coords_config",
        os.path.join(os.path.dirname(__file__), "..", "config", "coordinates.yaml"),
    )
    with open(coords_path) as f:
        _state["coords"] = yaml.safe_load(f)

    if simulate:
        rospy.logwarn("dobot_node: running in SIMULATION mode — no real arm movement. "
                      "Launch with simulate:=false at the lab tomorrow to use the real arm.")
        _state["dobot"] = SimulatedDobot()
    else:
        _state["dobot"] = RealDobot(port=port)

    _state["dobot"].connect()
    _state["dobot"].home()

    rospy.Subscriber("/task_mode", String, mode_callback)
    rospy.Subscriber("/required_items", String, required_callback)
    rospy.Subscriber("/verification_complete", Bool, complete_callback)

    rospy.loginfo("dobot_node: ready")
    rospy.spin()

    _state["dobot"].disconnect()


if __name__ == "__main__":
    main()
